"""Company look: accent colour and logo.

- Colour: change ACCENT_DEFAULT below, or set the SAFETY_AGENT_COULEUR variable (e.g. "#e2001a").
- Logo: put the company logo in the project's assets/ folder as logo.png, logo.svg or logo.jpg,
  or set SAFETY_AGENT_LOGO to the path of the file.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ACCENT_DEFAULT = "#c8102e"  # red; replace with the exact code from the company style guide
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def accent() -> str:
    value = os.getenv("SAFETY_AGENT_COULEUR", ACCENT_DEFAULT).strip()
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else ACCENT_DEFAULT


def tint(hex_color: str, amount: float) -> str:
    """Mix the colour with white (amount 0 = colour, 1 = white), for light backgrounds."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    mix = lambda c: round(c + (255 - c) * amount)  # noqa: E731
    return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"


def logo_path() -> Path | None:
    custom = os.getenv("SAFETY_AGENT_LOGO", "")
    if custom and Path(custom).is_file():
        return Path(custom)
    for name in ("logo.png", "logo.svg", "logo.jpg", "logo.jpeg"):
        if (ASSETS / name).is_file():
            return ASSETS / name
    return None
