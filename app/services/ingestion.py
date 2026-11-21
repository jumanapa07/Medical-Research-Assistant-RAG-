import hashlib
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Callable, Optional, Protocol

import numpy as np

REQUIRED_METADATA = ["document_id", "tenant_id", "owner_id", "title", "version", "visibility"]

SKIP_LABELS = {"page_header", "page_footer"}        # repeated noise on every page
PROSE_TYPES = {"paragraph", "list", "caption", "footnote", "title"}
ATOMIC_TYPES = {"table", "code"}                    # never merged with neighbours
PRESERVE_WS_TYPES = {"code", "formula"}             # whitespace is meaningful

SEP_COST = 1                                        # token slack for the "\n\n" between segments
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(\[])')
_MD_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+\S")
_PDF_FIXES = str.maketrans({
    "\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl",
    "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u00ad": "", "\u200b": "", "\ufeff": "",
})


class VectorStore(Protocol):
    """Minimal interface for stage 4. Implement for Qdrant / pgvector / OpenSearch."""

    def upsert(self, chunks: list[dict], embeddings: np.ndarray) -> None: ...

    def delete_document(self, tenant_id: str, document_id: str, keep_chunk_ids: set) -> int: ...


class InMemoryVectorStore:
    """Reference implementation used by the POC/tests. Always filters by tenant."""

    def __init__(self):
        self._rows: dict[str, tuple[dict, np.ndarray]] = {}

    def upsert(self, chunks, embeddings):
        for chunk, vec in zip(chunks, embeddings):
            self._rows[chunk["chunk_id"]] = (chunk, np.asarray(vec))

    def delete_document(self, tenant_id, document_id, keep_chunk_ids):
        stale = [cid for cid, (c, _) in self._rows.items()
                 if c["tenant_id"] == tenant_id and c["document_id"] == document_id
                 and cid not in keep_chunk_ids]
        for cid in stale:
            del self._rows[cid]
        return len(stale)

    def search(self, query_vec, tenant_id, k=5):
        rows = [(c, v) for c, v in self._rows.values() if c["tenant_id"] == tenant_id]
        if not rows:
            return []
        scores = np.array([float(v @ query_vec) for _, v in rows])
        order = np.argsort(-scores)[:k]
        return [(rows[i][0], float(scores[i])) for i in order]

    def count(self, tenant_id=None, document_id=None):
        return sum(1 for c, _ in self._rows.values()
                   if (tenant_id is None or c["tenant_id"] == tenant_id)
                   and (document_id is None or c["document_id"] == document_id))


