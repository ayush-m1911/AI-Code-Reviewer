from fastapi import FastAPI

from app.api import router


app = FastAPI(
    title="AI Code Reviewer",
    version="1.0.0"
)

app.include_router(router)