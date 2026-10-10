import json
import os

import requests

# where Ollama runs (set OLLAMA_URL when it is on another machine or in Docker)
OLLAMA_BASE = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")

# the two models the app uses
NEEDED_MODELS = ("qwen2.5:7b", "llama3.2:3b")


def ollama_status(needed=NEEDED_MODELS, timeout=1.5):
    """{'state': 'ready' | 'offline' | 'missing', 'missing': [models]}"""

    try:
        reply = requests.get(OLLAMA_BASE + "/api/tags", timeout=timeout)
        reply.raise_for_status()
        names = [m.get("name", "") for m in reply.json().get("models", [])]
    except Exception:
        return {"state": "offline", "missing": list(needed)}

    missing = [m for m in needed if not any(n == m or n.startswith(m) for n in names)]

    return {"state": "missing" if missing else "ready", "missing": missing}


class LLMClient:

    def __init__(self, model="qwen2.5:7b", timeout=180):

        self.url = OLLAMA_BASE + "/api/generate"
        self.model = model
        self.timeout = timeout

    def generate(self, prompt, json_mode=True, max_tokens=None):

        text = ""

        # Try up to 2 times (1 retry if the answer is not valid JSON)
        for attempt in range(2):

            text = self._ask_ollama(prompt, json_mode, max_tokens)

            # Normal text answer: no JSON needed
            if not json_mode:
                return text

            parsed = self._extract_json(text)

            if parsed is not None:
                return parsed

        # Still not JSON after retry: return the raw text
        return text

    def _ask_ollama(self, prompt, json_mode, max_tokens=None):

        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Keep the model in memory between questions (no slow reload)
            "keep_alive": "30m",
            "options": {"temperature": 0, "num_ctx": 8192}
        }

        # Stop long answers early (faster)
        if max_tokens is not None:
            body["options"]["num_predict"] = max_tokens

        # Ask Ollama to force valid JSON output
        if json_mode:
            body["format"] = "json"

        try:
            response = requests.post(
                self.url,
                json=body,
                timeout=self.timeout
            )
            response.raise_for_status()

        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Cannot reach Ollama. Open the Ollama app "
                "(or run 'ollama serve') and try again."
            )

        except requests.exceptions.Timeout:
            raise RuntimeError(
                "Ollama took too long to answer. Try again."
            )

        return response.json()["response"].strip()

    def _extract_json(self, text):

        # Best case: the whole text is valid JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Fallback: find the first { and the last }
        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return None