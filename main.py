import traceback
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from app import orchestrator, registry  # noqa: E402

MSG_UNAVAILABLE = "The ad data service is currently unavailable. Please try again shortly."
MSG_TIMEOUT = "The request timed out. Please retry."
MSG_GENERIC = "An unexpected error occurred. Please rephrase your question or try again."


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
    except orchestrator.MCPUnavailableError as exc:
        print(f"[query] MCP unavailable: {exc}")
        text = MSG_UNAVAILABLE
    except orchestrator.MCPTimeoutError as exc:
        print(f"[query] MCP timeout: {exc}")
        text = MSG_TIMEOUT
    except (httpx.ConnectError, httpx.RequestError) as exc:
        print(f"[query] transport error: {exc}")
        text = MSG_UNAVAILABLE
    except httpx.TimeoutException as exc:
        print(f"[query] timeout: {exc}")
        text = MSG_TIMEOUT
    except Exception as exc:
        print(f"[query] unexpected error: {exc}")
        traceback.print_exc()
        text = MSG_GENERIC
    return QueryResponse(response=text)
