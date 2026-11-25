from fastapi import FastAPI
from app.api.routes import auth,users,documents,chat
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.rag import get_rag

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_rag().warmup()
    yield

app = FastAPI(
    title="a Medical Reserach Assistant",
    description="This is a Medical Research Assistant API that helps researchers to find relevant medical research papers and articles based on their queries.",
    version="1.0.0",
    lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(documents.router)
app.include_router(chat.router)
@app.get("/")
async def read_root():  
    return {"message": "Welcome to the Medical Research Assistant API!"}


