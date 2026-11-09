"""Tool-calling agent over the project data.

The agent has read-only tools plus `record_proposal`. It cannot edit the
requirements or the FMEA: every suggestion lands in a list for human review.
Requires a model with tool calling (Qwen 2.5/3, Llama 3.1+, Mistral Small/Nemo...).
"""
from __future__ import annotations

import json
from typing import Callable

from .checks import run_all_checks
from .checks.action_priority import rpn
from .checks.fmea import row_ap, traceability_matrix
from .llm import LLMClient
from .models import FmeaRow, Project, Proposal, Requirement
from . import prompts
from .knowledge import KnowledgeBase


def _req_dict(r: Requirement) -> dict:
    return {"id": r.id, "niveau": r.level, "asil": r.asil_raw, "texte": r.text,
            "parents": r.parent_ids, "verification": r.verification, "statut": r.status}


def _fmea_dict(f: FmeaRow) -> dict:
    ratings = None not in (f.severity, f.occurrence, f.detection)
    return {"id": f.id, "element": f.item, "fonction": f.function, "mode": f.failure_mode, "effet": f.effect,
            "cause": f.cause, "S": f.severity, "O": f.occurrence, "D": f.detection,
            "AP": row_ap(f), "RPN": rpn(f.severity, f.occurrence, f.detection) if ratings else None,
            "prevention": f.prevention_controls, "detection": f.detection_controls,
            "actions": f.actions, "exigences": f.requirement_ids}


def _fn(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []}}}


TOOLS = [
    _fn("run_rule_checks", "Lance les contrôles automatiques (exigences, AMDEC, traçabilité). Renvoie les anomalies."),
    _fn("list_requirements", "Liste les exigences, filtrables par niveau (SG, FSR, TSR...) ou ASIL.",
        {"level": {"type": "string"}, "asil": {"type": "string", "description": "QM, A, B, C ou D"}}),
    _fn("get_requirement", "Détail d'une exigence avec parents, enfants et lignes AMDEC liées.",
        {"id": {"type": "string"}}, ["id"]),
    _fn("list_fmea_rows", "Liste les lignes AMDEC, filtrables par gravité minimale, priorité d'action ou élément.",
        {"min_severity": {"type": "integer"}, "ap": {"type": "string", "enum": ["H", "M", "L"]},
         "item": {"type": "string"}}),
    _fn("get_fmea_row", "Détail d'une ligne AMDEC avec les exigences liées.", {"id": {"type": "string"}}, ["id"]),
    _fn("traceability_matrix", "Matrice objectifs de sécurité -> exigences -> lignes AMDEC."),
    _fn("record_proposal", "Enregistre une proposition pour validation humaine. Seul moyen de suggérer une modification.",
        {"kind": {"type": "string", "enum": ["reformulation", "mode_de_defaillance", "exigence", "action", "autre"]},
         "target": {"type": "string", "description": "Identifiant concerné (exigence, ligne AMDEC ou élément)"},
         "content": {"type": "string", "description": "Texte proposé"},
         "rationale": {"type": "string", "description": "Justification, avec identifiants sources"}},
        ["kind", "target", "content", "rationale"]),
]


SEARCH_TOOL = _fn(
    "search_knowledge",
    "Recherche dans la base documentaire de l'entreprise (procédures, guides, AMDEC passées, retours d'expérience). "
    "Renvoie des extraits avec leur source.",
    {"query": {"type": "string", "description": "Mots-clés ou question"}}, ["query"])


class SafetyAgent:
    def __init__(self, llm: LLMClient, project: Project, max_steps: int = 12, on_tool: Callable | None = None,
                 kb: KnowledgeBase | None = None):
        self.llm = llm
        self.project = project
        self.kb = kb
        self.tools = TOOLS + ([SEARCH_TOOL] if kb else [])
        self.max_steps = max_steps
        self.on_tool = on_tool
        self.proposals: list[Proposal] = []
        self.messages: list[dict] = [{"role": "system", "content": prompts.AGENT_SYSTEM}]

    # ---- tools
    def _run_tool(self, name: str, args: dict):
        p = self.project
        if name == "run_rule_checks":
            findings = run_all_checks(p)
            return {"nombre": len(findings), "anomalies": [f.to_dict() for f in findings]}
        if name == "list_requirements":
            level, asil = (args.get("level") or "").upper(), (args.get("asil") or "").upper()
            return [_req_dict(r) for r in p.requirements.values()
                    if (not level or r.level.upper() == level) and (not asil or (r.asil and r.asil.level == asil))]
        if name == "get_requirement":
            r = p.requirements.get(args.get("id", ""))
            if not r:
                return {"erreur": f"Exigence {args.get('id')} inconnue"}
            return {**_req_dict(r), "enfants": [c.id for c in p.children_of(r.id)],
                    "lignes_amdec": [_fmea_dict(f) for f in p.fmea_rows_for(r.id)]}
        if name == "list_fmea_rows":
            ms, ap, item = args.get("min_severity"), args.get("ap"), (args.get("item") or "").lower()
            return [_fmea_dict(f) for f in p.fmea.values()
                    if (ms is None or (f.severity or 0) >= ms) and (not ap or row_ap(f) == ap)
                    and (not item or item in f.item.lower())]
        if name == "get_fmea_row":
            f = p.fmea.get(args.get("id", ""))
            if not f:
                return {"erreur": f"Ligne AMDEC {args.get('id')} inconnue"}
            return {**_fmea_dict(f), "exigences_detail": [_req_dict(p.requirements[i])
                                                          for i in f.requirement_ids if i in p.requirements]}
        if name == "traceability_matrix":
            return traceability_matrix(p)
        if name == "search_knowledge" and self.kb:
            hits = self.kb.search(args.get("query", ""), k=5, llm=self.llm)
            return [{"source": c.citation(), "extrait": c.text} for c in hits] or {"resultat": "aucun extrait trouvé"}
        if name == "record_proposal":
            prop = Proposal(args.get("kind", "autre"), args.get("target", ""), args.get("content", ""),
                            args.get("rationale", ""))
            self.proposals.append(prop)
            return {"ok": True, "message": "Proposition enregistrée, en attente de validation humaine."}
        return {"erreur": f"Outil inconnu : {name}"}

    # ---- loop
    def ask(self, question: str) -> str:
        self.messages.append({"role": "user", "content": question})
        for _ in range(self.max_steps):
            msg = self.llm.chat(self.messages, tools=self.tools)
            calls = msg.get("tool_calls") or []
            self.messages.append({"role": "assistant", "content": msg.get("content") or "",
                                  **({"tool_calls": calls} if calls else {})})
            if not calls:
                return msg.get("content") or ""
            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                raw = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else dict(raw)
                except json.JSONDecodeError:
                    args = {}
                if self.on_tool:
                    self.on_tool(name, args)
                result = self._run_tool(name, args)
                self.messages.append({"role": "tool", "tool_call_id": call.get("id", name), "name": name,
                                      "content": json.dumps(result, ensure_ascii=False)})
        return "Nombre maximal d'étapes atteint sans réponse finale. Reformulez ou découpez la question."
