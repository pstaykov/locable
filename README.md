# Locable - AI-Powered Website Builder

Locable is a local-first static site builder that pairs an Ollama tool-using model with retrieval over real Bootstrap templates. It suggests a matching template for your description, reuses CSS fragments from that template, and layers new HTML/CSS/JS to fit your request without leaving your machine.

## Why Locable
- Template-aware retrieval over real Bootstrap examples to keep results grounded.
- Tool-calling agent that writes to `site/` only through safe file tools.
- Local-only stack: Ollama + Chroma, no external APIs no monthly subscription.
- Inspectable and editable prompts (`locable/prompts/system_prompt.txt`) and template data (`locable/data/chroma/`).
- open-source - you think something is missing? Commit a pull request! Completely non profit and for free

## How it works (high level)
- You describe the site you want.
- Locable searches the Chroma store for the closest Bootstrap template and CSS snippets.
- The agent reuses that template, adds new HTML/CSS/JS, and writes files under `site/` using only controlled tools.
- Bootstrap assets are copied locally so the output can be opened or hosted as static files.

## Run with Docker (recommended)
Prerequisites: Docker and Docker Compose. For GPU acceleration, enable the NVIDIA container runtime; CPU-only also works.

1. Clone the repo and move into it:
   ```bash
   git clone https://github.com/pstaykov/locable.git
   cd locable
   ```
2. Start the stack:
   ```bash
   docker compose up -d
   ```
   - `ollama` downloads `qwen2.5-coder:14b-instruct` the first time it runs (kept in the `ollama_models` volume).
   - `locable` exposes the API/UI on port `8000`; Ollama listens on `11434`.
3. Open the UI at `http://localhost:8000/prompt-builder` (survey-driven) or `http://localhost:8000/builder` (original builder). API docs are at `API.md`.
4. Stop the stack when you are done:
   ```bash
   docker compose down
   ```

### Common Docker tweaks
- Change the model: edit the `ollama` service command in `docker-compose.yaml` to pull a different model, and set `OLLAMA_HOST` for `locable` if the URL changes.
- CPU-only: remove the `deploy.resources.reservations.devices` block from `docker-compose.yaml`.
- Rebuild locally instead of using the published image:
  ```bash
  docker build -t locable:local .
  docker run --rm -p 8000:8000 -e OLLAMA_HOST=http://host.docker.internal:11434 locable:local
  ```

## API basics
- `POST /generate` with JSON `{ "prompt": "...", "model": "optional", "mode": "full|html-only" }` starts a build and writes files under `site/`.
- `GET /files` lists generated files; `GET /files/{path}` reads a file.
- `GET /messages?run_id=...` streams stored agent messages for a run.
- Health check: `GET /health`.

## Project layout
- `locable/agent/` - builder agents and tools.
- `locable/prompts/` - system and helper prompts.
- `locable/scripts/` - utilities such as template indexing and db inspection.
- `locable/data/` - template embeddings, Chroma storage, and bootstrap assets.
- `locable/site/` - generated static site output.

## License
MIT License.
