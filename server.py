"""
Launcher for the FastAPI agent bridge.

Ensures ``src`` is on ``sys.path`` so ``showroom.presentation.server:app`` resolves.
Run: ``python server.py`` from the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

if __name__ == "__main__":
    uvicorn.run(
        "showroom.presentation.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
