"""Talks to Groq / OpenRouter (both speak the OpenAI API) and streams the answer."""
import logging

import openai
from openai import OpenAI
from PySide6.QtCore import QThread, Signal

from backend.config import active_provider, get_api_key


def friendly_error(exc: Exception, env_name: str = "the API key") -> str:
    """Turn a technical exception into a message a learner can act on."""
    # Order matters: APITimeoutError is a *kind of* APIConnectionError, so check it first.
    if isinstance(exc, openai.AuthenticationError):
        return "The API key was rejected. Open Settings from the tray menu and paste a valid key."
    if isinstance(exc, openai.PermissionDeniedError):
        return "Your API key is not allowed to use this model. Try another model in Settings."
    if isinstance(exc, openai.RateLimitError):
        return "Rate limit reached. Wait a minute and try again, or switch provider in Settings."
    if isinstance(exc, openai.NotFoundError):
        return "The model was not found. Check the model name in Settings."
    if isinstance(exc, openai.APITimeoutError):
        return "The request timed out. Try again in a moment."
    if isinstance(exc, openai.APIConnectionError):
        return "Could not reach the server. Check your internet connection."
    if isinstance(exc, openai.BadRequestError):
        return f"The service rejected the request: {exc}"
    if isinstance(exc, openai.APIStatusError):
        return f"The service returned an error (HTTP {exc.status_code}). Try again shortly."
    return f"Unexpected error: {exc}"


def stream_completion(provider, api_key, messages, timeout, should_stop=lambda: False):
    """Generator: yields the answer piece by piece as the model produces it."""
    client = OpenAI(
        base_url=provider["base_url"],
        api_key=api_key,
        timeout=timeout,
        max_retries=0,  # we show our own friendly error instead of silently retrying
    )
    stream = client.chat.completions.create(
        model=provider["model"],
        messages=messages,
        stream=True,
    )
    for chunk in stream:
        if should_stop():
            break
        if not chunk.choices:
            continue
        piece = chunk.choices[0].delta.content  # reasoning models also send other fields; we ignore them
        if piece:
            yield piece


class AIWorker(QThread):
    """Runs one streaming request in a background thread.

    Every signal carries `request_id` so the controller can ignore
    answers from a request the user has already replaced.
    """

    token_received = Signal(int, str)
    completed = Signal(int, str)
    failed = Signal(int, str)

    def __init__(self, request_id: int, config: dict, messages: list):
        super().__init__()
        self.request_id = request_id
        self._provider = active_provider(config)
        self._api_key = get_api_key(config)
        self._timeout = float(config.get("timeout_seconds", 60))
        self._messages = messages
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        env_name = self._provider["api_key_env"]
        if not self._api_key:
            self.failed.emit(
                self.request_id,
                "No API key found. Right-click the tray icon, open Settings and paste your key.",
            )
            return
        try:
            pieces = []
            for piece in stream_completion(
                self._provider, self._api_key, self._messages, self._timeout,
                should_stop=lambda: self._cancelled,
            ):
                pieces.append(piece)
                self.token_received.emit(self.request_id, piece)
            if not self._cancelled:
                self.completed.emit(self.request_id, "".join(pieces))
        except Exception as exc:  # never let a thread die silently
            logging.exception("AI request failed")
            self.failed.emit(self.request_id, friendly_error(exc, env_name))


if __name__ == "__main__":
    # Quick self-test:  python -m backend.ai_client "What does enumerate() do in Python?"
    import sys
    from backend.config import load_config

    config = load_config()
    question = " ".join(sys.argv[1:]) or "In one sentence, what is a Python list?"
    key = get_api_key(config)
    if not key:
        raise SystemExit("No API key found. Add one in the app's Settings window.")
    messages = [{"role": "user", "content": question}]
    try:
        for text in stream_completion(active_provider(config), key, messages, 60):
            print(text, end="", flush=True)
        print()
    except Exception as error:
        print("ERROR:", friendly_error(error))