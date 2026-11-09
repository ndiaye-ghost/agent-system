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
        return self._agent(messages, tools)

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
        refs = re.findall(r"^\[(\d+)\] \((.*?)\)$", user, re.M)
        cite = f" Voir aussi la base documentaire : [{refs[0][0]}] {refs[0][1]}." if refs else ""
        return {"criteres": crit, "reformulation": reform,
                "justification": "Réponse simulée (mode démo), construite à partir des règles automatiques." + cite}

    @staticmethod
    def _suggest(user: str) -> dict:
        item = re.search(r"^Élément : (.*)$", user, re.M).group(1)
        from_history = _modes_from_knowledge(user, item)
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
                          for m, g, e, c, s, o, d, pv, dt in modes]
                + from_history}

    @staticmethod
    def _agent(messages: list[dict], tools: list[dict]) -> dict:
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        question = messages[last_user]["content"].lower()
        done = [m for m in messages[last_user + 1:] if m.get("role") == "tool"]
        results = {m.get("name"): m["content"] for m in done}
        tool_names = {t["function"]["name"] for t in tools}

        # Questions about company documents -> knowledge base search
        wants_docs = any(w in question for w in ("procédure", "document", "retour", "historique", "précédent", "guide"))
        if wants_docs and "search_knowledge" in tool_names:
            if "search_knowledge" not in results:
                return _call([("search_knowledge", {"query": messages[last_user]["content"]})])
            hits = json.loads(results["search_knowledge"])
            hits = hits if isinstance(hits, list) else []
            lines = ["[DÉMO — réponse simulée, pas d'IA] Extraits trouvés dans la base documentaire :"]
            lines += [f"- {h['source']} : {h['extrait'][:220]}…" for h in hits[:4]]
            return _text("\n".join(lines))

        if "run_rule_checks" not in results:
            return _call([("run_rule_checks", {})])
        anomalies = json.loads(results["run_rule_checks"]).get("anomalies", [])

        if any(w in question for w in ("action", "propos")):
            if "record_proposal" not in results:
                targets = [a["target"] for a in anomalies if a["code"] == "FMEA-010"]
                return _call([("record_proposal", {
                    "kind": "action", "target": t,
                    "content": "[DÉMO] Définir une action de réduction du risque (diagnostic supplémentaire "
                               "ou redondance) ou justifier formellement l'absence d'action.",
                    "rationale": f"{t} : priorité d'action H sans action (FMEA-010)."}) for t in targets])
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


_HISTORY_KEYS = {"mode de défaillance": "mode", "effet": "effet", "cause": "cause", "s": "S", "o": "O", "d": "D",
                 "prévention": "prevention", "mesures de détection": "detection"}


def _modes_from_knowledge(user: str, item: str) -> list[dict]:
    """Reuse failure modes found in past FMEA excerpts ("Col: value | Col: value")."""
    out = []
    for num, source, body in re.findall(r"^\[(\d+)\] \((.*?)\)\n(.*?)(?=\n\n\[\d+\] |\Z)", user, re.M | re.S):
        fields = {}
        for part in body.split(" | "):
            key, _, value = part.partition(": ")
            if key.strip().lower() in _HISTORY_KEYS:
                fields[_HISTORY_KEYS[key.strip().lower()]] = value.strip()
        same_item = re.search(r"(?:Élément|Element|Composant): ([^|]*)", body)
        if fields.get("mode") and same_item and same_item.group(1).strip().lower() == item.strip().lower():
            out.append({"mot_guide": "retour d'expérience", **fields,
                        "mode": f"[DÉMO] {fields['mode']}",
                        "justification": f"Repris de l'AMDEC d'un projet précédent [{num}] {source}."})
    return out
