import re
import uuid
import hashlib
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

   
        


    def ingest(self, document: dict):

        required = [
            "document_id",
            "tenant_id",
            "owner_id",
            "title",
            "version",
            "blocks",
            "visibility",
        ]

        missing = [key for key in required if key not in document]

        if missing:
            raise ValueError(f"Missing document fields: {missing}")

        if document["visibility"] not in {"private", "shared", "tenant"}:
            raise ValueError("Invalid document visibility")

        # Stage 1: Chunk
        chunks = self.chunk_document(document)

        if not chunks:
            raise ValueError("No content available for ingestion")

        # Stage 2: Embed
        embeddings = self.embed_chunks(chunks)

        

        return {
            "document_id": document["document_id"],
            "chunks_created": len(chunks),
            "status": "pending",
        }