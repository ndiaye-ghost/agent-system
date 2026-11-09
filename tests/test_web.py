from pathlib import Path

import pytest

from safety_agent.models import Proposal
from safety_agent.validation import ACCEPTED, REJECTED, read_journal, record_decision

APP = str(Path(__file__).parent.parent / "safety_agent" / "webapp.py")


def test_journal_records_decisions(tmp_path):
    path = tmp_path / "j.csv"
    p = Proposal("reformulation", "FSR-06", "Le BMS doit…", "R2", data={"sources": ["[1] guide.docx"]})
    record_decision(p, ACCEPTED, "M. Ndiaye", "ok", "qwen2.5:7b", path=path)
    record_decision(Proposal("action", "FM-01", "x"), REJECTED, "Alice", path=path)
    rows = read_journal(path)
    assert [r["decision"] for r in rows] == [ACCEPTED, REJECTED]
    assert rows[0]["sources"] == "[1] guide.docx" and rows[0]["utilisateur"] == "M. Ndiaye"
    assert p.status == ACCEPTED


def test_journal_requires_user(tmp_path):
    with pytest.raises(ValueError):
        record_decision(Proposal("action", "FM-01", "x"), ACCEPTED, "  ", path=tmp_path / "j.csv")


@pytest.fixture
def app(tmp_path, monkeypatch):
    st_testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.chdir(tmp_path)  # journal and audit log written here
    monkeypatch.setenv("SAFETY_AGENT_BASE_URL", "http://127.0.0.1:9/v1")  # no server -> demo mode
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_page_loads_in_demo_mode_with_checks(app):
    assert any("Mode démo" in w.value for w in app.warning)
    assert [m.label for m in app.metric][:2] == ["Erreurs", "Avertissements"]
    assert app.metric[0].value == "9"


def test_review_then_validate(app, tmp_path):
    app.text_input(key="user").set_value("Testeur").run()
    review_button = next(b for b in app.button if b.label == "Lancer la relecture")
    review_button.click().run()
    assert not app.exception, app.exception
    validate = next(b for b in app.button if b.label == "✅ Valider")
    validate.click().run()
    rows = read_journal(tmp_path / "journal_validations.csv")
    assert rows and rows[0]["utilisateur"] == "Testeur" and rows[0]["decision"] == ACCEPTED


def test_agent_chat_keeps_history(app):
    app.chat_input[0].set_value("État des lieux ?").run()
    app.chat_input[0].set_value("Que dit notre guide sur les exigences temporelles ?").run()
    assert not app.exception, app.exception
    texts = [m.markdown[-1].value for m in app.chat_message if m.markdown]
    assert len(texts) == 4  # 2 questions + 2 answers kept
    assert "guide_redaction_exigences.docx" in texts[-1]


def test_document_search(app):
    search = next(t for t in app.text_input if t.label == "Rechercher dans les documents")
    search.set_value("watchdog démarrage").run()
    assert any("retours_experience.md" in m.value for m in app.markdown)
