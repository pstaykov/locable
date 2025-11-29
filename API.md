# Locable Builder API

## Overview
FastAPI service that wraps the BuilderAgent so a frontend can trigger website generation and read the generated files. Base URL examples below assume `http://127.0.0.1:8000`.

## Authentication
None (local-only). Ensure the server is not exposed publicly.

## Endpoints

### GET /health
- Purpose: Liveness probe.
- Response: `{ "status": "ok" }`

### POST /generate
- Purpose: Run the builder agent with a natural language prompt.
- Request body:
```json
{
  "prompt": "build a cafe landing page",
  "model": "qwen2.5-coder:14b-instruct",   // optional override
  "host": "http://localhost:11434",        // optional override
  "debug": false                             // optional; logs full agent responses server-side
}
```
- Behavior: Calls the agent, which may iterate tool calls and write files under `site/`.
- Response (200):
```json
{
  "status": "ok",
  "message": "short final summary from the agent",
  "files": [
    "site/index.html",
    "site/static/styles.css",
    "site/static/script.js"
  ]
}
```
- Errors: 500 with `{ "detail": "..." }` if the agent raises.

### GET /files
- Purpose: List generated files under `site/`.
- Response: JSON array of relative paths, e.g. `["site/index.html", "site/static/styles.css"]`.

### GET /files/{path}
- Purpose: Fetch the contents of a generated file.
- Path rule: If `path` does not start with `site/`, it is automatically prefixed with `site/` for safety.
- Response: Plain text of the file contents.
- Errors: 404 with `{ "detail": "ERROR: file not found: ..." }` if missing.

## Example cURL Flow
1) Generate:
```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"build a cafe landing page"}'
```
2) List files:
```bash
curl http://127.0.0.1:8000/files
```
3) Fetch HTML:
```bash
curl http://127.0.0.1:8000/files/site/index.html
```

## Running the API
From the repo root (`C:\code\ML\Locable`):
```bash
uvicorn locable.api:app --reload
```
Ensure your Ollama host is reachable at the configured `host`.
