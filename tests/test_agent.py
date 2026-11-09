import json
from pathlib import Path

from safety_agent.agent import SafetyAgent
from safety_agent.ai import review_requirement, suggest_failure_modes
from safety_agent.llm import extract_json
from safety_agent.loaders import load_project

EX = Path(__file__).parent.parent / "examples"


class FakeLLM:
    """Replays scripted assistant messages and records what it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None, json_mode=False):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        return self.replies.pop(0)


def tool_call(name, args, cid="c1"):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def project():
    return load_project(EX / "bms_exigences.csv", EX / "bms_amdec.csv")[0]


def test_agent_tool_loop_and_proposal():
    llm = FakeLLM([
        tool_call("list_fmea_rows", {"ap": "H"}),
        tool_call("record_proposal", {"kind": "action", "target": "FM-01", "content": "Ajouter une 2e référence",
                                      "rationale": "AP=H sans action"}, "c2"),
        {"role": "assistant", "content": "FM-01 et FM-04 sont en priorité H."},
    ])
    agent = SafetyAgent(llm, project())
    answer = agent.ask("Quelles lignes sont en priorité H ?")
    assert "FM-01" in answer
    tool_result = json.loads(llm.calls[1]["messages"][-1]["content"])
    assert {r["id"] for r in tool_result} == {"FM-01", "FM-04"}
    assert len(agent.proposals) == 1 and agent.proposals[0].status == "À VALIDER"


def test_agent_unknown_ids_do_not_crash():
    llm = FakeLLM([tool_call("get_requirement", {"id": "NOPE"}), {"role": "assistant", "content": "Inconnue."}])
    SafetyAgent(llm, project()).ask("?")
    assert "inconnue" in llm.calls[1]["messages"][-1]["content"]


def test_agent_stops_after_max_steps():
    llm = FakeLLM([tool_call("run_rule_checks", {})] * 3)
    assert "maximal" in SafetyAgent(llm, project(), max_steps=3).ask("?")


def test_review_requirement_parses_model_json():
    p = project()
    reply = {"content": "```json\n" + json.dumps({
        "criteres": {"non_ambigue": {"ok": False, "commentaire": "« rapidement » non défini"},
                     "verifiable": {"ok": True, "commentaire": ""}},
        "reformulation": "Le BMS doit détecter une perte de communication CAN en moins de 50 ms.",
        "justification": "Valeur chiffrée"}) + "\n```"}
    findings, proposals = review_requirement(FakeLLM([reply]), p, p.requirements["FSR-06"])
    assert {f.code for f in findings} == {"IA-AMBIG", "IA-FORMAT"}  # only 2/7 criteria answered
    assert all(f.source == "IA" for f in findings)
    assert proposals[0].kind == "reformulation"


def _review_with(answer: dict, req_id="FSR-06"):
    p = project()
    return review_requirement(FakeLLM([{"content": json.dumps(answer, ensure_ascii=False)}]), p, p.requirements[req_id])


ALL = ["non_ambigue", "comprehensible", "atomique", "coherente", "faisable", "verifiable", "necessaire"]


def test_review_accepts_accents_and_oui_non():
    answer = {"Critères": {**{k: {"commentaire": "", "ok": "oui"} for k in ALL},
                           "non-ambiguë": {"commentaire": "« rapidement »", "ok": "non"},
                           "Vérifiable": {"commentaire": "pas de seuil", "ok": "false"}}}
    findings, _ = _review_with(answer)
    assert {f.code for f in findings} == {"IA-AMBIG", "IA-VERIF"}


def test_review_flags_empty_answer():
    findings, _ = _review_with({"reformulation": ""})
    assert [f.code for f in findings] == ["IA-FORMAT"]


def test_review_flags_disagreement_with_rules():
    findings, _ = _review_with({"criteres": {k: {"commentaire": "", "ok": True} for k in ALL}})
    assert [f.code for f in findings] == ["IA-DESACCORD"]  # FSR-06 contains "rapidement"


def test_review_prompt_contains_rule_findings():
    p = project()
    llm = FakeLLM([{"content": "{}"}])
    review_requirement(llm, p, p.requirements["FSR-06"])
    assert "rapidement" in llm.calls[0]["messages"][1]["content"].split("Contrôles automatiques")[1]


def test_clean_requirement_has_no_disagreement():
    findings, _ = _review_with({"criteres": {k: {"commentaire": "", "ok": True} for k in ALL}}, "FSR-01")
    assert findings == []


def test_suggest_failure_modes():
    reply = {"content": json.dumps({"modes": [{"mode": "Mesure figée", "mot_guide": "fonction figée", "effet": "E",
                                               "cause": "C", "S": 9, "O": 3, "D": 4}]})}
    llm = FakeLLM([reply])
    props = suggest_failure_modes(llm, project(), "Capteur tension", "Mesurer la tension cellule")
    assert props[0].data["S"] == 9
    assert "Dérive de la mesure" in llm.calls[0]["messages"][1]["content"]  # existing mode passed to the model


def test_extract_json_with_prose():
    assert extract_json('Voici : {"a": 1} merci') == {"a": 1}


def test_demo_llm_runs_full_workflow():
    from safety_agent.ai import review_requirements
    from safety_agent.demo import DemoLLM

    p = project()
    agent = SafetyAgent(DemoLLM(), p)
    assert "erreurs" in agent.ask("État des lieux ?")
    agent.ask("Propose une action pour chaque ligne H sans action.")
    assert {pr.target for pr in agent.proposals} == {"FM-01", "FM-04"}
    findings, proposals = review_requirements(DemoLLM(), p, ["FSR-06"])
    assert "IA-AMBIG" in {f.code for f in findings} and proposals
    assert suggest_failure_modes(DemoLLM(), p, "Capteur", "Mesurer")
