from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from app import orchestrator, registry  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await registry.load()
    except Exception as exc:
        print(f"[startup] registry.load failed: {exc}")
    yield


app = FastAPI(title="Meta MCP Prototype", lifespan=lifespan)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    response: str


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    try:
        text = await orchestrator.run_query(req.query)
    except Exception as exc:
        text = f"Error: {exc}"
    return QueryResponse(response=text)
