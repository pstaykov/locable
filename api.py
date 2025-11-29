import asyncio
from uuid import uuid4
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .agent.builder_agent import BuilderAgent
from .agent.tools import list_files, read_file

app = FastAPI(
    title="Locable Builder API",
    description="FastAPI wrapper exposing the builder agent for frontend use.",
    version="0.1.0",
)

RUN_MESSAGES: Dict[str, List[dict]] = {}


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Website request or instructions.")
    model: Optional[str] = Field(None, description="Override the model name for this run.")
    host: Optional[str] = Field(None, description="Override the Ollama host URL.")
    debug: bool = Field(False, description="Log full agent responses to the server console.")


class GenerateResponse(BaseModel):
    status: str
    message: str
    run_id: str
    files: List[str]


class MessagesResponse(BaseModel):
    run_id: str
    cursor: int
    next_cursor: int
    messages: List[dict]


async def _run_builder(req: GenerateRequest, run_id: str) -> str:
    """Run the builder agent in a worker thread to keep the event loop responsive."""
    agent = BuilderAgent(model=req.model, host=req.host)

    def runner():
        result = agent.ask(req.prompt, req.debug)
        # snapshot message history for retrieval
        RUN_MESSAGES[run_id] = [
            {
                "role": m.get("role"),
                "content": m.get("content"),
                "tool_calls": m.get("tool_calls"),
            }
            for m in agent.messages
        ]
        return result

    return await asyncio.to_thread(runner)


@app.get("/health")
async def health():
    return {"status": "ok"}


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
    run_id = uuid4().hex
    try:
        message = await _run_builder(req, run_id)
        files = list_files("site")
        return {"status": "ok", "message": message, "run_id": run_id, "files": files}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/messages", response_model=MessagesResponse)
async def get_messages(run_id: str, cursor: int = 0):
    """Fetch stored messages for a run starting at the given cursor index."""
    if cursor < 0:
        raise HTTPException(status_code=400, detail="cursor must be >= 0")
    messages = RUN_MESSAGES.get(run_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="run_id not found")

    slice_msgs = messages[cursor:]
    next_cursor = cursor + len(slice_msgs)
    return {
        "run_id": run_id,
        "cursor": cursor,
        "next_cursor": next_cursor,
        "messages": slice_msgs,
    }
