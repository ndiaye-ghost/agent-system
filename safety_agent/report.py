"""Markdown report and CSV export of AI proposals."""
from __future__ import annotations

import csv
import datetime as dt
from collections import Counter
from pathlib import Path

from .checks.fmea import row_ap, traceability_matrix
from .models import Finding, Level, Project, Proposal

DISCLAIMER = (
    "> **Avertissement.** Les éléments marqués « IA » sont des propositions produites par un modèle de langage. "
    "Ils ne constituent pas une preuve de conformité ISO 26262 et doivent être revus et validés par un "
    "ingénieur sûreté de fonctionnement avant toute prise en compte."
)


def _esc(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def markdown_report(project: Project, findings: list[Finding], proposals: list[Proposal] | None = None,
                    title: str = "Rapport d'analyse sûreté de fonctionnement") -> str:
    proposals = proposals or []
    count = Counter(f.level for f in findings)
    ap_count = Counter(row_ap(r) or "?" for r in project.fmea.values())
    lines = [
        f"# {title}", "",
        f"Généré le {dt.datetime.now():%Y-%m-%d %H:%M} par safety-agent.", "",
        DISCLAIMER, "",
        "## Synthèse", "",
        "| Indicateur | Valeur |", "|---|---|",
        f"| Exigences | {len(project.requirements)} |",
        f"| Lignes AMDEC | {len(project.fmea)} |",
        f"| Priorité d'action H / M / L | {ap_count['H']} / {ap_count['M']} / {ap_count['L']} |",
        f"| Erreurs | {count[Level.ERROR]} |",
        f"| Avertissements | {count[Level.WARNING]} |",
        f"| Informations | {count[Level.INFO]} |",
        f"| Propositions IA à valider | {len(proposals)} |",
        "",
    ]
    for level in (Level.ERROR, Level.WARNING, Level.INFO):
        group = [f for f in findings if f.level == level]
        if not group:
            continue
        lines += [f"## {level.label} ({len(group)})", "", "| Code | Élément | Constat | Source |", "|---|---|---|---|"]
        lines += [f"| {f.code} | {_esc(f.target)} | {_esc(f.message)} | {f.source} |" for f in group]
        lines.append("")

    matrix = traceability_matrix(project)
    if matrix:
        lines += ["## Matrice de traçabilité", "",
                  "| Objectif de sécurité | ASIL | Exigences dérivées | Lignes AMDEC |", "|---|---|---|---|"]
        lines += [f"| {m['safety_goal']} | {m['asil']} | {', '.join(m['requirements']) or '—'} | "
                  f"{', '.join(m['fmea_rows']) or '**aucune**'} |" for m in matrix]
        lines.append("")

    if proposals:
        lines += ["## Propositions IA à valider", "", "| Type | Cible | Proposition | Justification | Statut |",
                  "|---|---|---|---|---|"]
        lines += [f"| {p.kind} | {_esc(p.target)} | {_esc(p.content)} | {_esc(p.rationale)} | {p.status} |"
                  for p in proposals]
        lines.append("")
    return "\n".join(lines)


def write_proposals_csv(proposals: list[Proposal], path: str | Path) -> None:
    """Failure-mode proposals export in FMEA column order, so they can be pasted after review."""
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Élément", "Mode de défaillance", "Mot-guide", "Effet", "Cause", "S", "O", "D",
                    "Prévention", "Mesures de détection", "Justification", "Statut"])
        for p in proposals:
            d = p.data
            w.writerow([p.target, d.get("mode", p.content), d.get("mot_guide", ""), d.get("effet", ""),
                        d.get("cause", ""), d.get("S", ""), d.get("O", ""), d.get("D", ""),
                        d.get("prevention", ""), d.get("detection", ""), p.rationale, f"PROPOSITION IA - {p.status}"])
