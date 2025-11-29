# Locable — AI-Powered Website Builder

Locable is a local-first website builder that pairs an Ollama tool-using model with retrieval over real Bootstrap templates. It suggests a matching template for your description, reuses CSS fragments from that template, and layers new HTML/CSS/JS to fit your request—all without leaving your machine.

## What It Does
- Template-aware retrieval: Chroma indexes per-template descriptions, HTML chunks, and CSS chunks, then ranks templates by semantic distance to the user prompt.
- Bootstrap-first generation: Uses local Bootstrap assets plus retrieved CSS samples, and only adds custom styling where needed.
- Tool-calling agent workflow: The agent writes and updates site files only through tools (`site/index.html`, `site/static/styles.css`, `site/static/script.js`) and will add extra HTML pages (e.g., `about.html`, `contact.html`, `blog.html`) when you request a multi-page site.
- Local-only stack: Runs entirely on your hardware (Ollama + Chroma); no external APIs or cloud calls.
- Inspectable prompts and data: System prompt lives at `locable/prompts/system_prompt.txt`; template embeddings and metadata live under `locable/data/chroma/`.

## How It Works (High Level)
1. You describe the site you want.
2. The agent queries Chroma for similar templates based on semantic search over stored descriptions and code chunks.
3. It chooses a base template, reuses its Bootstrap/CSS snippets, and generates the final HTML/CSS/JS for `site/`.
4. The resulting static site can be opened locally or served by any static host.

## Requirements
- Python 3.10+ (tested with 3.11)
- Ollama running locally with a tool-capable model (default: `qwen2.5-coder:14b-instruct`)
- Chroma (installed via `requirements.txt`)
- OS: Linux, macOS, or Windows

### Hardware Guidelines
- CPU: Modern 8+ core recommended for faster generation; works on 4 cores with slower throughput.
- GPU: highly recommended; Ollama will use it if available to speed up inference.
- RAM: 16 GB recommended for the default 14B model; 8 GB can work with smaller models or lower concurrency.
- Disk: ~5 GB free for Ollama model files plus room for template data (`locable/data/chroma/`).

## Quick Start
1) Install dependencies:
```bash
pip install -r requirements.txt
```

2) Ensure Ollama is running (default model: `qwen2.5-coder:14b-instruct`, or swap in another compatible model).

3) Index templates (one-time; rerun after adding templates):
```bash
python locable/scripts/build_template_index.py
```

4) Run the builder:
```bash
python -m locable.agent.builder_agent
```

Describe your site; the agent will propose templates, pull CSS chunks from the closest match, and generate `site/index.html`, `site/static/styles.css`, and `site/static/script.js` (plus extra HTML pages when you request a multi-page site).

## Project Layout
- `locable/agent/`: Tool-calling agents and entrypoints (e.g., `builder_agent.py`).
- `locable/prompts/`: System and helper prompts.
- `locable/scripts/`: Utilities such as template indexing.
- `locable/data/`: Template embeddings, Chroma storage, and sample templates.
- `locable/site/`: Generated static site output.

## Notes
- System prompt: `locable/prompts/system_prompt.txt`
- Template indexer: `locable/scripts/build_template_index.py`
- Chroma data path: `locable/data/chroma/` (auto-created)

## License
MIT License.
