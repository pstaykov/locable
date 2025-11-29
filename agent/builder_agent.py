import re
import json
import os
from pathlib import Path
from .tools import write_file, read_file, list_files, load_tools, load_system_prompt
from .final_model import FinalModelClient
from ..rag.vectorstore import LocalVectorStore


class BuilderAgent:
    """
    Builder agent that coordinates model calls, message flow, and tool execution.
    This version removes the fallback scaffold and enforces model-directed building.
    Phase 1 (information gathering) is still supported.
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

        if name == "write_file":
            path = args.get("path")
            content = args.get("content", "")
            if not path:
                return "ERROR: missing path"

            # normalize path into site/
            p = Path(path)
            if not p.parts or p.parts[0] != "site":
                p = Path("site") / p
            full = p.resolve()
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
        Perform Bootstrap-component retrieval using the local vector store and
        inject results as a system message. This improves model grounding.
        """

        try:
            hits = self.store.search(user_input, k)
        except Exception:
            return False

        # normalize retrieved docs
        if isinstance(hits, dict):
            docs = (hits.get("documents") or [[]])[0]
        elif isinstance(hits, list):
            docs = hits
        else:
            try:
                docs = list(hits)
            except:
                docs = []

        if not docs:
            return False

        snippet = "\n\n--- Retrieved Bootstrap context ---\n\n"
        for i, d in enumerate(docs[:k]):
            snippet += f"[{i+1}] {d[:1500].replace('\\n',' ')}\n\n"

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
                json_content = block.split("```")[0].strip()
            else:
                json_content = block.strip()
            
            if not json_content or '"name"' not in json_content:
                continue
            
            # Try strict JSON decode first
            try:
                parsed = json.loads(json_content)
            except Exception:
                # Try to convert Python dict → JSON
                try:
                    fixed = json_content.replace("'", "\"")
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

        # inject retrieval context for grounding
        self._append_retrieval_context(user_input, k=5)

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
