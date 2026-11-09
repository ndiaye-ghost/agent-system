"""Action Priority (AP) per the AIAG-VDA FMEA Handbook (2019), Design FMEA table.

Check this table against your company's copy of the handbook before relying on it:
some OEMs use their own variant.
"""
from __future__ import annotations

# For each severity band, then occurrence band: AP for detection bands
# (D 7-10, D 5-6, D 2-4, D 1).
_TABLE = {
    "S9-10": {
        "O8-10": "HHHH",
        "O6-7": "HHHH",
        "O4-5": "HHHM",
        "O2-3": "HMLL",
        "O1": "LLLL",
    },
    "S7-8": {
        "O8-10": "HHHH",
        "O6-7": "HHHM",
        "O4-5": "HMMM",
        "O2-3": "MMLL",
        "O1": "LLLL",
    },
    "S4-6": {
        "O8-10": "HHMM",
        "O6-7": "MMML",
        "O4-5": "MLLL",
        "O2-3": "LLLL",
        "O1": "LLLL",
    },
    "S2-3": {
        "O8-10": "MMLL",
        "O6-7": "LLLL",
        "O4-5": "LLLL",
        "O2-3": "LLLL",
        "O1": "LLLL",
    },
}


def _s_band(s: int) -> str | None:
    if s >= 9:
        return "S9-10"
    if s >= 7:
        return "S7-8"
    if s >= 4:
        return "S4-6"
    if s >= 2:
        return "S2-3"
    return None  # S = 1 -> always L


def _o_band(o: int) -> str:
    if o >= 8:
        return "O8-10"
    if o >= 6:
        return "O6-7"
    if o >= 4:
        return "O4-5"
    if o >= 2:
        return "O2-3"
    return "O1"


def _d_index(d: int) -> int:
    if d >= 7:
        return 0
    if d >= 5:
        return 1
    if d >= 2:
        return 2
    return 3


def action_priority(s: int, o: int, d: int) -> str:
    """Return 'H', 'M' or 'L'."""
    for name, v in (("S", s), ("O", o), ("D", d)):
        if not 1 <= v <= 10:
            raise ValueError(f"{name}={v} hors de l'échelle 1-10")
    band = _s_band(s)
    if band is None:
        return "L"
    return _TABLE[band][_o_band(o)][_d_index(d)]


def rpn(s: int, o: int, d: int) -> int:
    """Legacy Risk Priority Number, for companies still reporting it."""
    return s * o * d
