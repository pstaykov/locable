# Changelog

## v0.1.1
- Fixed assistant replies not being persisted into the conversation log, preventing context loss across turns.
- Limited retrieval context injection to the latest snippet by pruning prior retrieval system messages to reduce log bloat and token churn.
- Added a survey-driven prompt builder UI (frontend) and set it as the default landing page, including a direct `/builder` route for the original interface.
- color/focus fixes 

## v0.1.0
- Added template-aware indexing with per-template descriptions and CSS chunk storage in Chroma (`scripts/build_template_index.py`).
- Updated agents to suggest templates by description distance, surface CSS samples, and still layer custom CSS (`agent/agent.py`, `agent/builder_agent.py`, `rag/vectorstore.py`, `rag/chroma_store.py`).
- Rewrote system prompt to emphasize template grounding and local Bootstrap assets.
- Regenerated Chroma index (`data/chunks/templates.json`) to include template metadata.
