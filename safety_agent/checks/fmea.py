"""Deterministic checks on the FMEA and on FMEA <-> requirements traceability."""
from __future__ import annotations

from ..models import Finding, FmeaRow, Level, Project
from .action_priority import action_priority


def row_ap(row: FmeaRow) -> str | None:
    if None in (row.severity, row.occurrence, row.detection):
        return None
    return action_priority(row.severity, row.occurrence, row.detection)


def check_fmea(project: Project) -> list[Finding]:
    out: list[Finding] = []
    reqs = project.requirements
    for row in project.fmea.values():
        for name, value in (("S", row.severity), ("O", row.occurrence), ("D", row.detection)):
            if value is None:
                out.append(Finding("FMEA-001", Level.ERROR, row.id, f"Cotation {name} manquante."))
        if not row.failure_mode:
            out.append(Finding("FMEA-002", Level.ERROR, row.id, "Mode de défaillance non renseigné."))
        if not row.effect:
            out.append(Finding("FMEA-003", Level.WARNING, row.id, "Effet de la défaillance non renseigné."))
        if not row.cause:
            out.append(Finding("FMEA-004", Level.WARNING, row.id, "Cause de la défaillance non renseignée."))
        if not row.prevention_controls and not row.detection_controls:
            out.append(Finding("FMEA-005", Level.WARNING, row.id, "Aucune mesure de prévention ni de détection."))

        ap = row_ap(row)
        if ap == "H" and not row.actions:
            out.append(Finding("FMEA-010", Level.ERROR, row.id,
                               "Priorité d'action H sans action définie (action ou justification obligatoire)."))
        elif ap == "M" and not row.actions:
            out.append(Finding("FMEA-011", Level.WARNING, row.id,
                               "Priorité d'action M sans action ni justification."))
        if row.detection == 10 and row.severity and row.severity >= 9:
            out.append(Finding("FMEA-012", Level.WARNING, row.id,
                               "Défaillance critique (S≥9) sans aucun moyen de détection (D=10)."))

        unknown = [rid for rid in row.requirement_ids if rid not in reqs]
        known = [reqs[rid] for rid in row.requirement_ids if rid in reqs]
        if reqs and unknown:
            out.append(Finding("FMEA-020", Level.ERROR, row.id, f"Exigence(s) liée(s) inconnue(s) : {', '.join(unknown)}."))
        if reqs and row.severity and row.severity >= 9 and not known:
            out.append(Finding("FMEA-021", Level.ERROR, row.id,
                               "Effet critique pour la sécurité (S≥9) sans exigence de sécurité tracée."))
        if row.severity and row.severity >= 9 and known and all(r.asil and r.asil.level == "QM" for r in known):
            out.append(Finding("FMEA-022", Level.WARNING, row.id,
                               "Effet critique (S≥9) couvert uniquement par des exigences QM : vérifier la HARA."))
    return out


def check_traceability(project: Project) -> list[Finding]:
    """Every safety goal should be reached by at least one FMEA row (via the requirement tree)."""
    out: list[Finding] = []
    if not project.fmea or not project.requirements:
        return out
    covered: set[str] = set()
    for row in project.fmea.values():
        for rid in row.requirement_ids:
            if rid in project.requirements:
                covered.add(rid)
                covered |= project.ancestors(rid)
    for r in project.requirements.values():
        if r.is_safety_goal and r.id not in covered:
            out.append(Finding("TRA-001", Level.WARNING, r.id,
                               "Objectif de sécurité non couvert par l'AMDEC (aucun mode de défaillance relié)."))
        elif not r.is_safety_goal and not project.children_of(r.id) and r.id not in covered:
            out.append(Finding("TRA-002", Level.INFO, r.id,
                               "Exigence terminale non reliée à un mode de défaillance de l'AMDEC."))
    return out


def traceability_matrix(project: Project) -> list[dict]:
    """One row per safety goal: requirements below it and FMEA rows linked to them."""
    matrix = []
    for sg in (r for r in project.requirements.values() if r.is_safety_goal):
        below = [r.id for r in project.requirements.values() if sg.id in project.ancestors(r.id)]
        rows = sorted({f.id for rid in [sg.id, *below] for f in project.fmea_rows_for(rid)})
        matrix.append({"safety_goal": sg.id, "asil": str(sg.asil or "?"), "requirements": below, "fmea_rows": rows})
    return matrix
