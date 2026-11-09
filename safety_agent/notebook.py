"""Helpers for Jupyter notebooks: DataFrames and LLM selection."""
from __future__ import annotations

import pandas as pd

from .checks.action_priority import rpn
from .checks.fmea import row_ap, traceability_matrix
from .llm import LLMClient, LLMConfig, LLMError
from .models import Finding, Project, Proposal


def requirements_df(project: Project) -> pd.DataFrame:
    return pd.DataFrame([{"ID": r.id, "Niveau": r.level, "ASIL": r.asil_raw, "Texte": r.text,
                          "Parents": ", ".join(r.parent_ids), "Vérification": r.verification, "Statut": r.status}
                         for r in project.requirements.values()])


def fmea_df(project: Project) -> pd.DataFrame:
    rows = []
    for f in project.fmea.values():
        full = None not in (f.severity, f.occurrence, f.detection)
        rows.append({"ID": f.id, "Élément": f.item, "Mode": f.failure_mode, "Effet": f.effect, "Cause": f.cause,
                     "S": f.severity, "O": f.occurrence, "D": f.detection, "AP": row_ap(f),
                     "RPN": rpn(f.severity, f.occurrence, f.detection) if full else None,
                     "Actions": f.actions, "Exigences": ", ".join(f.requirement_ids)})
    return pd.DataFrame(rows)


def findings_df(findings: list[Finding]) -> pd.DataFrame:
    df = pd.DataFrame([f.to_dict() for f in findings], columns=["code", "level", "target", "message", "source"])
    return df.rename(columns={"code": "Code", "level": "Niveau", "target": "Élément", "message": "Constat",
                              "source": "Source"})


def proposals_df(proposals: list[Proposal]) -> pd.DataFrame:
    return pd.DataFrame([p.to_dict() for p in proposals],
                        columns=["kind", "target", "content", "rationale", "status"]).rename(
        columns={"kind": "Type", "target": "Cible", "content": "Proposition", "rationale": "Justification",
                 "status": "Statut"})


def matrix_df(project: Project) -> pd.DataFrame:
    return pd.DataFrame([{"Objectif de sécurité": m["safety_goal"], "ASIL": m["asil"],
                          "Exigences": ", ".join(m["requirements"]), "Lignes AMDEC": ", ".join(m["fmea_rows"]) or "AUCUNE"}
                         for m in traceability_matrix(project)])


def get_llm(base_url: str | None = None, model: str | None = None, demo_if_unreachable: bool = True):
    """Real client if the server answers, otherwise the demo LLM (canned answers)."""
    cfg = LLMConfig()
    if base_url:
        cfg.base_url = base_url
    if model:
        cfg.model = model
    client = LLMClient(cfg)
    try:
        models = client.ping()
        print(f"✅ Serveur LLM joignable : {cfg.base_url}")
        print(f"   Modèles disponibles : {', '.join(models) or 'aucun'}")
        if models and cfg.model not in models:
            print(f"⚠️  Le modèle '{cfg.model}' n'est pas dans la liste. Changez MODEL.")
        return client
    except LLMError as e:
        if not demo_if_unreachable:
            raise
        from .demo import DemoLLM

        print(f"⚠️  {e}")
        print("➡️  MODE DÉMO : réponses simulées, sans IA. Lancez Ollama/vLLM pour de vraies analyses.")
        return DemoLLM()
