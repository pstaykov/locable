import os
import re
import json
import os
from pathlib import Path
from .tools import (
    ROOT_DIR,
    write_file,
    read_file,
    list_files,
    load_tools,
    load_system_prompt,
)
from .final_model import FinalModelClient
from ..rag.vectorstore import LocalVectorStore

ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

class BuilderAgent:
    """
    Builder agent that coordinates model calls, message flow, and tool execution.
    Uses retrieval over Bootstrap templates (with descriptions and CSS chunks)
    to ground the model's generations.
    """

    def __init__(self, model=None, host=None):
        model = model or "qwen2.5-coder:14b-instruct"
        host = host or "http://localhost:11434"
        self.model = model
        self.host = host
        self.client = FinalModelClient(model=model, host=host)

        # load tools and system prompt
        self.tools = load_tools()
        self.system_prompt = load_system_prompt()

        # conversation state
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.retrieval_tag = "retrieval"  # track retrieval system messages for pruning

        # retrieval layer
        self.store = LocalVectorStore(
            persist_dir=str(ROOT_DIR / "data" / "chroma"),
            collection_name="bootstrap"
        )

    # -------------------------------------------------------------
    # Tool execution
    # -------------------------------------------------------------
    def execute_tool(self, name, args):
        """
        Execute a declared tool using the existing write_file/read_file/list_files helpers.
        This method forces all writes into site/ for safety, and rewrites Bootstrap CDN paths.
        """

        if name == "write_file":
            path = args.get("path")
            content = args.get("content", "")
            if not path:
                return "ERROR: missing path"

            # normalize path into site/ anchored at package root
            p = Path(path)
            if not p.parts or p.parts[0] != "site":
                p = Path("site") / p
            full = (ROOT_DIR / p).resolve()
            os.makedirs(full.parent, exist_ok=True)

            # rewrite Bootstrap CDN references to local static files
            if full.suffix.lower() == ".html" and isinstance(content, str):
                content = (
                    content.replace(
                        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css",
                        "static/bootstrap.min.css"
                    )
                    .replace(
                        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js",
                        "static/bootstrap.bundle.min.js"
                    )
                )

            return write_file(str(full), content)

        elif name == "read_file":
            return read_file(args.get("path"))

        elif name == "list_files":
            return list_files()

        # unknown tool
        return f"Unknown tool: {name}"

    # -------------------------------------------------------------
    # Retrieval context injection
    # -------------------------------------------------------------
    def _append_retrieval_context(self, user_input, k=5):
        """
        Inject template suggestions (by description distance), CSS samples, and
        component chunks into the conversation to ground generations.
        """

        snippet_parts = []

        # Template suggestions based on description similarity
        try:
            template_hits = self.store.search_templates(user_input, k=3)
        except Exception:
            template_hits = []

        if template_hits:
            snippet_parts.append("--- Template suggestions (by description distance) ---")
            for hit in template_hits:
                dist_val = hit.get("distance")
                dist_txt = f"{dist_val:.3f}" if isinstance(dist_val, (int, float)) else "n/a"
                snippet_parts.append(f"{hit.get('template')}: {hit.get('description')} (dist={dist_txt})")

            # Provide CSS samples from the best match
            top_template = template_hits[0].get("template")
            if top_template:
                try:
                    css_chunks = self.store.fetch_css_chunks(top_template, limit=3)
                except Exception:
                    css_chunks = []
                if css_chunks:
                    snippet_parts.append(f"CSS samples from {top_template} (trimmed):")
                    for i, chunk in enumerate(css_chunks, 1):
                        text = (chunk.get("text") or "")[:420].replace("\n", " ")
                        snippet_parts.append(f"[CSS {i}] {text}")

        # General component chunks
        try:
            hits = self.store.search(user_input, k=k, include_meta=True)
        except Exception:
            hits = None

        if hits:
            docs = (hits.get("documents") or [[]])[0]
            metas = (hits.get("metadatas") or [[]])[0]
            if docs:
                snippet_parts.append("--- Retrieved component chunks ---")
                for i, doc in enumerate(docs[:k]):
                    meta = metas[i] or {}
                    label = meta.get("template") or meta.get("source") or ""
                    snippet_parts.append(f"[{i+1}] {label} :: {doc[:600]}")

        if not snippet_parts:
            return False

        snippet = "\n\n".join(snippet_parts) + "\n"
        # Keep only the latest retrieval context to avoid log bloat.
        self.messages = [
            m for m in self.messages if m.get("name") != self.retrieval_tag
        ]
        self.messages.append(
            {"role": "system", "name": self.retrieval_tag, "content": snippet}
        )
        return True

    # -------------------------------------------------------------
    # Tool-call execution helper
    # -------------------------------------------------------------
    def _exec_tool_call(self, call):
        """
        Execute a single tool call. Accepts any model-produced shape.
        """

        fn = call.get("function") or {}
        tool_name = fn.get("name") or call.get("name")
        raw_args = fn.get("arguments") if fn else call.get("arguments")

        # parse arguments
        if isinstance(raw_args, dict):
            args = raw_args
        else:
            try:
                args = json.loads(raw_args)
            except:
                args = {}

        # execute
        result = self.execute_tool(tool_name, args)

        # append tool message so model sees the result
        self.messages.append({
            "role": "tool",
            "tool_call_id": call.get("id", f"tool_{tool_name}"),
            "name": tool_name,
            "content": json.dumps({"result": result})
        })

    # -------------------------------------------------------------
    # Embedded JSON tool-call detection
    # -------------------------------------------------------------
    def _execute_json_tool_calls(self, assistant_text):
        """
        Extremely robust tool-call extractor.
        Detects model-generated write_file/read_file/list_files calls
        even when the model prints raw dicts, Python-style dicts,
        incomplete JSON, or multiple adjacent objects.
        """
        
        executed = False
        
        # Split by code fences to handle multiple JSON blocks
        blocks = assistant_text.split("```json")

        for block in blocks[1:]:  # Skip first element (text before first ```json)
            # Extract content before closing ```
            if "```" in block:
                json_content = block.split("```", 1)[0].strip()
            else:
                json_content = block.strip()

            if not json_content or '"name"' not in json_content:
                continue

            # Try strict JSON decode first
            try:
                parsed = json.loads(json_content)
            except Exception:
                # Try to convert Python dict into JSON
                try:
                    fixed = json_content.replace("'", '"')
                    parsed = json.loads(fixed)
                except Exception:
                    continue

            # Ensure it's a tool dict
            if not isinstance(parsed, dict):
                continue
            if "name" not in parsed:
                continue

            # Execute the tool
            print(f"\n[Executing tool: {parsed.get('name')}]")
            self._exec_tool_call(parsed)
            executed = True
        
        return executed

    # -------------------------------------------------------------
    # Main interaction
    # -------------------------------------------------------------
    def ask(self, user_input, debug=False):
        """
        Main conversation loop.
        Always expects that the model eventually emits write_file tool calls.
        Handles model output, tool calls, retrieval context injection, and
        stopping condition.
        """

        # append user message
        self.messages.append({"role": "user", "content": user_input})

        # inject retrieval context for grounding (use larger k for more variety)
        self._append_retrieval_context(user_input, k=20)

        loop_guard = 0

        while True:
            loop_guard += 1
            if loop_guard > 12:
                return "Stopped after max iterations."

            # send to model
            resp = self.client.send(self.messages, tools=self.tools, stream=False)

            if debug:
                print("\n[DEBUG] Full API response keys:", list(resp.keys()))
                print(json.dumps(resp, indent=2))

            assistant = resp.get("message", {}) or {}
            content = assistant.get("content", "") or ""

            # show the assistant's content if present
            if content:
                print("\nAssistant:", content)

            # extract tool calls from top-level or nested
            tool_calls = (
                resp.get("tool_calls")
                or assistant.get("tool_calls")
                or resp.get("message", {}).get("tool_calls")
            )

            # tool_calls must be handled robustly
            if tool_calls:
                # normalize tool_calls to a list
                if isinstance(tool_calls, dict):
                    calls = [tool_calls]
                elif isinstance(tool_calls, list):
                    calls = tool_calls
                else:
                    calls = []

                # persist the assistant's tool call message so IDs are preserved
                assistant_msg = {
                    "role": assistant.get("role", "assistant"),
                    "content": content,
                    "tool_calls": calls
                }
                self.messages.append(assistant_msg)

                # execute each tool call
                for call in calls:
                    self._exec_tool_call(call)

                # model must receive the tool results
                continue

            # detect embedded JSON tool-calls inside assistant text
            if content and self._execute_json_tool_calls(content):
                continue

            # no tool calls -> final natural language answer
            print("\n===== FINAL ANSWER =====\n")
            # Persist the assistant reply so future turns retain it.
            self.messages.append({
                "role": assistant.get("role", "assistant"),
                "content": content
            })
            return content


