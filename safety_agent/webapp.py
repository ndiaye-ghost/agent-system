"""Web page for safety-agent (Streamlit), chat-first layout.

Run with:  safety-agent web            (this PC only)
           safety-agent web --partage  (colleagues open http://<pc-name>:8501)
"""
from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # streamlit runs this file as a script
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from safety_agent.agent import SafetyAgent  # noqa: E402
from safety_agent.ai import review_requirements, suggest_failure_modes  # noqa: E402
from safety_agent.checks import run_all_checks  # noqa: E402
from safety_agent.checks.action_priority import action_priority  # noqa: E402
from safety_agent.demo import DemoLLM  # noqa: E402
from safety_agent.knowledge import SUPPORTED, KnowledgeBase  # noqa: E402
from safety_agent.llm import LLMClient, LLMConfig, LLMError  # noqa: E402
from safety_agent.loaders import load_project  # noqa: E402
from safety_agent.models import Level, Proposal  # noqa: E402
from safety_agent.notebook import findings_df, fmea_df, matrix_df, requirements_df  # noqa: E402
from safety_agent.report import markdown_report, write_proposals_csv  # noqa: E402
from safety_agent.validation import ACCEPTED, REJECTED, proposal_id, read_journal, record_decision  # noqa: E402

APP_NAME = "Assistant Sûreté"
EXAMPLES = ROOT / "examples"
LEVEL_LABELS = {"error": "Erreur", "warning": "Avertissement", "info": "Information"}
SUGGESTIONS = [
    ("Faire un état des lieux", "Fais un état des lieux des erreurs bloquantes de l'AMDEC et des exigences."),
    ("Lignes critiques sans action", "Quelles lignes AMDEC de gravité 9 ou 10 n'ont pas d'action ?"),
    ("Couverture des objectifs", "Chaque objectif de sécurité est-il couvert par l'AMDEC ?"),
    ("Question de méthode", "Qu'est-ce que le FTTI et comment l'utiliser dans une exigence ?"),
]

st.set_page_config(page_title=APP_NAME, page_icon=":material/shield:", layout="wide",
                   initial_sidebar_state="expanded")

ss = st.session_state
ss.setdefault("page", "chat")
ss.setdefault("convs", [])           # [{"id", "title", "messages"}]
ss.setdefault("active", None)        # id of the open conversation
ss.setdefault("agents", {})          # conversation id -> SafetyAgent
ss.setdefault("proposals", {})       # proposal id -> Proposal
ss.setdefault("review_res", None)
ss.setdefault("suggest_ids", [])
ss.setdefault("cfg", {
    "user": "", "base_url": LLMConfig().base_url, "model": "qwen2.5:7b",
    "data_mode": "Exemple", "reqs_file": None, "fmea_file": None,
    "kb_mode": "Exemples", "kb_folder": "", "kb_files": (),
})
cfg = ss.cfg


# ----------------------------------------------------------------------------- style

