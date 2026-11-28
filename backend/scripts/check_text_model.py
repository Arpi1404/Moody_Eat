"""Try the text model settings before putting them on the server.

Usage, from backend/
--------------------
    python -m scripts.check_text_model

Reads TEXT_MODEL_URL, TEXT_MODEL_NAME and TEXT_MODEL_API_KEY from the
environment (or backend/.env), sends one short fixed request the same way the
app does, and prints the text that came back, or the status and the error. The
key is never printed. The request is a real one, so the provider may charge
for it. Exit status: 0 an answer came back, 1 it did not, 2 a setting is
missing.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from config import get_settings  # noqa: E402
from services.place_blurbs_service import (  # noqa: E402
    NARRATIVE_MAX_TOKENS,
    NARRATIVE_TIMEOUT_SECONDS,
    ask_model,
    configured_text_model,
)

_PROMPT = "Write one short sentence that wishes someone a good evening out."

_THINKING_HINT = (
    "A model that thinks first can use up the ceiling before it has finished "
    "answering: it may need a lower thinking setting on the provider's side, "
    "or a lighter model."
)
_HINTS = {
    "http_status": "The provider refused the request. Check the address, the model "
    "name and the key against its documentation. If it says max_tokens is not "
    "supported, this provider or model needs a different name for the token "
    "ceiling, and the app cannot use it as it is.",
    "timeout": "No answer in the time a quest waits. A model this slow would "
    "mostly give fallback text.",
    "request_failed": "The request could not be sent. Check that TEXT_MODEL_URL "
    "is the full address, starting with https://.",
    "not_json": "The answer was not JSON. TEXT_MODEL_URL may point at a web page "
    "instead of the chat-completions endpoint.",
    "empty_answer": "The reply held no text in choices[0].message.content. "
    + _THINKING_HINT,
    "cut_off": "The answer hit the token ceiling, so the app would not use it. "
    + _THINKING_HINT,
}


def main() -> int:
    model = configured_text_model()
    if model is None:
        settings = get_settings()
        missing = [
            name
            for name, value in (
                ("TEXT_MODEL_URL", settings.text_model_url),
                ("TEXT_MODEL_NAME", settings.text_model_name),
                ("TEXT_MODEL_API_KEY", settings.text_model_api_key),
            )
            if not value.strip()
        ]
        print(f"Not configured. Missing: {', '.join(missing)}")
        return 2

    # The same ceiling and time limit as the quest intro, so a model that
    # spends either before answering shows up here too.
    reply = asyncio.run(
        ask_model(model, _PROMPT, NARRATIVE_MAX_TOKENS, NARRATIVE_TIMEOUT_SECONDS)
    )
    if reply.problem is None:
        print(f"OK (HTTP {reply.status}). The model wrote:\n{reply.text}")
        return 0
    status = f"HTTP {reply.status}" if reply.status is not None else "no HTTP status"
    print(f"Failed: {reply.problem} ({status})")
    if reply.detail:
        print(reply.detail)
    print(_HINTS.get(reply.problem, ""))
    return 1


if __name__ == "__main__":
    sys.exit(main())
