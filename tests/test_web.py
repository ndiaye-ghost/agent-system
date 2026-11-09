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


def _go(at, page):
    at.button(key=f"nav_{page}").click().run()
    assert not at.exception, at.exception


def test_home_is_chat_with_suggestions(app):
    assert any("Comment puis-je vous aider" in m.value for m in app.markdown)
    assert app.chat_input
    assert any("Mode démonstration" in m.value for m in app.sidebar.markdown)


def test_checks_page(app):
    _go(app, "checks")
    assert [m.label for m in app.metric][:2] == ["Erreurs", "Avertissements"]
    assert app.metric[0].value == "9"


def test_settings_then_review_then_validate(app, tmp_path):
    _go(app, "settings")
    next(t for t in app.text_input if t.label == "Votre nom").set_value("Testeur").run()
    assert app.session_state["cfg"]["user"] == "Testeur"
    _go(app, "review")
    next(b for b in app.button if b.label == "Lancer la relecture").click().run()
    assert not app.exception, app.exception
    next(b for b in app.button if b.label == "Valider").click().run()
    rows = read_journal(tmp_path / "journal_validations.csv")
    assert rows and rows[0]["utilisateur"] == "Testeur" and rows[0]["decision"] == ACCEPTED


def test_chat_conversation_and_history(app):
    app.chat_input[0].set_value("État des lieux ?").run()
    app.chat_input[0].set_value("Que dit notre guide sur les exigences temporelles ?").run()
    assert not app.exception, app.exception
    texts = [m.markdown[0].value for m in app.chat_message if m.markdown]
    assert len(texts) == 4  # 2 questions + 2 answers
    assert "guide_redaction_exigences.docx" in texts[-1]
    assert len(app.session_state["convs"]) == 1
    app.button(key="nav_new").click().run()  # new conversation: back to the welcome screen
    assert any("Comment puis-je vous aider" in m.value for m in app.markdown)
    app.button(key="sugg_0").click().run()
    assert len(app.session_state["convs"]) == 2


def test_document_search(app):
    _go(app, "docs")
    next(t for t in app.text_input if t.label == "Rechercher dans les documents").set_value("watchdog démarrage").run()
    assert any("retours_experience.md" in m.value for m in app.markdown)


def test_agent_prompt_allows_general_questions():
    from safety_agent.prompts import AGENT_SYSTEM

    assert "Connaissances générales (à vérifier)" in AGENT_SYSTEM


def _server_app(tmp_path, monkeypatch, secrets=None):
    st_testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAFETY_AGENT_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("SAFETY_AGENT_SERVEUR", "1")
    monkeypatch.setenv("SAFETY_AGENT_MODEL", "qwen2.5:32b")
    monkeypatch.setenv("SAFETY_AGENT_DOCS", str(Path(__file__).parent.parent / "examples" / "documents"))
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    for k, v in (secrets or {}).items():
        at.secrets[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def test_server_mode_locks_model_and_folder(tmp_path, monkeypatch):
    at = _server_app(tmp_path, monkeypatch)
    assert at.session_state["cfg"]["model"] == "qwen2.5:32b"
    assert at.session_state["cfg"]["kb_mode"] == "Dossier"
    _go(at, "settings")
    labels = {t.label for t in at.text_input}
    assert "Adresse du serveur" not in labels and "Chemin du dossier" not in labels
    assert not any(b.label == "Arrêter l'application" for b in at.button)
    _go(at, "docs")
    assert any("4 document(s)" in c.value for c in at.caption)


def test_company_sign_in_required_when_configured(tmp_path, monkeypatch):
    at = _server_app(tmp_path, monkeypatch, secrets={"auth": {
        "redirect_uri": "http://localhost:8501/oauth2callback", "cookie_secret": "x" * 32,
        "client_id": "id", "client_secret": "secret",
        "server_metadata_url": "https://login.microsoftonline.com/tenant/v2.0/.well-known/openid-configuration"}})
    assert any(b.label == "Se connecter" for b in at.button)
    assert not at.chat_input  # nothing else is shown before sign-in


def test_local_mode_offers_stop_button(app):
    _go(app, "settings")
    assert any(b.label == "Arrêter l'application" for b in app.button)
