import json
from pathlib import Path
from typing import List

# Project root (locable/)
ROOT_DIR = Path(__file__).resolve().parent.parent


def _resolve_path(path: str) -> Path:
    """Return an absolute path anchored at the project root."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    resolved = candidate.resolve()
    # Prevent escaping the repository root
    try:
        resolved.relative_to(ROOT_DIR)
    except ValueError:
        raise ValueError(f"Path outside project root: {resolved}")
    return resolved


def write_file(path: str, content: str) -> str:
    """Write text content to a file, creating parent folders as needed."""
    target = _resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "" if content is None else str(content)
    target.write_text(text, encoding="utf-8")
    return f"Wrote {target} ({len(text.encode('utf-8'))} bytes)"


def read_file(path: str) -> str:
    """Read and return file contents, or an error string if missing."""
    target = _resolve_path(path)
    if not target.exists():
        return f"ERROR: file not found: {target}"
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return target.read_bytes().decode("utf-8", errors="replace")


def list_files(base: str = ".") -> List[str]:
    """List files under `base`, returned as paths relative to the project root."""
    root = _resolve_path(base)
    if not root.exists():
        return []
    files: List[str] = []
    for file in root.rglob("*"):
        if file.is_file():
            try:
                rel = file.relative_to(ROOT_DIR)
            except ValueError:
                # Skip anything outside the project root just in case
                continue
            files.append(str(rel))
    return files


def load_tools(tools_path: str | Path | None = None):
    """Load the tool JSON schema used for LLM tool calling."""
    path = _resolve_path(tools_path or (ROOT_DIR / "agent" / "tools.json"))
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_system_prompt(prompt_path: str | Path | None = None) -> str:
    """Load the system prompt that instructs the builder agent."""
    path = _resolve_path(prompt_path or (ROOT_DIR / "prompts" / "system_prompt.txt"))
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "You are a website builder agent. The system prompt file was not found."
