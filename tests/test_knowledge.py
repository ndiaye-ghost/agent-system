import json
import zipfile
from pathlib import Path

import pytest

from safety_agent.agent import SafetyAgent
from safety_agent.ai import review_requirement, suggest_failure_modes
from safety_agent.cli import main
from safety_agent.demo import DemoLLM
from safety_agent.knowledge import KnowledgeBase, extract, format_context, tokenize
from safety_agent.loaders import load_project

EX = Path(__file__).parent.parent / "examples"
DOCS = EX / "documents"


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.build([DOCS])


def project():
    return load_project(EX / "bms_exigences.csv", EX / "bms_amdec.csv")[0]


def test_all_example_formats_are_indexed(kb):
    assert {d["path"] for d in kb.documents} == {
        "amdec_bms_gen1.xlsx", "guide_redaction_exigences.docx", "procedure_amdec.pdf", "retours_experience.md"}
    assert all(d["chunks"] > 0 and "error" not in d for d in kb.documents)


def test_docx_sections_and_tables(tmp_path):
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           '<w:p><w:pPr><w:pStyle w:val="Titre1"/></w:pPr><w:r><w:t>Règles</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>Le terme rapidement est interdit.</w:t></w:r></w:p>'
           '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
           '</w:body></w:document>')
    path = tmp_path / "g.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)
    [(location, text)] = extract(path)
    assert location == "Règles" and "rapidement" in text and "A | B" in text


def test_tokenize_ignores_accents_case_and_plurals():
    assert tokenize("Les Défauts CAN") == tokenize("défaut can")


def test_search_finds_relevant_passages(kb):
    assert kb.search("dérive offset capteur de courant", 1)[0].source in {"retours_experience.md", "amdec_bms_gen1.xlsx"}
    assert kb.search("temps de réaction perte communication CAN", 3)[0].source == "guide_redaction_exigences.docx"
    assert kb.search("xyzzy inexistant") == []


def test_save_load_roundtrip(kb, tmp_path):
    kb.save(tmp_path / "kb.json")
    again = KnowledgeBase.load(tmp_path / "kb.json")
    assert len(again.chunks) == len(kb.chunks) and again.documents[0]["sha256"]


class FakeEmbedder:
    """Two-dimensional 'embeddings': [mentions temperature, mentions CAN]."""

    def embed(self, texts, model):
        return [[1.0 if "froid" in t.lower() or "température" in t.lower() else 0.01,
                 1.0 if "can" in t.lower() else 0.01] for t in texts]


def test_semantic_search_is_fused_with_keywords():
    kb = KnowledgeBase.build([DOCS], llm=FakeEmbedder(), embed_model="fake")
    assert all(c.embedding for c in kb.chunks)
    hits = kb.search("comportement à basse température", 3, llm=FakeEmbedder())
    assert any("froid" in c.text or "température" in c.text for c in hits)


def test_review_prompt_contains_cited_excerpts(kb):
    sent = []

    class Spy(DemoLLM):
        def chat(self, messages, tools=None, json_mode=False):
            sent.append(messages[-1]["content"])
            return super().chat(messages, tools, json_mode)

    p = project()
    _, proposals = review_requirement(Spy(), p, p.requirements["FSR-06"], kb)
    assert "[1] (" in sent[0] and "guide_redaction_exigences.docx" in sent[0]
    assert proposals[0].data["sources"]


def test_suggest_reuses_past_fmea(kb):
    props = suggest_failure_modes(DemoLLM(), project(), "Capteur de courant pack", "Mesurer le courant batterie", kb=kb)
    reused = [p for p in props if "AMDEC d'un projet précédent" in p.rationale]
    assert any("Offset" in p.data["mode"] for p in reused)


def test_agent_search_tool(kb):
    agent = SafetyAgent(DemoLLM(), project(), kb=kb)
    assert "search_knowledge" in {t["function"]["name"] for t in agent.tools}
    answer = agent.ask("Que dit notre guide sur les exigences temporelles ?")
    assert "guide_redaction_exigences.docx" in answer
    assert "search_knowledge" not in {t["function"]["name"] for t in SafetyAgent(DemoLLM(), project()).tools}


def test_cli_index_and_search(tmp_path, capsys):
    out = tmp_path / "kb.json"
    assert main(["index", str(DOCS), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["chunks"]
    assert main(["search", "watchdog démarrage", "--kb", str(out), "-k", "1"]) == 0
    assert "retours_experience.md" in capsys.readouterr().out


def test_format_context_empty():
    assert "Aucun extrait" in format_context([])
