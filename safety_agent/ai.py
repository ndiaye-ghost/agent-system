"""Single-shot AI tasks: requirement review and failure-mode suggestions.

These are more reliable than the free-form agent with small local models,
because each call has one narrow job and a fixed JSON format.
"""
from __future__ import annotations

from .llm import LLMClient, LLMError, extract_json
from .models import Finding, Level, Project, Proposal, Requirement
from . import prompts
from .knowledge import KnowledgeBase, format_context

NO_KB = "Aucune base documentaire fournie."

# criterion -> (finding code, label)
CRITERIA_LABELS = {
    "non_ambigue": ("IA-AMBIG", "ambiguë"),
    "comprehensible": ("IA-COMPR", "peu compréhensible"),
    "atomique": ("IA-ATOM", "non atomique"),
    "coherente": ("IA-COHER", "incohérente"),
    "faisable": ("IA-FAISA", "faisabilité douteuse"),
    "verifiable": ("IA-VERIF", "non vérifiable"),
    "necessaire": ("IA-NECES", "nécessité non démontrée"),
}


def review_requirement(llm: LLMClient, project: Project, req: Requirement,
                       kb: KnowledgeBase | None = None) -> tuple[list[Finding], list[Proposal]]:
    parents = "; ".join(
        f"{p.id} [{p.asil_raw}] {p.text}" for pid in req.parent_ids if (p := project.requirements.get(pid))
    ) or "aucune"
    sources = kb.search(f"{req.text} {parents}", k=4, llm=llm) if kb else []
    user = prompts.REVIEW_USER.format(
        id=req.id, level=req.level or "?", asil=req.asil_raw or "ASIL ?", text=req.text,
        parents=parents, verification=req.verification or "non renseignée",
        knowledge=format_context(sources) if kb else NO_KB,
    )
    answer = llm.chat(
        [{"role": "system", "content": prompts.REVIEW_SYSTEM}, {"role": "user", "content": user}], json_mode=True
    )
    data = extract_json(answer.get("content", ""))
    findings: list[Finding] = []
    for key, (code, label) in CRITERIA_LABELS.items():
        crit = (data.get("criteres") or {}).get(key) or {}
        if crit.get("ok") is False:
            findings.append(Finding(code, Level.WARNING, req.id,
                                    f"Exigence {label} : {crit.get('commentaire', '').strip()}", source="IA"))
    proposals = []
    reformulation = (data.get("reformulation") or "").strip()
    if reformulation and reformulation != req.text:
        proposals.append(Proposal("reformulation", req.id, reformulation, (data.get("justification") or "").strip(),
                                  data={"sources": _sources(sources)}))
    return findings, proposals


def _sources(chunks) -> list[str]:
    return [f"[{n}] {c.citation()}" for n, c in enumerate(chunks, 1)]


def review_requirements(llm: LLMClient, project: Project, ids: list[str] | None = None, on_progress=None,
                        kb: KnowledgeBase | None = None):
    findings, proposals = [], []
    targets = [project.requirements[i] for i in ids] if ids else list(project.requirements.values())
    for n, req in enumerate(targets, 1):
        if on_progress:
            on_progress(n, len(targets), req.id)
        try:
            f, p = review_requirement(llm, project, req, kb)
        except LLMError as e:
            f, p = [Finding("IA-ERR", Level.INFO, req.id, f"Relecture IA impossible : {e}", source="IA")], []
        findings += f
        proposals += p
    return findings, proposals


def suggest_failure_modes(llm: LLMClient, project: Project, item: str, function: str, context: str = "",
                          kb: KnowledgeBase | None = None) -> list[Proposal]:
    existing = [
        f"- {r.failure_mode}" for r in project.fmea.values()
        if item.lower() in r.item.lower() or (function and function.lower() in r.function.lower())
    ]
    sources = kb.search(f"{item} {function} mode de défaillance {context}", k=6, llm=llm) if kb else []
    user = prompts.SUGGEST_USER.format(
        item=item, function=function or "non précisée", context=context or "non précisé",
        existing="\n".join(existing) or "aucun",
        knowledge=format_context(sources) if kb else NO_KB,
    )
    answer = llm.chat(
        [{"role": "system", "content": prompts.SUGGEST_SYSTEM}, {"role": "user", "content": user}], json_mode=True
    )
    data = extract_json(answer.get("content", ""))
    modes = data.get("modes", data) if isinstance(data, dict) else data
    out = []
    for m in modes or []:
        if not isinstance(m, dict) or not m.get("mode"):
            continue
        content = (
            f"Mode : {m.get('mode')} [{m.get('mot_guide', '')}] | Effet : {m.get('effet', '')} | "
            f"Cause : {m.get('cause', '')} | S={m.get('S', '?')} O={m.get('O', '?')} D={m.get('D', '?')} | "
            f"Prévention : {m.get('prevention', '')} | Détection : {m.get('detection', '')}"
        )
        target = f"{item} / {function}" if function else item
        out.append(Proposal("mode_de_defaillance", target, content, m.get("justification", ""),
                            data={**m, "sources": _sources(sources)}))
    return out
