"""Data model: requirements, FMEA rows and findings."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

ASIL_RANK = {"QM": 0, "A": 1, "B": 2, "C": 3, "D": 4}

# Accepts "C", "ASIL C", "ASIL B(D)", "B(D)", "QM", "QM(B)"
_ASIL_RE = re.compile(r"^\s*(?:ASIL\s*)?(QM|[ABCD])\s*(?:\(\s*(?:ASIL\s*)?(QM|[ABCD])\s*\))?\s*$", re.I)


@dataclass(frozen=True)
class Asil:
    """An ASIL, optionally decomposed: ASIL B(D) means 'B, decomposed from D'."""

    level: str
    decomposed_from: str | None = None

    @classmethod
    def parse(cls, raw: str | None) -> "Asil | None":
        if raw is None or not str(raw).strip():
            return None
        m = _ASIL_RE.match(str(raw))
        if not m:
            raise ValueError(f"ASIL invalide : {raw!r}")
        level = m.group(1).upper()
        origin = m.group(2).upper() if m.group(2) else None
        return cls(level, origin)

    @property
    def rank(self) -> int:
        return ASIL_RANK[self.level]

    def __str__(self) -> str:
        base = "QM" if self.level == "QM" else f"ASIL {self.level}"
        return f"{base}({self.decomposed_from})" if self.decomposed_from else base


@dataclass
class Requirement:
    id: str
    text: str
    level: str = ""  # SG, FSR, TSR, HSR, SSR...
    asil_raw: str = ""
    parent_ids: list[str] = field(default_factory=list)
    verification: str = ""
    status: str = ""

    @property
    def asil(self) -> Asil | None:
        try:
            return Asil.parse(self.asil_raw)
        except ValueError:
            return None

    @property
    def is_safety_goal(self) -> bool:
        return self.level.upper() in {"SG", "SAFETY GOAL", "OBJECTIF DE SECURITE"}


@dataclass
class FmeaRow:
    id: str
    item: str = ""
    function: str = ""
    failure_mode: str = ""
    effect: str = ""
    cause: str = ""
    severity: int | None = None
    occurrence: int | None = None
    detection: int | None = None
    prevention_controls: str = ""
    detection_controls: str = ""
    actions: str = ""
    requirement_ids: list[str] = field(default_factory=list)


class Level(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def label(self) -> str:
        return {"error": "ERREUR", "warning": "AVERTISSEMENT", "info": "INFO"}[self.value]


@dataclass
class Finding:
    code: str
    level: Level
    target: str
    message: str
    source: str = "règle"  # "règle" (deterministic) or "IA" (LLM proposal, to be validated)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "level": self.level.value,
            "target": self.target,
            "message": self.message,
            "source": self.source,
        }


@dataclass
class Project:
    requirements: dict[str, Requirement] = field(default_factory=dict)
    fmea: dict[str, FmeaRow] = field(default_factory=dict)

    def children_of(self, req_id: str) -> list[Requirement]:
        return [r for r in self.requirements.values() if req_id in r.parent_ids]

    def fmea_rows_for(self, req_id: str) -> list[FmeaRow]:
        return [f for f in self.fmea.values() if req_id in f.requirement_ids]

    def ancestors(self, req_id: str) -> set[str]:
        """All requirement ids above req_id (cycle-safe)."""
        seen: set[str] = set()
        stack = list(self.requirements[req_id].parent_ids) if req_id in self.requirements else []
        while stack:
            pid = stack.pop()
            if pid in seen or pid not in self.requirements:
                continue
            seen.add(pid)
            stack.extend(self.requirements[pid].parent_ids)
        return seen


@dataclass
class Proposal:
    """A suggestion produced by the AI. Never applied automatically: an engineer must review it."""

    kind: str  # reformulation | mode_de_defaillance | exigence | action | autre
    target: str
    content: str
    rationale: str = ""
    status: str = "À VALIDER"
    data: dict = field(default_factory=dict)  # structured content, e.g. FMEA fields

    def to_dict(self) -> dict:
        return {"kind": self.kind, "target": self.target, "content": self.content,
                "rationale": self.rationale, "status": self.status}
