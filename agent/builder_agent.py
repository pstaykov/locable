import json
from .agent import write_file, read_file, list_files, load_tools, load_system_prompt
from .final_model import FinalModelClient
from rag.vectorstore import LocalVectorStore


class BuilderAgent:
    """Builder agent that coordinates model calls and local tool execution.

    This agent uses the existing tool implementations found in
    `agent/agent.py` (write_file, read_file, list_files) and the
    `tools.json` metadata loaded by `load_tools()`.
    """

    def __init__(self, model=None, host=None):
        model = model or "qwen2.5-coder:14b-instruct"
        host = host or "http://localhost:11434"
        self.client = FinalModelClient(model=model, host=host)
        self.tools = load_tools()
        self.system_prompt = load_system_prompt()
        self.messages = [{"role": "system", "content": self.system_prompt}]

        # Chroma-backed retriever
        self.store = LocalVectorStore(persist_dir="data/chroma", collection_name="bootstrap")

    def execute_tool(self, name, args):
        if name == "write_file":
            return write_file(args["path"], args["content"])
        elif name == "read_file":
            return read_file(args["path"])
        elif name == "list_files":
            return list_files()
        else:
            return f"Unknown tool: {name}"

    def _append_retrieval_context(self, user_input, k: int = 3):
        try:
            hits = self.store.search(user_input, k)
        except Exception:
            return False

        # LocalVectorStore.search returns a list of documents (compat wrapper).
        # Accept either list-of-strings or dict-like chroma result.
        docs = []
        if isinstance(hits, dict):
            docs = (hits.get("documents") or [[]])[0]
        elif isinstance(hits, list):
            docs = hits
        elif hasattr(hits, "__iter__"):
            try:
                docs = list(hits)
            except Exception:
                docs = []

        if not docs:
            return False

        # include short retrieved context as a system message so the model can reference it
        snippet = "\n\n--- Retrieved documents (top %d) ---\n\n" % k
        for i, d in enumerate(docs[:k]):
            snippet += f"[{i+1}] {d[:1000].replace('\\n',' ')}\n\n"

        self.messages.append({"role": "system", "content": snippet})
        return True

    def _user_confirmed_build(self, last_user: str, assistant_content: str) -> bool:
        if not last_user:
            return False
        lu = last_user.strip().lower()
        if any(tok in lu for tok in ("yes", "y", "do it", "go ahead", "build", "please build")):
            # also check assistant asked a build question
            if assistant_content and "build" in assistant_content.lower():
                return True
        return False

    def _build_website(self) -> str:
        """Simple deterministic website scaffolding using existing write_file tool."""
        # Build index.html using Bootstrap assets if available in data/bootstrap
        # Prefer copying the project's bundled bootstrap files into site/static
        bs_css_src = "data/bootstrap/bootstrap.min.css"
        bs_js_src = "data/bootstrap/bootstrap.bundle.min.js"

        # Default fallback small CSS/JS if bootstrap files are missing
        fallback_css = "body { font-family: Arial, sans-serif; margin:0; padding:0; }\nnav{background:#0a6ea8;color:#fff;padding:1rem}"
        fallback_js = "console.log('Sushi Masterpiece loaded');"

        results = []

        # Copy bootstrap files into site/static if present
        try:
            css_content = read_file(bs_css_src)
            if css_content.startswith("Error: file not found"):
                css_content = fallback_css
                results.append(f"{bs_css_src}: MISSING, using fallback styles")
            else:
                results.append(f"{bs_css_src}: copied to site/static/bootstrap.min.css")
        except Exception as e:
                css_content = fallback_css
                results.append(f"{bs_css_src}: READ ERROR {e}")

        try:
            js_content = read_file(bs_js_src)
            if js_content.startswith("Error: file not found"):
                js_content = fallback_js
                results.append(f"{bs_js_src}: MISSING, using fallback script")
            else:
                results.append(f"{bs_js_src}: copied to site/static/bootstrap.bundle.min.js")
        except Exception as e:
                js_content = fallback_js
                results.append(f"{bs_js_src}: READ ERROR {e}")

        # Minimal custom styles that won't override Bootstrap
        custom_css = "body { padding-top: 60px; } .hero{padding:2rem;}"

        # Use Bootstrap classes in the HTML structure
        index_html = f"""<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
    <title>Sushi Masterpiece</title>
    <link rel=\"stylesheet\" href=\"static/bootstrap.min.css\">
    <link rel=\"stylesheet\" href=\"static/styles.css\">
</head>
<body>
    <nav class=\"navbar navbar-expand-lg navbar-dark bg-primary fixed-top\">
        <div class=\"container-fluid\">
            <a class=\"navbar-brand\" href=\"#\">Sushi Masterpiece</a>
        </div>
    </nav>
    <main class=\"container\">
        <div class=\"py-5 text-center hero\">
            <h1 class=\"display-4\">Sushi Masterpiece</h1>
            <p class=\"lead\">Indulge in the art of Japanese cuisine.</p>
        </div>

        <div class=\"row\">
            <div class=\"col-md-8\">
                <h2>About</h2>
                <p>Welcome to Sushi Masterpiece, where every bite is a piece of art. Our chefs use only the freshest ingredients to create authentic and exquisite sushi dishes.</p>
            </div>
            <div class=\"col-md-4\">
                <h3>Contact</h3>
                <address>
                    123 Sushi Lane<br>
                    Tokyo<br>
                    <a href=\"tel:+81312345678\">+81-3-1234-5678</a><br>
                    <a href=\"mailto:sushi@example.com\">sushi@example.com</a>
                </address>
            </div>
        </div>
    </main>

    <script src=\"static/bootstrap.bundle.min.js\"></script>
    <script src=\"static/script.js\"></script>
</body>
</html>
"""

        # Write files into site/ and site/static
        write_targets = [
                ("site/index.html", index_html),
                ("site/static/bootstrap.min.css", css_content),
                ("site/static/bootstrap.bundle.min.js", js_content),
                ("site/static/styles.css", custom_css),
                ("site/static/script.js", fallback_js),
        ]

        for path, content in write_targets:
            try:
                res = self.execute_tool("write_file", {"path": path, "content": content})
                results.append(f"{path}: {res}")
            except Exception as e:
                results.append(f"{path}: ERROR {e}")

        return "\n".join(results)

    def ask(self, user_input, debug=False):
        # append user message
        self.messages.append({"role": "user", "content": user_input})

        # add retrieval context before calling the model
        try:
            self._append_retrieval_context(user_input, k=3)
        except Exception:
            pass

        loop_guard = 0
        last_assistant_content = ""
        while True:
            loop_guard += 1
            if loop_guard > 8:
                return "Stopped after max iterations."

            # send to model
            resp = self.client.send(self.messages, tools=self.tools, stream=False)

            if debug:
                print("\n[DEBUG] Full API response:")
                print(json.dumps(resp, indent=2))

            assistant = resp.get("message", {})
            content = assistant.get("content", "")
            tool_calls = assistant.get("tool_calls")

            # show assistant content if any (intermediate reasoning)
            if content:
                print(f"\nAssistant: {content}")

            # detect confirmation flow: if assistant asked to build and last user confirmed -> do the build locally
            last_user = ""
            # find last user message
            for m in reversed(self.messages):
                if m.get("role") == "user":
                    last_user = m.get("content", "")
                    break

            if not tool_calls:
                # If assistant asks to build and user confirmed, run build and append tool message then continue loop
                if self._user_confirmed_build(last_user, content):
                    build_result = self._build_website()
                    print("[LOCAL BUILD] Result:\n", build_result)
                    # append a synthetic tool message so model gets context of action
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": "local_build_1",
                        "name": "local_build",
                        "content": json.dumps({"result": build_result})
                    })
                    # also append assistant acknowledgement so model can continue if needed
                    self.messages.append({"role": "assistant", "content": "Build completed locally."})
                    # continue the loop to get final model confirmation/next steps
                    continue

                # otherwise treat as final answer and return content
                print("\n===== FINAL ANSWER =====\n")
                return content

            # otherwise, developer model wants us to run tools
            # append assistant message (so model maintains context)
            self.messages.append({"role": "assistant", **assistant})

            # execute each tool call and append its result as a tool message
            for call in tool_calls:
                # Expecting structure similar to: {"id": ..., "function": {"name":..., "arguments": ...}}
                fn = call.get("function", {})
                tool_name = fn.get("name")
                raw_args = fn.get("arguments")

                # parse arguments robustly
                if isinstance(raw_args, dict):
                    args = raw_args
                else:
                    try:
                        args = json.loads(raw_args)
                    except Exception as e:
                        # on parse error, provide a helpful debug message
                        err_msg = f"ERROR parsing tool arguments for {tool_name}: {e}\nRaw: {raw_args}"
                        print(err_msg)
                        # append a tool message with the error so the model can continue
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "name": tool_name,
                            "content": err_msg,
                        })
                        continue

                print(f"\n[Executing tool: {tool_name} with args {args}]")
                result = self.execute_tool(tool_name, args)
                print(f"Result: {result}")

                # append tool result for the model to consume
                # wrap result as JSON string for clarity
                try:
                    tool_content = json.dumps({"result": result})
                except Exception:
                    tool_content = str(result)

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "name": tool_name,
                    "content": tool_content,
                })


# After agent initialization or at top of `main()` / `run()`:
store = LocalVectorStore(persist_dir="data/chroma", collection_name="bootstrap")
try:
    sample = store.search("container class css", k=3)
    print("[RETRIEVAL DEBUG] sample search results:", sample)
except Exception as e:
    print("[RETRIEVAL DEBUG] failed search:", e)

if __name__ == "__main__":
    agent = BuilderAgent()
    print("Builder Agent CLI")
    print("Type a request (ex: 'Create a simple landing page')")
    while True:
        q = input("You: ")
        agent.ask(q, debug=True)
