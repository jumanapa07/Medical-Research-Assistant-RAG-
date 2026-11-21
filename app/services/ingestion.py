import re
from pathlib import Path
from docling.document_converter import DocumentConverter
import unicodedata

from sentence_transformers import SentenceTransformer


class IngestionPipeline:

    def __init__(
        self,
        collection_name: str,
        embedding_model: str = "BAAI/bge-small-en-v1.5",
        chunk_size: int = 1800,
        chunk_overlap: int = 200,
    ):
        self.converter = DocumentConverter()
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("Invalid chunk size or overlap")

        self.collection_name = collection_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Initialize dependencies once.
        self.model = SentenceTransformer(embedding_model)
        self.embedding_dimension = self.model.get_sentence_embedding_dimension()

        


    @staticmethod
    def clean_text(text: str) -> str:

        if not text:
            return ""

        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def parse_document(self, file_path: str, metadata: dict) -> dict:
        """
        Convert a PDF into structured document blocks.

        metadata must come from the trusted backend:
        document_id, tenant_id, owner_id, title, version, visibility.
        """

        path = Path(file_path)

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Document not found: {file_path}")

        required = [
            "document_id",
            "tenant_id",
            "owner_id",
            "title",
            "version",
            "visibility",
        ]

        missing = [field for field in required if field not in metadata]

        if missing:
            raise ValueError(f"Missing metadata: {missing}")

        if path.suffix.lower() != ".pdf":
            raise ValueError("Currently only PDF files are supported")

        # Convert PDF
        result = self.converter.convert(str(path))
        doc = result.document

        if doc is None:
            raise ValueError("Document parsing failed")

        blocks = []

        # Iterate through elements in document reading order
        for item, hierarchy_level in doc.iterate_items():

            label = getattr(item.label, "value", str(item.label)).lower()

            # Extract page provenance
            page_number = None

            if item.prov:
                page_number = item.prov[0].page_no

            # Identify document element type
            if label == "table":

                # Preserve table structure instead of flattening it.
                dataframe = item.export_to_dataframe(doc=doc)
                content = dataframe.to_csv(index=False)
                block_type = "table"
                heading_level = 0

            else:
                content = getattr(item, "text", "")
                heading_level = 0

                if label == "section_header":
                    block_type = "heading"
                    heading_level = getattr(item, "level", 1) or 1

                elif label == "title":
                    block_type = "title"

                elif label == "list_item":
                    block_type = "list"

                elif label == "caption":
                    block_type = "caption"

                else:
                    block_type = "paragraph"

            content = self.clean_text(content)

            if not content:
                continue

            blocks.append({
                "type": block_type,
                "level": heading_level,
                "content": content,
                "page_number": page_number,
                "source_label": label,
            })

        if not blocks:
            raise ValueError("No extractable content found in PDF")

        # Metadata is supplied by the trusted backend,
        # not extracted from the uploaded document.
        return {
            **metadata,
            "source": str(path.name),
            "blocks": blocks,
        }
    
    def chunk_document(self, document: dict) -> list[dict]:

        # paragraph aware sentence based chunking
        paragraphs = [para.strip() for para in re.split(r"\n\s*\n", text)]
        pieces = []
        for paragraph in paragraphs:
            if len(paragraph) <= self.chunk_size:
                pieces.append(paragraph)
                continue
            senetnces = re.findall(r"[^.!?]+[.!?]+(?:\s|$)|[^.!?]+$", paragraph)
            # apply overlapping
            buffer = ""
            for sentence in senetnces:
                if buffer and len(buffer) + len(sentence) > self.chunk_size:
                    pieces.append(buffer)
                    buffer = buffer[-self.chunk_overlap:]  # keep overlap

                buffer += sentence

            if buffer.strip():
                pieces.append(buffer.strip())
            chunks = []
            overlap = ""
        for piece in pieces:
            if overlap and len(overlap) + len(piece) + 2 > self.chunk_size:
                chunks.append(overlap.strip())
                overlap = ""
            overlap = overlap + piece if overlap else piece

        if overlap.strip():
            chunks.append(overlap.strip())

        return chunks
    def embed_chunks(self, chunks: list[dict]):

        texts = [chunk["content"] for chunk in chunks]

        return self.model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )


    def ingest_file(self, file_path: str, metadata: dict):

        # Stage 1: Parse
        document = self.parse_document(file_path, metadata)

        # Stage 2: Chunk
        chunks = self.chunk_document(document)

        # Stage 3: Embed
        embeddings = self.embed_chunks(chunks)

        return {
            "document_id": document["document_id"],
            "blocks_extracted": len(document["blocks"]),
            "chunks_created": len(chunks),
            "embeddings_created": len(embeddings),
            "status": "pending",
        }