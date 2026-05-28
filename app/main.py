from fastapi import FastAPI

from .routers import parse

app = FastAPI(
    title="Parser Service",
    version="0.1.0",
    description="Code parsing service — Various languages supported, for extraction over REST",
)

app.include_router(parse.router, prefix="/structured", tags=["parse", "structured"])
app.include_router(parse.router, prefix="/parse", tags=["parse"])


@app.get("/health")
async def health():
    return {"status": "ok"}