CSS = """
<style>
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .stMarkdown, input, textarea, button {
  font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, "Helvetica Neue", Arial, sans-serif;
}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
[data-testid="stHeader"] { background: transparent; }
.block-container, [data-testid="stBottomBlockContainer"] { max-width: __WIDTH__; }
.block-container { padding-top: 2.2rem; padding-bottom: 6rem; }
h1 { font-size: 1.6rem !important; font-weight: 600 !important; padding-bottom: 0.2rem !important; }
h2, h3 { font-size: 1.1rem !important; font-weight: 600 !important; padding-top: 1rem !important; }

/* sidebar */
[data-testid="stSidebar"] { background: #f7f7f8; border-right: 1px solid #ececec; }
[data-testid="stSidebarHeader"] { padding: 0.6rem 0.8rem 0; height: 2.6rem; }
[data-testid="stSidebarUserContent"] { padding-top: 0; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 2px; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[data-testid="stSidebar"] button {
  justify-content: flex-start; width: 100%; border-radius: 8px; border: none; background: transparent;
  padding: 0.42rem 0.6rem; min-height: 0; color: #1f2328;
}
[data-testid="stSidebar"] button > div { justify-content: flex-start !important; width: 100%; gap: 0.55rem; }
[data-testid="stSidebar"] button:hover { background: #ececf1; color: #1f2328; }
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] { background: #e6e6ea; }
[data-testid="stSidebar"] .st-key-nav_new button { background: #ffffff; border: 1px solid #dcdce0; margin-bottom: 0.3rem; }
[data-testid="stSidebar"] button p { font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sa-brand { font-weight: 600; font-size: 1rem; padding: 0 0.6rem 0.6rem; color: #1f2328; }
.sa-section { font-size: 0.72rem; color: #8b8f97; text-transform: uppercase; letter-spacing: .05em;
              margin: 1rem 0 0.25rem 0.6rem; }
.sa-status { font-size: 0.82rem; color: #57606a; padding: 0.1rem 0.6rem; }
.sa-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }

/* chat */
[data-testid="stChatMessage"] { background: transparent; padding: 0.4rem 0; gap: 0; }
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"] { display: none; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
  background: #f1f1f3; border-radius: 18px; padding: 0.6rem 1rem; max-width: 78%; flex: 0 1 auto; margin-left: auto !important; margin-right: 0 !important;
}
[data-testid="stChatMessageContent"] p { line-height: 1.6; }
[data-testid="stChatInput"] { border-radius: 24px; }
.sa-hero { text-align: center; margin: 14vh 0 2rem; }
.sa-hero h1 { font-size: 1.9rem !important; color: #1f2328; margin-bottom: 0.3rem; }
.sa-hero p { color: #6e7781; }
.sa-note { color: #8b8f97; font-size: 0.8rem; text-align: center; }
</style>
"""


def inject_css(wide: bool) -> None:
    st.markdown(CSS.replace("__WIDTH__", "1100px" if wide else "780px"), unsafe_allow_html=True)


# ----------------------------------------------------------------------------- cached loaders

def _to_temp(name: str, data: bytes) -> Path:
    path = Path(tempfile.mkdtemp(prefix="safety_agent_")) / Path(name).name
    path.write_bytes(data)
    return path


@st.cache_data(show_spinner=False)
def load_uploaded(reqs: tuple | None, fmea: tuple | None):
    return load_project(_to_temp(*reqs) if reqs else None, _to_temp(*fmea) if fmea else None)


@st.cache_data(show_spinner=False)
def load_examples():
    return load_project(EXAMPLES / "bms_exigences.csv", EXAMPLES / "bms_amdec.csv")


@st.cache_resource(show_spinner=False)
def build_kb_from_paths(paths: tuple[str, ...], _signature: str) -> KnowledgeBase:
    return KnowledgeBase.build(list(paths))


@st.cache_resource(show_spinner=False)
def build_kb_from_uploads(files: tuple[tuple[str, bytes], ...]) -> KnowledgeBase:
    folder = Path(tempfile.mkdtemp(prefix="safety_agent_docs_"))
    for name, data in files:
        (folder / Path(name).name).write_bytes(data)
    return KnowledgeBase.build([folder])


def folder_signature(folder: Path) -> str:
    """Changes when a document is added, removed or modified, so the base is rebuilt."""
    files = sorted(f for f in folder.rglob("*") if f.suffix.lower() in SUPPORTED)
    return ";".join(f"{f.name}:{f.stat().st_mtime_ns}:{f.stat().st_size}" for f in files)


# ----------------------------------------------------------------------------- context

def check_connection(force: bool = False) -> None:
    key = (cfg["base_url"], cfg["model"])
    if force or ss.get("llm_key") != key:
        try:
            available = LLMClient(LLMConfig(base_url=cfg["base_url"], model=cfg["model"])).ping()
            ss.llm_status = ("ok" if cfg["model"] in available else "missing", available)
        except LLMError:
            ss.llm_status = ("down", [])
        ss.llm_key = key


check_connection()
status, available = ss.llm_status
llm = LLMClient(LLMConfig(base_url=cfg["base_url"], model=cfg["model"])) if status == "ok" else DemoLLM()
model_label = cfg["model"] if status == "ok" else "démo"

load_errors: list = []
if cfg["data_mode"] == "Mes fichiers" and (cfg["reqs_file"] or cfg["fmea_file"]):
    project, load_errors = load_uploaded(cfg["reqs_file"], cfg["fmea_file"])
    data_key = tuple((f[0], len(f[1])) for f in (cfg["reqs_file"], cfg["fmea_file"]) if f)
