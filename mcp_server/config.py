"""Environment loading shared by every entry point.

The README tells people to copy `.env.example` to `.env`, so every entry point has
to actually read it. Kept in one place so a new entry point cannot forget.
"""

from __future__ import annotations

import sys

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - .env is optional
    load_dotenv = None  # type: ignore[assignment]


def load_env() -> None:
    """Load `.env` from the working directory if python-dotenv is available."""
    if load_dotenv is not None:
        load_dotenv()


def prepare_console() -> None:
    """Make stdout forgiving before printing anything.

    Windows consoles default to a legacy code page (cp932 on the machine this was
    built on). Tool results legitimately contain currency symbols such as the yen
    sign, and a `UnicodeEncodeError` inside a print call would kill the process.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - not fatal
        pass


def bootstrap() -> None:
    """What every entry point needs: config, plus a console that cannot crash."""
    load_env()
    prepare_console()
