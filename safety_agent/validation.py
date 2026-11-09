"""Decision journal: who accepted or rejected which AI proposal, and when.

One CSV file, appended only (never rewritten), readable in Excel. When the web
page is shared, all colleagues write to the same journal on the host machine.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os
import threading
from pathlib import Path

from .models import Proposal

COLUMNS = ["horodatage", "utilisateur", "decision", "type", "cible", "proposition", "justification",
           "sources", "commentaire", "modele", "id_proposition"]
ACCEPTED, REJECTED = "VALIDÉE", "REJETÉE"
_LOCK = threading.Lock()  # the web server handles users in threads of one process


def journal_path() -> Path:
    return Path(os.getenv("SAFETY_AGENT_JOURNAL", "journal_validations.csv"))


def proposal_id(p: Proposal) -> str:
    return hashlib.sha1(f"{p.kind}|{p.target}|{p.content}".encode()).hexdigest()[:12]


def record_decision(p: Proposal, decision: str, user: str, comment: str = "", model: str = "",
                    path: str | Path | None = None) -> dict:
    if decision not in (ACCEPTED, REJECTED):
        raise ValueError(f"Décision inconnue : {decision}")
    if not user.strip():
        raise ValueError("Le nom de l'utilisateur est obligatoire pour la traçabilité.")
    row = {
        "horodatage": dt.datetime.now().isoformat(timespec="seconds"),
        "utilisateur": user.strip(),
        "decision": decision,
        "type": p.kind,
        "cible": p.target,
        "proposition": p.content,
        "justification": p.rationale,
        "sources": " ; ".join(p.data.get("sources", [])),
        "commentaire": comment.strip(),
        "modele": model,
        "id_proposition": proposal_id(p),
    }
    path = Path(path) if path else journal_path()
    with _LOCK:
        new = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
            if new:
                w.writeheader()
            w.writerow(row)
    p.status = decision
    return row


def read_journal(path: str | Path | None = None) -> list[dict]:
    path = Path(path) if path else journal_path()
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))
