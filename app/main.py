from fastapi import FastAPI

app = FastAPI(
    title="a Medical Reserach Assistant",
    description="This is a Medical Research Assistant API that helps researchers to find relevant medical research papers and articles based on their queries.",
    version="1.0.0",
)

@app.get("/")
async def read_root():  
    return {"message": "Welcome to the Medical Research Assistant API!"}


