"""Deterministic checks on safety requirements (ISO 26262-8 §6, ISO 26262-9 §5)."""
from __future__ import annotations

import re
from collections import defaultdict

from ..models import ASIL_RANK, Asil, Finding, Level, Project

# Words that make a requirement ambiguous or not verifiable (FR + EN).
AMBIGUOUS_TERMS = [
    "rapidement", "rapide", "suffisant", "suffisamment", "approprié", "appropriée", "adéquat", "adéquate",
    "acceptable", "raisonnable", "si possible", "si nécessaire", "le cas échéant", "minimiser", "maximiser",
    "optimiser", "environ", "etc", "convivial", "robuste", "efficace", "normalement", "généralement",
    "quickly", "fast", "sufficient", "appropriate", "adequate", "reasonable", "as soon as possible",
    "if possible", "if necessary", "minimize", "maximize", "optimize", "approximately", "user-friendly",
    "robust", "efficient", "normally", "usually", "and/or", "et/ou",
]
_AMBIGUOUS_RE = re.compile(r"(?<!\w)(" + "|".join(re.escape(t) for t in AMBIGUOUS_TERMS) + r")(?!\w)", re.I)

_SHALL_RE = re.compile(r"\b(doit|doivent|shall|must)\b", re.I)
_TIMING_RE = re.compile(r"\b(délai|temps|durée|réagir|réaction|délais|time|delay|within|react|latence|latency)\b", re.I)
_NUMBER_UNIT_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(ms|s|µs|us|min|h|hz|khz|v|mv|a|ma|°c|%|km/h)\b", re.I)

# ISO 26262-9 §5.4: allowed ASIL decomposition pairs (sorted, highest first).
VALID_DECOMPOSITIONS = {
    "D": [("C", "A"), ("B", "B"), ("D", "QM")],
    "C": [("B", "A"), ("C", "QM")],
    "B": [("A", "A"), ("B", "QM")],
    "A": [("A", "QM")],
}


def check_requirements(project: Project) -> list[Finding]:
    out: list[Finding] = []
    reqs = project.requirements

    for r in reqs.values():
        # --- Attributes
        if not r.asil_raw:
            out.append(Finding("REQ-001", Level.ERROR, r.id, "ASIL non renseigné."))
        elif r.asil is None:
            out.append(Finding("REQ-002", Level.ERROR, r.id, f"ASIL illisible : {r.asil_raw!r}."))
        if not r.is_safety_goal and not r.verification:
            out.append(Finding("REQ-003", Level.WARNING, r.id,
                               "Méthode de vérification non renseignée (ISO 26262-8 §9)."))

        # --- Hierarchy
        if r.is_safety_goal:
            if r.parent_ids:
                out.append(Finding("REQ-010", Level.WARNING, r.id, "Un objectif de sécurité ne devrait pas avoir de parent."))
            if r.asil and r.asil.decomposed_from:
                out.append(Finding("REQ-011", Level.ERROR, r.id, "Un objectif de sécurité ne peut pas être décomposé."))
        elif not r.parent_ids:
            out.append(Finding("REQ-012", Level.ERROR, r.id,
                               "Exigence orpheline : aucun parent (rupture de traçabilité vers un objectif de sécurité)."))
        for pid in r.parent_ids:
            if pid not in reqs:
                out.append(Finding("REQ-013", Level.ERROR, r.id, f"Parent inconnu : {pid}."))
        if r.id in project.ancestors(r.id):
            out.append(Finding("REQ-014", Level.ERROR, r.id, "Cycle dans la hiérarchie des exigences."))

        # --- ASIL inheritance
        if r.asil:
            for pid in r.parent_ids:
                parent = reqs.get(pid)
                if not parent or not parent.asil:
                    continue
                out += _check_inheritance(r.id, r.asil, pid, parent.asil)

        # --- Wording
        text = r.text
        if not text:
            out.append(Finding("REQ-020", Level.ERROR, r.id, "Texte de l'exigence vide."))
            continue
        terms = sorted({m.group(1).lower() for m in _AMBIGUOUS_RE.finditer(text)})
        if terms:
            out.append(Finding("REQ-021", Level.WARNING, r.id,
                               f"Termes ambigus ou non vérifiables : {', '.join(terms)}."))
        shall = len(_SHALL_RE.findall(text))
        if shall == 0:
            out.append(Finding("REQ-022", Level.WARNING, r.id, "Pas de verbe d'obligation (« doit » / « shall »)."))
        elif shall > 1:
            out.append(Finding("REQ-023", Level.WARNING, r.id,
                               f"Exigence non atomique : {shall} verbes d'obligation, à scinder."))
        if _TIMING_RE.search(text) and not _NUMBER_UNIT_RE.search(text):
            out.append(Finding("REQ-024", Level.WARNING, r.id,
                               "Contrainte temporelle sans valeur chiffrée (FTTI / temps de réaction ?)."))

    out += _check_decomposition_pairs(project)
    return out


def _check_inheritance(rid: str, asil: Asil, pid: str, parent_asil: Asil) -> list[Finding]:
    # The ASIL a child must cover is its own, or the original one if decomposed.
    target = parent_asil.decomposed_from or parent_asil.level
    if asil.decomposed_from:
        if asil.decomposed_from != target:
            return [Finding("REQ-030", Level.ERROR, rid,
                            f"Décomposition {asil} incohérente avec l'ASIL du parent {pid} ({parent_asil}).")]
        return []
    if asil.rank < ASIL_RANK[target]:
        return [Finding("REQ-031", Level.ERROR, rid,
                        f"{asil} inférieur à l'ASIL du parent {pid} ({parent_asil}) sans décomposition déclarée.")]
    return []


def _check_decomposition_pairs(project: Project) -> list[Finding]:
    """Children of the same parent decomposed from the same ASIL must form a valid pair."""
    out: list[Finding] = []
    groups: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for r in project.requirements.values():
        if r.asil and r.asil.decomposed_from:
            for pid in r.parent_ids:
                groups[(pid, r.asil.decomposed_from)].append((r.id, r.asil.level))
    for (pid, origin), members in groups.items():
        ids = ", ".join(m[0] for m in members)
        if len(members) != 2:
            out.append(Finding("REQ-032", Level.WARNING, pid,
                               f"Décomposition de l'ASIL {origin} : {len(members)} élément(s) ({ids}), "
                               "une paire est attendue. Vérifier l'argumentaire d'indépendance."))
            continue
        pair = tuple(sorted((m[1] for m in members), key=lambda a: -ASIL_RANK[a]))
        if pair not in VALID_DECOMPOSITIONS.get(origin, []):
            out.append(Finding("REQ-033", Level.ERROR, pid,
                               f"Décomposition invalide ({ids}) : {pair[0]}({origin}) + {pair[1]}({origin}) "
                               f"n'est pas autorisée par l'ISO 26262-9 §5."))
        else:
            out.append(Finding("REQ-034", Level.INFO, pid,
                               f"Décomposition {pair[0]}({origin}) + {pair[1]}({origin}) ({ids}) : "
                               "justifier l'indépendance (analyse des défaillances de cause commune)."))
    return out
