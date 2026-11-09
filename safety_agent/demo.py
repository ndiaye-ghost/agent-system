"""Demo LLM: canned answers so the notebooks run without a model server.

It is NOT an AI: answers are built from the deterministic checks and fixed
templates. Use it to discover the workflow, then switch to your real server.
"""
from __future__ import annotations

import json
import re

from . import prompts
from .checks.requirements import _AMBIGUOUS_RE, _SHALL_RE


class DemoLLM:
    is_demo = True

    def chat(self, messages: list[dict], tools=None, json_mode: bool = False) -> dict:
        system = messages[0].get("content", "") if messages else ""
        if system == prompts.REVIEW_SYSTEM:
            return {"role": "assistant", "content": json.dumps(self._review(messages[-1]["content"]), ensure_ascii=False)}
        if system == prompts.SUGGEST_SYSTEM:
            return {"role": "assistant", "content": json.dumps(self._suggest(messages[-1]["content"]), ensure_ascii=False)}
        if not tools:
            return _text("[DÉMO] Ceci est une réponse simulée : aucun modèle n'est connecté. "
                         "Lancez Ollama ou vLLM pour obtenir de vraies réponses.")
        return self._agent(messages)

    @staticmethod
    def _review(user: str) -> dict:
        text = re.search(r"^Texte : (.*)$", user, re.M).group(1)
        vague = sorted({m.group(1) for m in _AMBIGUOUS_RE.finditer(text)})
        multi = len(_SHALL_RE.findall(text)) > 1
        ok = lambda c: {"ok": True, "commentaire": ""}  # noqa: E731
        crit = {k: ok(k) for k in ["non_ambigue", "comprehensible", "atomique", "coherente", "faisable",
                                   "verifiable", "necessaire"]}
        reform = ""
        if vague:
            crit["non_ambigue"] = {"ok": False, "commentaire": f"termes non définis : {', '.join(vague)}"}
            crit["verifiable"] = {"ok": False, "commentaire": "pas de critère de réussite chiffré"}
            reform = "[DÉMO] Reformuler avec une valeur chiffrée (ex. temps de réaction en ms) et un état sûr défini."
        if multi:
            crit["atomique"] = {"ok": False, "commentaire": "plusieurs obligations dans une même exigence"}
            reform = reform or "[DÉMO] Scinder en deux exigences distinctes."
        return {"criteres": crit, "reformulation": reform,
                "justification": "Réponse simulée (mode démo), construite à partir des règles automatiques."}

    @staticmethod
    def _suggest(user: str) -> dict:
        item = re.search(r"^Élément : (.*)$", user, re.M).group(1)
        modes = [
            ("Perte du signal", "perte de fonction", "Information indisponible pour la fonction de sécurité",
             "Rupture de connexion, défaut d'alimentation", 8, 3, 3, "Connecteur verrouillé", "Diagnostic de circuit ouvert"),
            ("Valeur figée", "fonction figée", "Dérive non détectée de la grandeur surveillée",
             "Blocage du convertisseur, défaut logiciel", 9, 3, 5, "Revue de conception", "Contrôle de variation / plausibilité"),
            ("Valeur erronée hors tolérance", "valeur erronée", "Décision de sécurité prise sur une mesure fausse",
             "Dérive en température, vieillissement", 9, 4, 5, "Composants qualifiés AEC-Q", "Comparaison avec une mesure redondante"),
        ]
        return {"modes": [{"mode": f"[DÉMO] {m} ({item})", "mot_guide": g, "effet": e, "cause": c, "S": s, "O": o,
                           "D": d, "prevention": pv, "detection": dt,
                           "justification": "Exemple générique (mode démo), à remplacer par l'analyse du modèle."}
                          for m, g, e, c, s, o, d, pv, dt in modes]}

    @staticmethod
    def _agent(messages: list[dict]) -> dict:
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        question = messages[last_user]["content"].lower()
        done = [m for m in messages[last_user + 1:] if m.get("role") == "tool"]
        names = {m.get("name") for m in done}
        if "run_rule_checks" not in names:
            return _call([("run_rule_checks", {})])
        data = json.loads(next(m for m in done if m.get("name") == "run_rule_checks")["content"])
        anomalies = data.get("anomalies", [])
        wants_actions = any(w in question for w in ("action", "propos"))
        if wants_actions and "record_proposal" not in names:
            targets = [a["target"] for a in anomalies if a["code"] == "FMEA-010"]
            return _call([("record_proposal", {
                "kind": "action", "target": t,
                "content": "[DÉMO] Définir une action de réduction du risque (diagnostic supplémentaire "
                           "ou redondance) ou justifier formellement l'absence d'action.",
                "rationale": f"{t} : priorité d'action H sans action (FMEA-010)."}) for t in targets])
        if wants_actions:
            n = sum(1 for m in done if m.get("name") == "record_proposal")
            return _text(f"[DÉMO — réponse simulée, pas d'IA] {n} proposition(s) d'action enregistrée(s) "
                         "pour les lignes en priorité H sans action. Voir le tableau des propositions.")
        errors = [a for a in anomalies if a["level"] == "error"]
        lines = [f"[DÉMO — réponse simulée, pas d'IA] {len(anomalies)} anomalies détectées, dont {len(errors)} erreurs :"]
        lines += [f"- {a['target']} : {a['message']}" for a in errors[:10]]
        return _text("\n".join(lines))


def _text(content: str) -> dict:
    return {"role": "assistant", "content": content}


def _call(calls: list[tuple[str, dict]]) -> dict:
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": f"demo{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)}}
        for i, (n, a) in enumerate(calls)]}