else:
    project, load_errors = load_examples()
    data_key = ("exemple",)

kb, kb_error = None, ""
if cfg["kb_mode"] == "Exemples":
    kb = build_kb_from_paths((str(EXAMPLES / "documents"),), folder_signature(EXAMPLES / "documents"))
elif cfg["kb_mode"] == "Dossier" and cfg["kb_folder"]:
    folder = Path(cfg["kb_folder"])
    if folder.is_dir():
        kb = build_kb_from_paths((str(folder),), folder_signature(folder))
    else:
        kb_error = "Dossier introuvable."
elif cfg["kb_mode"] == "Téléverser" and cfg["kb_files"]:
    kb = build_kb_from_uploads(cfg["kb_files"])

context_key = (data_key, id(kb), cfg["base_url"], cfg["model"], status)
if ss.get("context_key") != context_key:  # data or model changed: agents restart with the visible history
    ss.agents = {}
    ss.context_key = context_key


# ----------------------------------------------------------------------------- helpers

def go(page: str) -> None:
    ss.page = page


def new_conversation() -> None:
    ss.active = None
    ss.page = "chat"


def open_conversation(cid: str) -> None:
    ss.active = cid
    ss.page = "chat"


def get_agent(conv: dict) -> SafetyAgent:
    if conv["id"] not in ss.agents:
        agent = SafetyAgent(llm, project, kb=kb)
        for m in conv["messages"]:  # replay the visible history so the agent keeps the context
            agent.messages.append({"role": m["role"], "content": m["content"]})
        ss.agents[conv["id"]] = agent
    return ss.agents[conv["id"]]


def register(props: list[Proposal]) -> list[str]:
    ids = []
    for p in props:
        pid = proposal_id(p)
        ss.proposals.setdefault(pid, p)
        ids.append(pid)
    return ids


def pending_count() -> int:
    return sum(p.status == "À VALIDER" for p in ss.proposals.values())


def proposal_card(pid: str, where: str) -> None:
    p: Proposal = ss.proposals[pid]
    with st.container(border=True):
        st.markdown(f"**{p.kind.replace('_', ' ').capitalize()}** · `{p.target}` · {p.status.lower()}")
        st.write(p.content)
        if p.rationale:
            st.caption(f"Justification : {p.rationale}")
        if p.data.get("sources"):
            with st.expander("Sources"):
                for s in p.data["sources"]:
                    st.caption(s)
        if p.status == "À VALIDER":
            comment = st.text_input("Commentaire (facultatif)", key=f"c_{where}_{pid}")
            c1, c2, _ = st.columns([1, 1, 3])
            for col, label, icon, decision in ((c1, "Valider", ":material/check:", ACCEPTED),
                                               (c2, "Rejeter", ":material/close:", REJECTED)):
                if col.button(label, icon=icon, key=f"{decision}_{where}_{pid}", disabled=not cfg["user"].strip(),
                              width="stretch"):
                    record_decision(p, decision, cfg["user"], comment, model_label)
                    st.rerun()
            if not cfg["user"].strip():
                st.caption("Renseignez votre nom dans Paramètres pour valider ou rejeter.")


def findings_table(findings, key: str) -> None:
    if not findings:
        st.success("Aucun constat.")
        return
    df = findings_df(findings)
    levels = st.segmented_control("Niveaux", list(LEVEL_LABELS), default=["error", "warning"],
                                  format_func=LEVEL_LABELS.get, selection_mode="multi", key=f"lv_{key}",
                                  label_visibility="collapsed")
    df = df[df["Niveau"].isin(levels or [])].copy()
    df["Niveau"] = df["Niveau"].map(LEVEL_LABELS)
    st.dataframe(df, hide_index=True, width="stretch")


