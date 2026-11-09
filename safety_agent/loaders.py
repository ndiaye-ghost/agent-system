"""Load requirements and FMEA from CSV (`,` or `;`) or Excel (.xlsx).

Column names are matched loosely (case, accents, FR/EN aliases), so exports
from Excel, DOORS, Polarion or APIS IQ usually load without edits.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path

from .models import Finding, FmeaRow, Level, Project, Requirement

REQ_COLUMNS = {
    "id": ["id", "identifiant", "ref", "reference", "req id", "requirement id"],
    "text": ["text", "texte", "description", "exigence", "requirement", "libelle"],
    "level": ["level", "niveau", "type", "categorie"],
    "asil_raw": ["asil", "niveau asil", "integrity"],
    "parent_ids": ["parent", "parents", "parent id", "parent ids", "derive de", "derived from", "satisfies"],
    "verification": ["verification", "methode de verification", "verification method", "methode"],
    "status": ["status", "statut", "etat"],
}

FMEA_COLUMNS = {
    "id": ["id", "identifiant", "ref", "n", "no", "numero"],
    "item": ["item", "element", "composant", "component", "systeme", "structure"],
    "function": ["function", "fonction"],
    "failure_mode": ["failure mode", "mode de defaillance", "defaillance", "mode"],
    "effect": ["effect", "effet", "effets", "fe", "failure effect", "effet de la defaillance"],
    "cause": ["cause", "causes", "fc", "failure cause", "cause de la defaillance"],
    "severity": ["s", "severity", "gravite", "severite", "g"],
    "occurrence": ["o", "occurrence", "frequence", "f"],
    "detection": ["d", "detection", "detectabilite", "non detection", "n"],
    "prevention_controls": ["prevention", "prevention controls", "mesures de prevention", "pc"],
    "detection_controls": ["detection controls", "mesures de detection", "dc", "controles de detection"],
    "actions": ["actions", "action", "actions recommandees", "recommended actions", "plan d'action"],
    "requirement_ids": ["requirements", "exigences", "req", "req ids", "exigences liees", "linked requirements"],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[_\-./]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _split_ids(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;,\n|]+", raw or "") if p.strip()]


def _read_rows(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook  # optional dependency

        ws = load_workbook(path, read_only=True, data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(h or "") for h in rows[0]]
        return [
            {header[i]: ("" if v is None else str(v)) for i, v in enumerate(r) if i < len(header)}
            for r in rows[1:]
            if any(v not in (None, "") for v in r)
        ]
    text = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    except (csv.Error, IndexError):
        dialect = csv.excel
    return [r for r in csv.DictReader(io.StringIO(text), dialect=dialect) if any((v or "").strip() for v in r.values())]


def _map_header(header: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    """Return {field_name: source_column}. Exact alias match wins over prefix match."""
    normed = {_norm(h): h for h in header if h}
    mapping: dict[str, str] = {}
    for fname, names in aliases.items():
        for alias in names:
            if alias in normed and normed[alias] not in mapping.values():
                mapping[fname] = normed[alias]
                break
    return mapping


def _rating(raw: str, row_id: str, name: str, findings: list[Finding]) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        value = int(float(raw.replace(",", ".")))
    except ValueError:
        findings.append(Finding("FMEA-000", Level.ERROR, row_id, f"Cotation {name} illisible : {raw!r}."))
        return None
    if not 1 <= value <= 10:
        findings.append(Finding("FMEA-000", Level.ERROR, row_id, f"Cotation {name}={value} hors de l'échelle 1-10."))
        return None
    return value


def load_requirements(path: str | Path) -> tuple[dict[str, Requirement], list[Finding]]:
    rows = _read_rows(Path(path))
    findings: list[Finding] = []
    if not rows:
        return {}, findings
    cols = _map_header(list(rows[0].keys()), REQ_COLUMNS)
    if "id" not in cols or "text" not in cols:
        raise ValueError(f"{path}: colonnes 'id' et 'texte' introuvables (en-têtes : {list(rows[0].keys())})")
    reqs: dict[str, Requirement] = {}
    for row in rows:
        get = lambda f: (row.get(cols[f]) or "").strip() if f in cols else ""  # noqa: E731
        rid = get("id")
        if not rid:
            continue
        if rid in reqs:
            findings.append(Finding("REQ-000", Level.ERROR, rid, "Identifiant d'exigence en double."))
            continue
        reqs[rid] = Requirement(
            id=rid,
            text=get("text"),
            level=get("level"),
            asil_raw=get("asil_raw"),
            parent_ids=_split_ids(get("parent_ids")),
            verification=get("verification"),
            status=get("status"),
        )
    return reqs, findings


def load_fmea(path: str | Path) -> tuple[dict[str, FmeaRow], list[Finding]]:
    rows = _read_rows(Path(path))
    findings: list[Finding] = []
    if not rows:
        return {}, findings
    cols = _map_header(list(rows[0].keys()), FMEA_COLUMNS)
    if "failure_mode" not in cols:
        raise ValueError(f"{path}: colonne 'mode de défaillance' introuvable (en-têtes : {list(rows[0].keys())})")
    fmea: dict[str, FmeaRow] = {}
    for n, row in enumerate(rows, start=1):
        get = lambda f: (row.get(cols[f]) or "").strip() if f in cols else ""  # noqa: E731
        fid = get("id") or f"L{n}"
        if fid in fmea:
            findings.append(Finding("FMEA-000", Level.ERROR, fid, "Identifiant de ligne AMDEC en double."))
            continue
        fmea[fid] = FmeaRow(
            id=fid,
            item=get("item"),
            function=get("function"),
            failure_mode=get("failure_mode"),
            effect=get("effect"),
            cause=get("cause"),
            severity=_rating(get("severity"), fid, "S", findings),
            occurrence=_rating(get("occurrence"), fid, "O", findings),
            detection=_rating(get("detection"), fid, "D", findings),
            prevention_controls=get("prevention_controls"),
            detection_controls=get("detection_controls"),
            actions=get("actions"),
            requirement_ids=_split_ids(get("requirement_ids")),
        )
    return fmea, findings


def load_project(reqs_path: str | Path | None, fmea_path: str | Path | None) -> tuple[Project, list[Finding]]:
    project, findings = Project(), []
    if reqs_path:
        project.requirements, f = load_requirements(reqs_path)
        findings += f
    if fmea_path:
        project.fmea, f = load_fmea(fmea_path)
        findings += f
    return project, findings
