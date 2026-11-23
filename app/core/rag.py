from app.services.ingestion import IngestionPipeline
from app.services.vector_store import QdrantVectorStore
from app.services.ingestion_service import DocumentIngestionService
from app.services.retriever import Retriever
from app.services.generation import GenerationService

from sentence_transformers import SentenceTransformer

pipeline = IngestionPipeline(
    collection_name="medical_research",
    embedding_model="BAAI/bge-small-en-v1.5",
    chunk_size=400,
    chunk_overlap=60,
)
embedding_model = SentenceTransformer(
    "BAAI/bge-small-en-v1.5"
)
vector_store = QdrantVectorStore(
    collection_name="medical_research",
    vector_size=pipeline.embedding_dimension,
    url="http://localhost:6333",
)

ingestion_service = DocumentIngestionService(
    pipeline=pipeline,
    vector_store=vector_store,
)
retriever = Retriever(
    store=vector_store,
    embedding_model=embedding_model,
)

generation_service = GenerationService()