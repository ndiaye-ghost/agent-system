"""Single-shot AI tasks: requirement review and failure-mode suggestions.

These are more reliable than the free-form agent with small local models,
because each call has one narrow job and a fixed JSON format.
"""
from __future__ import annotations

import unicodedata

from .checks.requirements import check_requirements
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


def _key(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return "_".join(s.replace("-", " ").split())


def _ok(value) -> bool | None:
    """Accept true/false, "oui"/"non", "ok"/"ko"... as the model may answer either way."""
    if isinstance(value, bool):
        return value
    v = _key(value) if isinstance(value, (str, int)) else ""
    if v in {"true", "oui", "yes", "ok", "vrai", "1", "conforme", "respecte"}:
        return True
    if v in {"false", "non", "no", "ko", "faux", "0", "non_conforme", "non_respecte"}:
        return False
    return None


def _criteria(data: dict) -> dict[str, dict]:
    """Criteria dict with normalized keys, wherever the model put it."""
    if not isinstance(data, dict):
        return {}
    normed = {_key(k): v for k, v in data.items()}
    block = normed.get("criteres") or normed.get("criteria") or normed
    if not isinstance(block, dict):
        return {}
    out = {}
    for k, v in block.items():
        k = _key(k)
        if k == "ambigue":
            k = "non_ambigue"
        if isinstance(v, dict):
            out[k] = {_key(kk): vv for kk, vv in v.items()}
        elif isinstance(v, (bool, str)):
            out[k] = {"ok": v, "commentaire": ""}
    return out


def _rule_findings(project: Project, req: Requirement) -> list[Finding]:
    """Deterministic wording/attribute checks for this requirement only."""
    scope = Project({req.id: req, **{p: project.requirements[p] for p in req.parent_ids if p in project.requirements}})
    return [f for f in check_requirements(scope) if f.target == req.id and f.code not in {"REQ-012", "REQ-013"}]


def review_requirement(llm: LLMClient, project: Project, req: Requirement,
                       kb: KnowledgeBase | None = None) -> tuple[list[Finding], list[Proposal]]:
    parents = "; ".join(
        f"{p.id} [{p.asil_raw}] {p.text}" for pid in req.parent_ids if (p := project.requirements.get(pid))
    ) or "aucune"
    sources = kb.search(f"{req.text} {parents}", k=4, llm=llm) if kb else []
    rules = _rule_findings(project, req)
    user = prompts.REVIEW_USER.format(
        rule_findings="\n".join(f"- {f.message}" for f in rules) or "- aucun problème détecté",
        id=req.id, level=req.level or "?", asil=req.asil_raw or "ASIL ?", text=req.text,
        parents=parents, verification=req.verification or "non renseignée",
        knowledge=format_context(sources) if kb else NO_KB,
    )
    answer = llm.chat(
        [{"role": "system", "content": prompts.REVIEW_SYSTEM}, {"role": "user", "content": user}], json_mode=True
    )
    data = extract_json(answer.get("content", ""))
    criteria = _criteria(data)
    findings: list[Finding] = []
    answered = 0
    for key, (code, label) in CRITERIA_LABELS.items():
        crit = criteria.get(key) or {}
        ok = _ok(crit.get("ok"))
        if ok is None:
            continue
        answered += 1
        if ok is False:
            comment = str(crit.get("commentaire") or crit.get("comment") or "").strip()
            findings.append(Finding(code, Level.WARNING, req.id, f"Exigence {label} : {comment}", source="IA"))
    # Never fail silently: an empty answer must not look like "requirement is fine".
    if answered < len(CRITERIA_LABELS):
        findings.append(Finding("IA-FORMAT", Level.WARNING, req.id,
                                f"Réponse IA incomplète : {answered}/{len(CRITERIA_LABELS)} critères évalués. "
                                "Relancer ou consulter le journal d'audit.", source="IA"))
    if rules and answered and not any(f.level == Level.WARNING and f.code != "IA-FORMAT" for f in findings):
        findings.append(Finding("IA-DESACCORD", Level.WARNING, req.id,
                                "L'IA juge l'exigence conforme alors que les contrôles automatiques ont relevé : "
                                + "; ".join(f.message for f in rules) + " La relecture IA n'est pas fiable ici.",
                                source="IA"))
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