# ----------------------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown(f'<div class="sa-brand">{APP_NAME}</div>', unsafe_allow_html=True)
    st.button("Nouvelle conversation", icon=":material/edit_square:", on_click=new_conversation,
              type="tertiary", key="nav_new", width="stretch")

    if ss.convs:
        st.markdown('<div class="sa-section">Conversations</div>', unsafe_allow_html=True)
        for conv in reversed(ss.convs[-12:]):
            active = ss.page == "chat" and ss.active == conv["id"]
            st.button(conv["title"], key=f"conv_{conv['id']}", on_click=open_conversation, args=(conv["id"],),
                      type="secondary" if active else "tertiary", width="stretch")

    st.markdown('<div class="sa-section">Outils</div>', unsafe_allow_html=True)
    n_pending = pending_count()
    for page, label, icon in (
        ("checks", "Contrôles automatiques", ":material/fact_check:"),
        ("review", "Relecture des exigences", ":material/rate_review:"),
        ("fmea", "Modes de défaillance", ":material/report:"),
        ("proposals", f"Propositions{f' ({n_pending})' if n_pending else ''}", ":material/task_alt:"),
        ("docs", "Documents", ":material/folder_open:"),
        ("settings", "Paramètres", ":material/settings:"),
    ):
        st.button(label, icon=icon, key=f"nav_{page}", on_click=go, args=(page,),
                  type="secondary" if ss.page == page else "tertiary", width="stretch")

    color = "#2da44e" if status == "ok" else "#d29922"
    state = f"{cfg['model']}" if status == "ok" else "Mode démonstration"
    st.markdown(f'<div class="sa-section">Session</div>'
                f'<div class="sa-status"><span class="sa-dot" style="background:{color}"></span>{state}</div>'
                f'<div class="sa-status">{cfg["user"] or "Utilisateur non renseigné"}</div>',
                unsafe_allow_html=True)


# ----------------------------------------------------------------------------- pages

