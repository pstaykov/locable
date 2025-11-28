import os
import json
import requests


# ---------------------------------------------------------
# Load tools.json
# ---------------------------------------------------------
def load_tools():
    with open("tools.json", "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------
def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True) if "/" in path else None
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"File written: {path}"


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: file not found: {path}"


def list_files():
    files = []
    for root, dirs, filenames in os.walk("."):
        for name in filenames:
            files.append(os.path.join(root, name))
    return json.dumps(files, indent=2)

def load_system_prompt():
    with open("prompts/system_prompt.txt", "r", encoding="utf-8") as f:
        return f.read()

# ---------------------------------------------------------
# Agent Class
# ---------------------------------------------------------
class WebsiteBuilderAgent:
    def __init__(self, model="qwen2.5-coder:14b-instruct", host="http://localhost:11434"):
        self.model = model
        self.url = f"{host}/api/chat"
        self.tools = load_tools()
        self.messages = []

        # Basic system prompt — you can extend later
        self.system_prompt = load_system_prompt()


    # Map tool name to function
    def execute_tool(self, name, args):
        if name == "write_file":
            return write_file(args["path"], args["content"])
        elif name == "read_file":
            return read_file(args["path"])
        elif name == "list_files":
            return list_files()
        return f"Unknown tool: {name}"

    # Main call
    def ask(self, user_input):
        # Only include system prompt once
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})

        # Add user's new message
        self.messages.append({"role": "user", "content": user_input})

        while True:

            payload = {
                "model": self.model,
                "messages": self.messages,
                "tools": self.tools,
                "stream": False
            }

            response = requests.post(self.url, json=payload)
            data = response.json()
            
            # Debug: Print full response
            print(f"\n[DEBUG] Full API response: {json.dumps(data, indent=2)}")
            
            assistant = data.get("message", {})
            
            print(f"\n[DEBUG] Assistant object: {json.dumps(assistant, indent=2)}")

            tool_calls = assistant.get("tool_calls", None)
            content = assistant.get("content", "")
            
            print(f"\n[DEBUG] tool_calls: {tool_calls}")
            print(f"[DEBUG] content: {content}")

            # Print any content from the assistant
            if content:
                print(f"\nAssistant: {content}")

            # No tool call → final message
            if not tool_calls:
                print("\n===== FINAL ANSWER =====\n")
                return content

            # Otherwise, execute tools
            self.messages.append({"role": "assistant", **assistant})

            for call in tool_calls:
                tool_name = call["function"]["name"]
                raw_args = call["function"]["arguments"]

                # DEBUG PRINT
                print("\n[DEBUG] Raw arguments from model:", raw_args)

                # Robust argument parsing
                if isinstance(raw_args, dict):
                    args = raw_args
                else:
                    try:
                        args = json.loads(raw_args)
                    except Exception as e:
                        print("\n!!! JSON PARSE ERROR !!!")
                        print("Model gave:", raw_args)
                        print("Error:", e)
                        return

                print(f"\n[Executing tool: {tool_name} with args {args}]")        
                result = self.execute_tool(tool_name, args)

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": tool_name,
                    "content": json.dumps({"result": result})
                })



# ---------------------------------------------------------
# Command Line Interface
# ---------------------------------------------------------
if __name__ == "__main__":
    agent = WebsiteBuilderAgent()

    print("Local Website Builder Agent (DeepSeek + Ollama)")
    print("Type your request (e.g. 'Create a portfolio landing page'): \n")

    while True:
        user_query = input("You: ")
        agent.ask(user_query)
