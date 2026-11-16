import json
from pathlib import Path

import pytest

from safety_agent.agent import SafetyAgent, is_general_question
from safety_agent.demo import DemoLLM
from safety_agent.glossary import GLOSSARY, find_terms
from safety_agent.loaders import load_project

EX = Path(__file__).parent.parent / "examples"


def project():
    return load_project(EX / "bms_exigences.csv", EX / "bms_amdec.csv")[0]


@pytest.mark.parametrize("question,general", [
    ("c'est quoi un AMDEC", True),
    ("Qu’est-ce que le FTTI ?", True),
    ("Explique la décomposition d'ASIL", True),
    ("Différence entre AMDEC et FMEDA", True),
    ("Quelles lignes AMDEC de gravité 9 ou 10 n'ont pas d'action ?", False),
    ("Fais un état des lieux des erreurs bloquantes", False),
    ("Explique pourquoi FSR-06 est ambiguë", False),
    ("Que dit notre procédure sur la détection ?", False),
    ("Chaque objectif de sécurité est-il couvert par l'AMDEC ?", False),
])
def test_routing(question, general):
    assert is_general_question(question, project()) is general


def test_glossary_finds_terms_and_expands_amdec_correctly():
    [amdec] = find_terms("c'est quoi un AMDEC")
    assert amdec.definition.startswith("Analyse des Modes de Défaillance, de leurs Effets et de leur Criticité")
    assert [t.name for t in find_terms("différence entre AMDEC et FMEDA")] == ["AMDEC", "FMEDA"]
    assert find_terms("bonjour") == []
    assert len({t.name for t in GLOSSARY}) == len(GLOSSARY)


class Spy:
    def __init__(self, reply="Réponse."):
        self.calls, self.reply = [], reply

    def chat(self, messages, tools=None, json_mode=False):
        self.calls.append({"messages": messages, "tools": tools})
        return {"role": "assistant", "content": self.reply}


def test_general_question_uses_glossary_without_project_tools():
    spy = Spy("L'AMDEC est…")
    used = []
    agent = SafetyAgent(spy, project(), on_tool=lambda n, a: used.append(n))
    assert agent.ask("c'est quoi un AMDEC") == "L'AMDEC est…"
    call = spy.calls[0]
    assert call["tools"] is None
    prompt = call["messages"][-1]["content"]
    assert "Analyse des Modes de Défaillance, de leurs Effets et de leur Criticité" in prompt
    assert "run_rule_checks" not in used and used == ["glossaire"]
    assert [m["role"] for m in agent.messages[-2:]] == ["user", "assistant"]  # kept in the conversation


def test_project_question_still_uses_tools():
    agent = SafetyAgent(DemoLLM(), project())
    used = []
    agent.on_tool = lambda n, a: used.append(n)
    agent.ask("Quelles lignes AMDEC de gravité 9 ou 10 n'ont pas d'action ?")
    assert "run_rule_checks" in used


def test_demo_general_answer_is_the_glossary_definition():
    answer = SafetyAgent(DemoLLM(), project()).ask("c'est quoi un AMDEC")
    assert "Analyse des Modes de Défaillance, de leurs Effets et de leur Criticité" in answer
    assert "anomalies" not in answer
