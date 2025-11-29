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


class BuilderAgent:
    """
    Builder agent that coordinates model calls, message flow, and tool execution.
    Uses retrieval over Bootstrap templates (with descriptions and CSS chunks)
    to ground the model's generations.
    """

    def __init__(self, model=None, host=None):
        model = model or "qwen2.5-coder:14b-instruct"
        host = host or "http://localhost:11434"
        self.client = FinalModelClient(model=model, host=host)

        # load tools and system prompt
        self.tools = load_tools()
        self.system_prompt = load_system_prompt()

        # conversation state
        self.messages = [{"role": "system", "content": self.system_prompt}]

        # retrieval layer
        self.store = LocalVectorStore(
            persist_dir="data/chroma",
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

        print(f"[DEBUG execute_tool] Called with name='{name}'")
        print(f"[DEBUG] args: {args}")

        if name == "write_file":
            path = args.get("path")
            content = args.get("content", "")
            if not path:
                return "ERROR: missing path"

            # normalize path into site/ anchored at package root
            p = Path(path)
            print(f"[DEBUG] Original path: {path}")

            if not p.parts or p.parts[0] != "site":
                p = Path("site") / p

            full = (ROOT_DIR / p).resolve()
            print(f"[DEBUG] Full resolved path: {full}")

            os.makedirs(full.parent, exist_ok=True)
            print(f"[DEBUG] Created directory: {full.parent}")

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

            print(f"[DEBUG] Calling write_file({full}, content_length={len(content)})")
            result = write_file(str(full), content)
            print(f"[DEBUG] write_file returned: {result}")
            return result

        elif name == "read_file":
            result = read_file(args.get("path"))
            print(f"[DEBUG] read_file returned: {result[:100] if result else result}...")
            return result

        elif name == "list_files":
            result = list_files()
            print(f"[DEBUG] list_files returned: {result}")
            return result

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
        except Exception as e:
            print(f"[DEBUG] template search failed: {e}")
            template_hits = []

        if template_hits:
            snippet_parts.append("--- Template suggestions (by description distance) ---")
            for hit in template_hits:
                dist_val = hit.get("distance")
                dist_txt = f"{dist_val:.3f}" if isinstance(dist_val, (int, float)) else "n/a"
                snippet_parts.append(f"{hit.get('template')}: {hit.get('description')} (dist={dist_txt})")

            top_template = template_hits[0].get("template")
            if top_template:
                try:
                    css_chunks = self.store.fetch_css_chunks(top_template, limit=3)
                except Exception as e:
                    print(f"[DEBUG] css fetch failed: {e}")
                    css_chunks = []
                if css_chunks:
                    snippet_parts.append(f"CSS samples from {top_template} (trimmed):")
                    for i, chunk in enumerate(css_chunks, 1):
                        text = (chunk.get("text") or "")[:420].replace("\n", " ")
                        snippet_parts.append(f"[CSS {i}] {text}")

        # General component chunks
        try:
            hits = self.store.search(user_input, k=k, include_meta=True)
        except Exception as e:
            print(f"[DEBUG] search failed: {e}")
            hits = None

        if hits:
            docs = (hits.get("documents") or [[]])[0]
            metas = (hits.get("metadatas") or [[]])[0]
            if docs:
                snippet_parts.append("--- Retrieved component chunks ---")
                for i, doc in enumerate(docs[:k]):
                    meta = metas[i] or {}
                    label = meta.get("template") or meta.get("source") or ""
                    snippet_parts.append(f"[{i+1}] {label} :: {doc[:600].replace('\n', ' ')}")

        if not snippet_parts:
            return False

        snippet = "\n\n".join(snippet_parts) + "\n"
        self.messages.append({"role": "system", "content": snippet})
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

        print(f"[DEBUG _exec_tool_call] tool_name: {tool_name}")
        print(f"[DEBUG] raw_args type: {type(raw_args)}")
        print(f"[DEBUG] raw_args: {raw_args}")

        # parse arguments
        if isinstance(raw_args, dict):
            args = raw_args
        else:
            try:
                args = json.loads(raw_args)
            except Exception as e:
                print(f"[ERROR] Failed to parse arguments: {e}")
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
    # Embedded JSON tool-call detection (FIXED VERSION)
    # -------------------------------------------------------------
    def _execute_json_tool_calls(self, assistant_text):
        """
        Robust tool-call extractor for model-generated JSON blocks.
        Handles multiple ```json blocks in the assistant's response.
        """

        executed = False

        print("[DEBUG _execute_json_tool_calls] Checking for embedded tool calls...")
        
        # Split by ```json markers
        blocks = assistant_text.split("```json")
        print(f"[DEBUG] Found {len(blocks) - 1} potential JSON blocks")

        for i, block in enumerate(blocks[1:], 1):  # Skip first element (text before first ```json)
            # Extract content before closing ```
            if "```" in block:
                json_content = block.split("```", 1)[0].strip()
            else:
                json_content = block.strip()

            print(f"[DEBUG] Block {i} content preview: {json_content[:100]}...")
            
            if not json_content or '"name"' not in json_content:
                print(f"[DEBUG] Block {i} skipped (no 'name' field)")
                continue

            # Try strict JSON decode first
            try:
                parsed = json.loads(json_content)
                print(f"[DEBUG] Block {i} parsed successfully")
            except Exception as e:
                print(f"[DEBUG] Block {i} JSON parse failed: {e}")
                # Try to convert Python dict into JSON
                try:
                    fixed = json_content.replace("'", "\"")
                    parsed = json.loads(fixed)
                    print(f"[DEBUG] Block {i} parsed after quote fix")
                except Exception as e2:
                    print(f"[DEBUG] Block {i} still failed after quote fix: {e2}")
                    continue

            # Ensure it's a tool dict
            if not isinstance(parsed, dict):
                print(f"[DEBUG] Block {i} not a dict")
                continue
            if "name" not in parsed:
                print(f"[DEBUG] Block {i} has no 'name' field")
                continue

            # Execute the tool
            print(f"\n[Executing embedded tool: {parsed.get('name')}]")
            self._exec_tool_call(parsed)
            executed = True

        print(f"\n[DEBUG] Total tools executed from embedded JSON: {executed}")
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
        self._append_retrieval_context(user_input, k=8)

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
                print("\nAssistant:", content[:500])  # Truncate long responses

            # extract tool calls from top-level or nested
            tool_calls = (
                resp.get("tool_calls")
                or assistant.get("tool_calls")
                or resp.get("message", {}).get("tool_calls")
            )

            # tool_calls must be handled robustly
            if tool_calls:
                print(f"\n[DEBUG] Found {len(tool_calls) if isinstance(tool_calls, list) else 1} standard tool calls")
                
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
            if content:
                # Append assistant message FIRST
                self.messages.append({
                    "role": "assistant",
                    "content": content
                })
                
                # Then check for and execute any embedded tool calls
                if self._execute_json_tool_calls(content):
                    print("[DEBUG] Embedded tool calls found and executed, continuing loop...")
                    continue

            # no tool calls -> final natural language answer
            print("\n===== FINAL ANSWER =====\n")
            return content


# -------------------------------------------------------------
# Optional CLI launcher
# -------------------------------------------------------------
if __name__ == "__main__":
    agent = BuilderAgent()
    print("Builder Agent")
    print("Type your request (ex: 'Create a simple landing page')")
    while True:
        q = input("You: ")
        agent.ask(q, debug=True)
