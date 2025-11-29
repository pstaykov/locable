# Locable – AI-Powered Website Builder

Locable is a local-first website builder that pairs an Ollama model with retrieval over real Bootstrap templates. It picks a fitting template by description, reuses its CSS chunks, and layers new styling for your request.

## Features
- Template-aware retrieval: Chroma stores per-template descriptions, HTML chunks, and CSS chunks; the agent suggests templates by semantic distance to the user request.
- Bootstrap-first output: Uses local Bootstrap assets plus template CSS samples, then adds custom CSS for the final site.
- Tool-calling agent: Writes site files via tools only (`site/index.html`, `site/static/styles.css`, `site/static/script.js`).
- Local-only stack: Runs entirely on your machine (Ollama + Chroma), no external APIs.

## Quick Start
1) Install deps  
```bash
pip install -r requirements.txt
```

2) Ensure Ollama is running (default model: `qwen2.5-coder:14b-instruct`, or another tool-calling model).

3) Index templates (one-time, rerun after adding templates)  
```bash
python locable/scripts/build_template_index.py
```

4) Run the builder  
```bash
python -m locable.agent.builder_agent
```

Describe your site; the agent will propose templates, pull CSS chunks from the closest match, and generate `site/index.html`, `site/static/styles.css`, `site/static/script.js`.

## Notes
- System prompt: `locable/prompts/system_prompt.txt`
- Template indexer: `locable/scripts/build_template_index.py`
- Chroma data lives under `locable/data/chroma/` (auto-created)

## License
MIT License.