class IngestionPipeline:

    def __init__(
        self,
        collection_name: str,
        embedding_model: str = "BAAI/bge-small-en-v1.5",
        chunk_size: int = 400,       # TOKENS (embedding-model tokenizer), not characters
        chunk_overlap: int = 60,     # TOKENS
        *,
        model=None,                  # injectable SentenceTransformer-like object
        converter=None,              # injectable Docling DocumentConverter
        token_counter: Optional[Callable[[str], int]] = None,
        max_file_mb: int = 100,
        query_instruction: Optional[str] = None,
    ):
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size // 2:
            raise ValueError("Invalid chunk size or overlap (overlap must be < chunk_size/2)")

        self.collection_name = collection_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_file_bytes = max_file_mb * 1024 * 1024
        self.max_prefix = max(16, chunk_size // 4)
        self._converter = converter

        if model is None:
            from sentence_transformers import SentenceTransformer  # lazy: heavy import
            model = SentenceTransformer(embedding_model)
        self.model = model

        max_seq = getattr(model, "max_seq_length", None)
        if max_seq and chunk_size > max_seq - 8:
            raise ValueError(
                f"chunk_size={chunk_size} tokens exceeds the model limit ({max_seq}); "
                "longer chunks would be silently truncated at embedding time"
            )

        dim_fn = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
        self.embedding_dimension = dim_fn()

        if token_counter is None:
            tokenizer = model.tokenizer
            token_counter = lambda text: len(tokenizer.encode(text, add_special_tokens=False))  # noqa: E731
        self._count = token_counter

        

    @property
    def converter(self):
        if self._converter is None:
            self._converter = self._build_converter()
        return self._converter

    @staticmethod
    def _build_converter():
        from docling.document_converter import DocumentConverter
        try:  # explicit pipeline options (OCR for scans, table structure); API differs across versions
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import PdfFormatOption

            opts = PdfPipelineOptions()
            opts.do_ocr = True
            opts.do_table_structure = True
            return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
        except Exception:  # noqa: BLE001
            return DocumentConverter()

    def _len(self, text: str) -> int:
        return self._count(text)

    @staticmethod
    def clean_text(text: str, preserve_whitespace: bool = False) -> str:
        if not text:
            return ""
        # NFC + explicit PDF-artifact fixes. NFKC is avoided: it rewrites x² -> x2, ① -> 1.
        text = unicodedata.normalize("NFC", text).translate(_PDF_FIXES)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if preserve_whitespace:                      # code / formulas keep their indentation
            return text.strip("\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" ?\n ?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _heading_level(text: str, docling_level) -> int:
        """Docling often reports every heading as level 1; numbering is a more reliable signal."""
        m = _NUMBERED_HEADING.match(text)
        if m:
            return len(m.group(1).split("."))
        return max(1, int(docling_level or 1))

    def parse_document(self, file_path: str, metadata: dict) -> dict:
        """
        Convert a PDF into structured document blocks.
        metadata must come from the trusted backend: document_id, tenant_id, owner_id,
        title, version, visibility.
        """
        missing = [f for f in REQUIRED_METADATA if metadata.get(f) in (None, "")]
        if missing:
            raise ValueError(f"Missing metadata: {missing}")

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Document not found: {file_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError("Currently only PDF files are supported")
        if path.stat().st_size > self.max_file_bytes:
            raise ValueError("File exceeds maximum allowed size")
        with path.open("rb") as fh:
            if not fh.read(5).startswith(b"%PDF"):
                raise ValueError("File is not a valid PDF")

        result = self.converter.convert(str(path))
        doc = result.document
        if doc is None:
            raise ValueError("Document parsing failed")

        blocks = []
        for item, _depth in doc.iterate_items():
            label = getattr(item.label, "value", str(item.label)).lower()
            if label in SKIP_LABELS:
                continue

            page_number = item.prov[0].page_no if getattr(item, "prov", None) else None
            level = 0

            if label == "table":
                try:
                    content = item.export_to_markdown(doc=doc)
                except Exception:  # noqa: BLE001
                    content = item.export_to_dataframe(doc=doc).to_csv(index=False)
                block_type = "table"
            else:
                content = getattr(item, "text", "") or ""
                block_type = {
                    "section_header": "heading", "title": "title", "list_item": "list",
                    "caption": "caption", "footnote": "footnote",
                    "code": "code", "formula": "formula",
                }.get(label, "paragraph")

            content = self.clean_text(content, preserve_whitespace=block_type in PRESERVE_WS_TYPES)
            if not content:
                continue

            if block_type == "heading":
                content = " ".join(content.split())
                level = self._heading_level(content, getattr(item, "level", 1))

            blocks.append({
                "type": block_type, "level": level, "content": content,
                "page_number": page_number, "source_label": label,
            })

        if not blocks:
            raise ValueError("No extractable content found in PDF")

        return {**metadata, "source": path.name, "blocks": blocks}

    def _hard_split(self, text: str, max_size: int) -> list[str]:
        """Last resort: pack whole words; only slice inside a word that alone exceeds the limit."""
        out, cur, cur_len = [], [], 0
        for word in text.split():
            wl = self._len(word)
            if wl > max_size:
                if cur:
                    out.append(" ".join(cur))
                    cur, cur_len = [], 0
                step = max(1, max_size)
                out.extend(word[i:i + step] for i in range(0, len(word), step))
                continue
            add = wl + (1 if cur else 0)
            if cur and cur_len + add > max_size:
                out.append(" ".join(cur))
                cur, cur_len = [word], wl
            else:
                cur.append(word)
                cur_len += add
        if cur:
            out.append(" ".join(cur))
        return out

    def _split_sentences(self, text: str, max_size: int) -> list[str]:
        # re.split keeps every character, so no text can be silently dropped.
        sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
        pieces, current, cur_len = [], "", 0
        for sentence in sentences:
            sl = self._len(sentence)
            if sl > max_size:
                if current:
                    pieces.append(current)
                    current, cur_len = "", 0
                pieces.extend(self._hard_split(sentence, max_size))
                continue
            add = sl + (1 if current else 0)
            if current and cur_len + add > max_size:
                pieces.append(current)
                current, cur_len = sentence, sl
            else:
                current = f"{current} {sentence}".strip()
                cur_len += add
        if current:
            pieces.append(current)
        return pieces

    def _split_lines(self, text: str, max_size: int) -> list[str]:
        """Line-preserving split (code, tables without a clear header)."""
        pieces, cur, cur_len = [], [], 0
        for line in text.splitlines():
            ll = self._len(line) + 1
            if ll > max_size:
                if cur:
                    pieces.append("\n".join(cur))
                    cur, cur_len = [], 0
                pieces.extend(self._hard_split(line, max_size))
                continue
            if cur and cur_len + ll > max_size:
                pieces.append("\n".join(cur))
                cur, cur_len = [], 0
            cur.append(line)
            cur_len += ll
        if cur:
            pieces.append("\n".join(cur))
        return pieces

    def _split_table(self, text: str, max_size: int) -> list[str]:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) < 2:
            return self._hard_split(text, max_size)

        header_lines = 2 if _MD_SEP.match(lines[1]) else 1      # markdown: header + separator row
        header = "\n".join(lines[:header_lines])
        rows = lines[header_lines:]
        hl = self._len(header)
        if not rows or hl >= max_size // 2:
            return self._split_lines(text, max_size)

        pieces, cur, cur_len = [], [], hl
        for row in rows:
            rl = self._len(row) + 1
            if hl + rl > max_size:                              
                if cur:
                    pieces.append(header + "\n" + "\n".join(cur))
                    cur, cur_len = [], hl
                pieces.extend(f"{header}\n{frag}" for frag in self._hard_split(row, max_size - hl - 1))
                continue
            if cur and cur_len + rl > max_size:
                pieces.append(header + "\n" + "\n".join(cur))
                cur, cur_len = [], hl
            cur.append(row)
            cur_len += rl
        if cur:
            pieces.append(header + "\n" + "\n".join(cur))
        return pieces

    def _split_block(self, text: str, block_type: str, max_size: int) -> list[str]:
        if self._len(text) <= max_size:
            return [text]
        if block_type == "table":
            return self._split_table(text, max_size)
        if block_type == "code":
            return self._split_lines(text, max_size)
        return self._split_sentences(text, max_size)

    def _get_overlap(self, text: str, max_size: int) -> str:
        """Tail of the previous chunk: whole words only, preferably starting at a sentence start."""
        limit = min(self.chunk_overlap, max_size)
        if limit <= 0 or not text:
            return ""

        window = limit * 12                                      
        tail = text[-window:]
        starts = [m.start() for m in re.finditer(r"\S+", tail)]
        if len(tail) < len(text) and not text[-len(tail) - 1].isspace():
            starts = starts[1:]                                 

        best = ""
        for s in reversed(starts):
            if self._len(tail[s:]) > limit:
                break
            best = tail[s:]
        boundary = re.search(r"[.!?]\s+(?=\S)", best)
        if boundary:
            best = best[boundary.end():]
        return best.strip()

    @staticmethod
    def _truncate(text: str, n: int) -> str:
        text = " ".join((text or "").split())
        return text if len(text) <= n else text[: n - 1].rstrip() + "\u2026"

    def _build_prefix(self, title: str, path: list[str]) -> str:
        """Document/section context prepended to every chunk; always fits in max_prefix tokens."""

        def render(t, parts, dropped):
            lines = f"Document: {t}\n" if t else ""
            if parts:
                shown = (["\u2026"] if dropped else []) + parts
                lines += f"Section: {' > '.join(shown)}\n"
            return lines + "\n" if lines else ""

        t = self._truncate(title, 120)
        parts = [self._truncate(p, 80) for p in path]
        dropped = False
        prefix = render(t, parts, dropped)
        while parts and self._len(prefix) > self.max_prefix:
            parts, dropped = parts[1:], True                     
            prefix = render(t, parts, dropped)
        if self._len(prefix) > self.max_prefix:
            prefix = render(self._truncate(title, 40), parts, dropped)
        if self._len(prefix) > self.max_prefix:
            prefix = ""
        return prefix

    def chunk_document(self, document: dict) -> list[dict]:
        chunks: list[dict] = []
        section_path: list[str] = []
        segments: list[dict] = []
        seg_tokens = 0
        chunk_index = 0
        prefix_cache: dict[tuple, str] = {}

        def prefix() -> str:
            key = tuple(section_path)
            if key not in prefix_cache:
                prefix_cache[key] = self._build_prefix(document["title"], section_path)
            return prefix_cache[key]

        def flush():
            """Emit current segments as a chunk. Returns (body, last_real_type, last_real_page)."""
            nonlocal segments, seg_tokens, chunk_index
            if not segments:
                return "", "", None

            body = "\n\n".join(s["content"] for s in segments)
            content = prefix() + body
            pages = [s["page_number"] for s in segments if s["page_number"] is not None]
            body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            chunk_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{document['tenant_id']}:{document['document_id']}:{document['version']}:{chunk_index}:{body_hash}",
            ))

            chunks.append({
                "chunk_id": chunk_id,
                "document_id": document["document_id"],
                "tenant_id": document["tenant_id"],
                "owner_id": document["owner_id"],
                "visibility": document["visibility"],
                "version": document["version"],
                "title": document["title"],
                "section_path": list(section_path),
                "chunk_index": chunk_index,
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "block_types": list(dict.fromkeys(s["type"] for s in segments)),
                "text": body,                    # clean body: show to users / feed to the LLM
                "content": content,              # prefix + body: what gets embedded
                "content_hash": body_hash,
                "token_count": self._len(content),
            })

            real = [s for s in segments if s["type"] != "overlap"] or segments
            chunk_index += 1
            segments, seg_tokens = [], 0
            return body, real[-1]["type"], real[-1]["page_number"]

        for block in document["blocks"]:
            block_type = block.get("type", "paragraph")
            text = self.clean_text(block.get("content", ""), preserve_whitespace=block_type in PRESERVE_WS_TYPES)
            if not text:
                continue
            page = block.get("page_number")

            if block_type == "heading":
                flush()
                text = " ".join(text.split())
                level = max(1, int(block.get("level", 1) or 1))
                level = min(level, len(section_path) + 1)       
                section_path[:] = section_path[:level - 1]
                section_path.append(text)
                continue

            budget = self.chunk_size - self._len(prefix())

            if block_type in ATOMIC_TYPES:                       
                flush()
                for piece in self._split_block(text, block_type, budget):
                    segments.append({"content": piece, "type": block_type, "page_number": page})
                    flush()
                continue

            is_prose = block_type in PROSE_TYPES
            if self._len(text) <= budget:
                pieces = [text]
            else:   # leave room so the overlap fits next to every split piece
                reserve = self.chunk_overlap + SEP_COST + 1
                pieces = self._split_block(text, block_type, max(budget - reserve, budget // 2))

            for piece in pieces:
                pl = self._len(piece)
                if segments and seg_tokens + SEP_COST + pl > budget:
                    prev_body, prev_type, prev_page = flush()
                    overlap = ""
                    if is_prose and prev_type in PROSE_TYPES:
                        overlap = self._get_overlap(prev_body, budget - pl - SEP_COST)
                    if overlap:
                        segments.append({"content": overlap, "type": "overlap", "page_number": prev_page})
                        seg_tokens = self._len(overlap)
                seg_tokens += pl + (SEP_COST if segments else 0)
                segments.append({"content": piece, "type": block_type, "page_number": page})

        flush()
        return chunks

    def embed_chunks(self, chunks: list[dict]) -> np.ndarray:
        if not chunks:
            return np.zeros((0, self.embedding_dimension), dtype="float32")
        return self.model.encode(
            [c["content"] for c in chunks],
            batch_size=32, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False,
        )

    def ingest_document(self, document: dict, store: Optional[VectorStore] = None) -> dict:
        chunks = self.chunk_document(document)
        if not chunks:
            raise ValueError("Chunking produced no chunks")
        embeddings = self.embed_chunks(chunks)

        status, removed = "embedded_not_persisted", 0
        if store is not None:
            # Upsert first, then drop stale chunks (older versions / previous chunking of this
            # version): readers never see a gap. For true atomicity use a version flag in the store.
            store.upsert(chunks, embeddings)
            removed = store.delete_document(
                document["tenant_id"], document["document_id"],
                keep_chunk_ids={c["chunk_id"] for c in chunks},
            )
            status = "active"

        result = {
            "document_id": document["document_id"],
            "version": document["version"],
            "blocks_extracted": len(document["blocks"]),
            "chunks_created": len(chunks),
            "embeddings_created": len(embeddings),
            "stale_chunks_removed": removed,
            "max_chunk_tokens": max(c["token_count"] for c in chunks),
            "status": status,
        }
        if store is None:   
            result["chunks"], result["embeddings"] = chunks, embeddings
        return result

    def ingest_file(self, file_path: str, metadata: dict, store: Optional[VectorStore] = None) -> dict:
        document = self.parse_document(file_path, metadata)
        return self.ingest_document(document, store)