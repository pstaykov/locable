import asyncio
import os
from uuid import uuid4
from pathlib import Path
import shutil
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent.builder_agent import BuilderAgent
from .agent.tools import ROOT_DIR, list_files, read_file
from .rag.vectorstore import LocalVectorStore

ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

app = FastAPI(
    title="Locable Builder API",
    description="FastAPI wrapper exposing the builder agent for frontend use.",
    version="0.1.0",
)

RUN_MESSAGES: Dict[str, List[dict]] = {}

# Project roots and common paths (inner package lives at locable/locable)
PACKAGE_ROOT = ROOT_DIR
SITE_DIR = PACKAGE_ROOT / "frontend"
TEMPLATE_DIR = PACKAGE_ROOT / "data" / "templates"
BOOTSTRAP_DIR = PACKAGE_ROOT / "data" / "bootstrap"
CHROMA_DIR = PACKAGE_ROOT / "data" / "chroma"
SITE_OUTPUT_DIR = PACKAGE_ROOT / "site"

SITE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files
if SITE_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(SITE_DIR / "static")), name="static")
app.mount("/site", StaticFiles(directory=str(SITE_OUTPUT_DIR), html=True), name="site")


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Website request or instructions.")
    model: Optional[str] = Field(None, description="Override the model name for this run.")
    host: Optional[str] = Field(None, description="Override the Ollama host URL.")
    debug: bool = Field(False, description="Log full agent responses to the server console.")
    mode: str = Field("full", description="Generation mode: 'full' (LLM) or 'html-only' (template copy).")


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
    agent = BuilderAgent(model=req.model, host=ollama_host)

    def runner():
        result = agent.ask(req.prompt, req.debug)
        # snapshot full message history for retrieval/debug UI
        RUN_MESSAGES[run_id] = agent.messages.copy()
        return result

    return await asyncio.to_thread(runner)


def _copy_bootstrap_to_site():
    """Ensure site/static has bootstrap assets for html-only mode."""
    for dest_root in [
        SITE_OUTPUT_DIR / "static",
        SITE_DIR / "static",
    ]:
        dest_root.mkdir(parents=True, exist_ok=True)
        for fname in ("bootstrap.min.css", "bootstrap.bundle.min.js"):
            src = BOOTSTRAP_DIR / fname
            dst = dest_root / fname
            if src.exists():
                shutil.copy(src, dst)


def _pick_template(prompt: str) -> tuple[str, Path]:
    store = LocalVectorStore(persist_dir=str(CHROMA_DIR), collection_name="bootstrap")
    hits = store.search_templates(prompt, k=1)

    # Fallback: broaden search if description-only filter returned nothing
    if not hits:
        try:
            broad = store.search(prompt, k=3, include_meta=True)
            docs = (broad.get("documents") or [[]])[0]
            metas = (broad.get("metadatas") or [[]])[0]
            if docs and metas:
                template_name = metas[0].get("template")
                if template_name:
                    hits = [{"template": template_name}]
        except Exception:
            hits = []

    if not hits:
        raise HTTPException(status_code=404, detail="No templates found for the given description.")

    template_name = hits[0].get("template")
    if not template_name:
        raise HTTPException(status_code=404, detail="Template metadata missing.")
    template_root = TEMPLATE_DIR / template_name
    if not template_root.exists():
        raise HTTPException(status_code=404, detail=f"Template directory not found: {template_name}")
    return template_name, template_root


def _find_main_html(template_root: Path) -> Path:
    index_path = template_root / "index.html"
    if index_path.exists():
        return index_path
    html_files = sorted(template_root.rglob("*.html"))
    if not html_files:
        raise HTTPException(status_code=404, detail="No HTML files found in template.")
    return html_files[0]


def _sanitize_html_for_bootstrap_only(html: str) -> str:
    """Strip non-Bootstrap CSS/JS links and ensure local bootstrap assets are referenced."""
    import re

    # remove link tags that do not mention bootstrap
    def strip_non_bootstrap(match):
        tag = match.group(0)
        if "bootstrap" not in tag.lower():
            return ""
        return tag

    html = re.sub(r"<link[^>]*rel=[\"']stylesheet[\"'][^>]*>", strip_non_bootstrap, html, flags=re.IGNORECASE)

    # remove script tags that do not mention bootstrap
    def strip_non_bootstrap_script(match):
        tag = match.group(0)
        if "bootstrap" not in tag.lower():
            return ""
        return tag

    html = re.sub(r"<script[^>]*></script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<script[^>]*>.*?</script>", strip_non_bootstrap_script, html, flags=re.IGNORECASE | re.DOTALL)

    # enforce local bootstrap asset references
    if "bootstrap.min.css" not in html:
        html = html.replace("</head>", '  <link rel="stylesheet" href="static/bootstrap.min.css">\n</head>')
    else:
        html = re.sub(r'href=["\'][^"\']*bootstrap[^"\']*\.css["\']', 'href="static/bootstrap.min.css"', html, flags=re.IGNORECASE)

    if "bootstrap.bundle.min.js" not in html:
        html = html.replace("</body>", '  <script src="static/bootstrap.bundle.min.js"></script>\n</body>')
    else:
        html = re.sub(r'src=["\'][^"\']*bootstrap[^"\']*bundle[^"\']*\.js["\']', 'src="static/bootstrap.bundle.min.js"', html, flags=re.IGNORECASE)

    return html


def _generate_html_only(prompt: str) -> str:
    template_name, template_root = _pick_template(prompt)
    main_html_path = _find_main_html(template_root)
    raw_html = main_html_path.read_text(encoding="utf-8", errors="ignore")
    sanitized_html = _sanitize_html_for_bootstrap_only(raw_html)

    # ensure site/static/bootstrap assets exist
    _copy_bootstrap_to_site()

    target = SITE_OUTPUT_DIR / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(sanitized_html, encoding="utf-8")
    return f"HTML-only build created from template '{template_name}' using {main_html_path.name}"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    """Redirect to the prompt builder for the default landing experience."""
    return RedirectResponse(url="/prompt-builder", status_code=307)


@app.get("/prompt-builder")
async def prompt_builder():
    """Serve the survey-driven prompt builder page."""
    page_path = SITE_DIR / "prompt-builder.html"
    if not page_path.exists():
        raise HTTPException(status_code=404, detail="prompt-builder.html not found")
    return FileResponse(str(page_path), media_type="text/html")


@app.get("/prompt-builder.html")
async def prompt_builder_html():
    """Alias for prompt builder with .html suffix."""
    return await prompt_builder()


@app.get("/builder")
async def builder():
    """Explicit route for the original builder UI."""
    index_path = SITE_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(str(index_path), media_type="text/html")


@app.get("/builder.html")
async def builder_html():
    """Alias to serve the builder UI with .html suffix."""
    return await builder()


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
        if req.mode == "html-only":
            message = _generate_html_only(req.prompt)
            RUN_MESSAGES[run_id] = [
                {"role": "user", "content": req.prompt},
                {"role": "assistant", "content": message},
            ]
        else:
            message = await _run_builder(req, run_id)
            _copy_bootstrap_to_site()
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
