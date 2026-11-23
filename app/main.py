from fastapi import FastAPI
from app.api.routes import auth,users,documents,chat

app = FastAPI(
    title="a Medical Reserach Assistant",
    description="This is a Medical Research Assistant API that helps researchers to find relevant medical research papers and articles based on their queries.",
    version="1.0.0",
)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(documents.router)
app.include_router(chat.router)
@app.get("/")
async def read_root():  
    return {"message": "Welcome to the Medical Research Assistant API!"}