def page_chat() -> None:
    inject_css(wide=False)
    conv = next((c for c in ss.convs if c["id"] == ss.active), None)
    pending_question = ss.pop("pending_question", None)

    hero = st.empty()
    if conv is None and not pending_question:
        hero_box = hero.container()
        hero_box.markdown(f'<div class="sa-hero"><h1>Comment puis-je vous aider ?</h1>'
                    f'<p>Exigences, AMDEC, procédures internes et questions ISO 26262.</p></div>',
                    unsafe_allow_html=True)
        cols = hero_box.columns(2)
        for i, (label, question) in enumerate(SUGGESTIONS):
            if cols[i % 2].button(label, key=f"sugg_{i}", width="stretch"):
                ss.pending_question = question
                st.rerun()
        if status != "ok":
            hero_box.markdown('<p class="sa-note">Aucun modèle connecté : les réponses sont simulées. '
                        'Démarrez Ollama ou réglez le serveur dans Paramètres.</p>', unsafe_allow_html=True)
    else:
        for m in (conv["messages"] if conv else []):
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                if m.get("tools"):
                    with st.expander("Détails"):
                        for name, args in m["tools"]:
                            st.caption(f"{name} {args or ''}")

    question = st.chat_input("Posez votre question") or pending_question
    if question:
        if conv is None:
            conv = {"id": uuid.uuid4().hex[:8], "title": question[:48] + ("…" if len(question) > 48 else ""),
                    "messages": []}
            ss.convs.append(conv)
            ss.active = conv["id"]
        hero.empty()
        agent = get_agent(conv)
        conv["messages"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        tools: list = []
        agent.on_tool = lambda name, args: tools.append((name, args))
        before = len(agent.proposals)
        with st.chat_message("assistant"), st.spinner("Réflexion…"):
            try:
                answer = agent.ask(question)
            except LLMError as e:
                answer = f"Le modèle ne répond pas : {e}"
        if register(agent.proposals[before:]):
            answer += "\n\n*Des propositions ont été enregistrées : voir « Propositions ».*"
        conv["messages"].append({"role": "assistant", "content": answer, "tools": tools})
        st.rerun()


def page_checks() -> None:
    inject_css(wide=True)
    st.title("Contrôles automatiques")
    st.caption("Règles fixes et reproductibles, sans IA.")
    findings = load_errors + run_all_checks(project)
    count = {lv: sum(f.level == lv for f in findings) for lv in Level}
    aps = fmea_df(project)["AP"].value_counts() if project.fmea else pd.Series(dtype=int)
    c = st.columns(4)
    c[0].metric("Erreurs", count[Level.ERROR])
    c[1].metric("Avertissements", count[Level.WARNING])
    c[2].metric("Informations", count[Level.INFO])
    c[3].metric("Priorité d'action H", int(aps.get("H", 0)))
    findings_table(findings, "checks")
    if project.requirements:
        st.subheader("Traçabilité")
        st.dataframe(matrix_df(project), hide_index=True, width="stretch")
    with st.expander("Exigences"):
        st.dataframe(requirements_df(project), hide_index=True, width="stretch")
    with st.expander("AMDEC"):
        st.dataframe(fmea_df(project), hide_index=True, width="stretch")
    st.download_button("Télécharger le rapport", markdown_report(project, findings), "rapport_controles.md",
                       "text/markdown", icon=":material/download:")


def page_review() -> None:
    inject_css(wide=True)
    st.title("Relecture des exigences")
    st.caption("Évaluation selon l'ISO 26262-8 §6.4 et proposition de reformulation. Environ 2 minutes par exigence "
               "sans carte graphique.")
    findings = run_all_checks(project)
    flagged = sorted({f.target for f in findings if f.code.startswith("REQ-02") and f.target in project.requirements})
    ids = st.multiselect("Exigences à relire", list(project.requirements), default=flagged[:2])
    if st.button("Lancer la relecture", type="primary", disabled=not ids):
        bar = st.progress(0.0, "Relecture…")
        res_findings, res_props = review_requirements(
            llm, project, ids, kb=kb,
            on_progress=lambda n, t, rid: bar.progress((n - 1) / t, f"Relecture de {rid} ({n}/{t})…"))
        bar.empty()
        ss.review_res = (res_findings, register(res_props))
    if ss.review_res:
        res_findings, pids = ss.review_res
        findings_table(res_findings, "review")
        for pid in pids:
            proposal_card(pid, "review")


def page_fmea() -> None:
    inject_css(wide=True)
    st.title("Modes de défaillance")
    st.caption("Propositions à partir des mots-guides et de vos AMDEC passées. Environ 4 minutes sans carte graphique.")
    with st.form("suggest_form", border=False):
        c1, c2 = st.columns(2)
        item = c1.text_input("Élément", "Capteur de courant pack")
        function = c2.text_input("Fonction", "Mesurer le courant batterie")
        context = st.text_input("Contexte", "BMS 400 V, véhicule électrique")
        submitted = st.form_submit_button("Proposer", type="primary")
    if submitted:
        with st.spinner("Analyse en cours…"):
            ss.suggest_ids = register(suggest_failure_modes(llm, project, item, function, context, kb=kb))
    if ss.suggest_ids:
        rows = []
        for pid in ss.suggest_ids:
            d = ss.proposals[pid].data
            try:
                ap = action_priority(int(d["S"]), int(d["O"]), int(d["D"]))
            except (KeyError, ValueError, TypeError):
                ap = "?"
            rows.append({"Mode": d.get("mode"), "Effet": d.get("effet"), "Cause": d.get("cause"),
                         "S": d.get("S"), "O": d.get("O"), "D": d.get("D"), "AP": ap})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "p.csv"
            write_proposals_csv([ss.proposals[p] for p in ss.suggest_ids], out)
            st.download_button("Exporter au format AMDEC (CSV)", out.read_bytes(), "propositions_amdec.csv",
                               "text/csv", icon=":material/download:")
        for pid in ss.suggest_ids:
            proposal_card(pid, "suggest")


def page_proposals() -> None:
    inject_css(wide=True)
    st.title("Propositions")
    pending = [pid for pid, p in ss.proposals.items() if p.status == "À VALIDER"]
    st.subheader(f"À valider ({len(pending)})")
    if not pending:
        st.caption("Aucune proposition en attente dans cette session.")
    for pid in pending:
        proposal_card(pid, "all")
    st.subheader("Journal des décisions")
    journal = read_journal()
    if journal:
        jdf = pd.DataFrame(journal)
        st.dataframe(jdf[["horodatage", "utilisateur", "decision", "type", "cible", "proposition", "commentaire"]],
                     hide_index=True, width="stretch")
        st.download_button("Télécharger le journal", jdf.to_csv(sep=";", index=False).encode("utf-8-sig"),
                           "journal_validations.csv", "text/csv", icon=":material/download:")
    else:
        st.caption("Aucune décision enregistrée pour l'instant.")


def page_docs() -> None:
    inject_css(wide=True)
    st.title("Documents")
    if not kb:
        st.info("Aucune base documentaire. Choisissez une source dans Paramètres.")
        return
    st.caption(f"{len(kb.documents)} document(s), {len(kb.chunks)} extraits.")
    query = st.text_input("Rechercher dans les documents", placeholder="ex. dérive du capteur de courant")
    if query:
        hits = kb.search(query, k=5, llm=llm if status == "ok" else None)
        if not hits:
            st.caption("Aucun extrait trouvé.")
        for n, c in enumerate(hits, 1):
            with st.container(border=True):
                st.markdown(f"**[{n}] {c.citation()}**")
                st.write(c.text)
    with st.expander("Documents indexés"):
        st.dataframe(pd.DataFrame(kb.documents)[["path", "chunks"]].rename(
            columns={"path": "Document", "chunks": "Extraits"}), hide_index=True, width="stretch")


def page_settings() -> None:
    inject_css(wide=False)
    st.title("Paramètres")
    before = dict(cfg)

    st.subheader("Utilisateur")
    cfg["user"] = st.text_input("Votre nom", cfg["user"], help="Enregistré dans le journal des décisions.")

    st.subheader("Modèle")
    cfg["base_url"] = st.text_input("Adresse du serveur", cfg["base_url"])
    cfg["model"] = st.text_input("Modèle", cfg["model"])
    if st.button("Tester la connexion"):
        check_connection(force=True)
        st.rerun()
    if status == "ok":
        st.success(f"Connecté à {cfg['model']}.")
    elif status == "missing":
        st.warning(f"Modèle « {cfg['model']} » absent du serveur. Disponibles : {', '.join(available) or 'aucun'}.")
    else:
        st.warning("Serveur injoignable : mode démonstration (réponses simulées).")

    st.subheader("Exigences et AMDEC")
    modes = ["Exemple", "Mes fichiers"]
    cfg["data_mode"] = st.radio("Source", modes, index=modes.index(cfg["data_mode"]), horizontal=True)
    if cfg["data_mode"] == "Mes fichiers":
        up_r = st.file_uploader("Exigences (.csv, .xlsx)", type=["csv", "xlsx"])
        up_f = st.file_uploader("AMDEC (.csv, .xlsx)", type=["csv", "xlsx"])
        if up_r:
            cfg["reqs_file"] = (up_r.name, up_r.getvalue())
        if up_f:
            cfg["fmea_file"] = (up_f.name, up_f.getvalue())
        loaded = [f[0] for f in (cfg["reqs_file"], cfg["fmea_file"]) if f]
        st.caption("Fichiers chargés : " + (", ".join(loaded) if loaded else "aucun (l'exemple reste utilisé)"))
    st.caption(f"{len(project.requirements)} exigences, {len(project.fmea)} lignes AMDEC.")
    for f in load_errors:
        st.warning(f"{f.target} : {f.message}")

    st.subheader("Base documentaire")
    kb_modes = ["Exemples", "Dossier", "Téléverser", "Aucune"]
    cfg["kb_mode"] = st.radio("Documents", kb_modes, index=kb_modes.index(cfg["kb_mode"]), horizontal=True)
    if cfg["kb_mode"] == "Dossier":
        cfg["kb_folder"] = st.text_input("Chemin du dossier", cfg["kb_folder"],
                                         help="Dossier sur la machine qui fait tourner la page.")
    elif cfg["kb_mode"] == "Téléverser":
        docs = st.file_uploader("Documents", type=[s.lstrip(".") for s in sorted(SUPPORTED)],
                                accept_multiple_files=True)
        if docs:
            cfg["kb_files"] = tuple((d.name, d.getvalue()) for d in docs)
    if kb_error:
        st.error(kb_error)
    if kb:
        st.caption(f"{len(kb.documents)} document(s), {len(kb.chunks)} extraits.")
        for d in (d for d in kb.documents if "error" in d):
            st.warning(f"{d['path']} illisible : {d['error']}")
    if cfg != before:  # apply the new settings to the whole page right away
        st.rerun()


PAGES = {"chat": page_chat, "checks": page_checks, "review": page_review, "fmea": page_fmea,
         "proposals": page_proposals, "docs": page_docs, "settings": page_settings}
PAGES.get(ss.page, page_chat)()
