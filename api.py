import asyncio
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent.builder_agent import BuilderAgent
from .agent.tools import list_files, read_file

app = FastAPI(
    title="Locable Builder API",
    description="FastAPI wrapper exposing the builder agent for frontend use.",
    version="0.1.0",
)

# Get the directory containing this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")

# Mount static files
if os.path.exists(SITE_DIR):
    app.mount("/static", StaticFiles(directory=os.path.join(SITE_DIR, "static")), name="static")


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Website request or instructions.")
    model: Optional[str] = Field(None, description="Override the model name for this run.")
    host: Optional[str] = Field(None, description="Override the Ollama host URL.")
    debug: bool = Field(False, description="Log full agent responses to the server console.")


class GenerateResponse(BaseModel):
    status: str
    message: str
    files: List[str]


async def _run_builder(req: GenerateRequest) -> str:
    """Run the builder agent in a worker thread to keep the event loop responsive."""
    agent = BuilderAgent(model=req.model, host=req.host)
    return await asyncio.to_thread(agent.ask, req.prompt, req.debug)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    """Serve the index.html file."""
    index_path = os.path.join(SITE_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path, media_type="text/html")


@app.get("/files", response_model=List[str])
async def list_site_files():
    """List generated files under the site/ directory."""
    return list_files("site")


@app.get("/files/{path:path}", response_class=PlainTextResponse)
async def read_site_file(path: str):
    """Read a generated file. Paths are anchored under site/ for safety."""
    normalized = path if path.startswith("site") else f"site/{path}"
    content = read_file(normalized)
    if isinstance(content, str) and content.startswith("ERROR:"):
        raise HTTPException(status_code=404, detail=content)
    return content


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """Trigger a build from the frontend and return the agent's summary plus written files."""
    try:
        message = await _run_builder(req)
        files = list_files("site")
        return {"status": "ok", "message": message, "files": files}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
