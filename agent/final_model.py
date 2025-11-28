import requests


class FinalModelClient:
    """Simple wrapper around the local model HTTP API.

    send(messages, tools=None, stream=False) -> dict
    returns the parsed JSON response from the API (not just the content field) so
    callers can inspect tool call metadata.
    """

    def __init__(self, model="qwen2.5-coder:14b-instruct", host="http://localhost:11434"):
        self.model = model
        self.url = f"{host}/api/chat"

    def send(self, messages, tools=None, stream=False):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        if tools is not None:
            payload["tools"] = tools

        resp = requests.post(self.url, json=payload)
        resp.raise_for_status()
        return resp.json()