# -------------------------------------------------------------
# Optional CLI launcher
# -------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import textwrap

    def _parse_args():
        parser = argparse.ArgumentParser(
            prog="locable",
            description="Chat with the Locable builder agent to generate sites.",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        parser.add_argument("-m", "--model", help="Override the Ollama model name")
        parser.add_argument("--host", help="Override the Ollama host (ex: http://ollama:11434)")
        parser.add_argument("-d", "--debug", action="store_true", help="Log full model responses")
        return parser.parse_args()

    def _print_banner(agent: BuilderAgent, debug: bool):
        bar = "=" * 68
        print(f"\n{bar}")
        print(" Locable Builder CLI ".center(68))
        print(bar)
        defaults = [
            f"Model: {agent.model}",
            f"Ollama: {agent.host}",
            f"Debug logging: {'on' if debug else 'off'}",
        ]
        print(" | ".join(defaults))
        print("\nType a request (ex: Create a simple landing page)")
        print("Commands: /help to see tips, /quit to exit\n")

    def _print_help():
        print(
            textwrap.dedent(
                """
                Quick commands:
                  /help   show this message
                  /quit   exit the CLI

                Examples:
                  prompt> Build a two-page portfolio with a contact form
                  prompt> Add a CTA section with a button and background image
                """
            ).strip()
        )

    args = _parse_args()
    host = args.host if args.host is not None else ollama_host
    agent = BuilderAgent(model=args.model, host=host)
    _print_banner(agent, args.debug)

    while True:
        try:
            q = input("prompt> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not q:
            continue

        normalized = q.lower()
        if normalized in {"exit", "quit", "/quit", "/q"}:
            print("Goodbye.")
            break
        if normalized in {"help", "/help"}:
            _print_help()
            continue

        result = agent.ask(q, debug=args.debug)
        if result:
            print(f"\nResult: {result}\n")
