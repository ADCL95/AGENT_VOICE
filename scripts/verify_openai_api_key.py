"""
Smoke-test OpenAI credentials using the same configuration as the app
(``get_settings()`` → ``local.settings.json`` at repo root).

Usage (from repository root, virtualenv active)::

    python scripts/verify_openai_api_key.py

Exit code 0 if the key works; 1 otherwise. The API key is never printed.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from openai import OpenAI
        from showroom.core.settings import get_settings
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"Import error: {e}", file=sys.stderr)
        print("Activate the project venv and run `pip install -e .` from the repo root.", file=sys.stderr)
        return 1

    settings = get_settings()
    print(settings.openai_api_key)
    client = OpenAI(api_key=settings.openai_api_key)
    try:
        model = client.models.retrieve(settings.model_main)
        print(f"OK: authenticated; model {model.id!r} is reachable.")
        return 0
    except Exception as e:
        print(f"API call failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
