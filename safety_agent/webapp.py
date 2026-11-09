"""Web page for safety-agent (Streamlit).

Run with:  safety-agent web            (this PC only)
           safety-agent web --partage  (colleagues open http://<pc-name>:8501)
"""
from __future__ import annotations

import sys
import tempfile
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

EXAMPLES = ROOT / "examples"
LEVEL_LABELS = {"error": "🔴 Erreur", "warning": "🟠 Avertissement", "info": "🔵 Info"}

st.set_page_config(page_title="Safety Agent – ISO 26262", page_icon="🛡️", layout="wide")
ss = st.session_state
ss.setdefault("proposals", {})       # id -> Proposal
ss.setdefault("chat", [])            # [{"role", "content", "tools"}]
ss.setdefault("review", None)        # (findings, [proposal ids])
ss.setdefault("suggest_ids", [])         # [proposal ids]


# ----------------------------------------------------------------------------- cached loaders

def _to_temp(name: str, data: bytes) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="safety_agent_"))
    path = folder / Path(name).name
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


# ----------------------------------------------------------------------------- sidebar

with st.sidebar:
    st.title("🛡️ Safety Agent")
    st.caption("Assistant IA AMDEC et exigences ISO 26262")

    user = st.text_input("👤 Votre nom", key="user", help="Obligatoire pour valider ou rejeter une proposition.")

    st.subheader("🧠 Modèle d'IA")
    base_url = st.text_input("Adresse du serveur", LLMConfig().base_url)
    model = st.text_input("Modèle", "qwen2.5:7b")
    if st.button("Tester la connexion") or "llm_status" not in ss or ss.get("llm_key") != (base_url, model):
        client = LLMClient(LLMConfig(base_url=base_url, model=model))
        try:
            available = client.ping()
            ok = model in available
            ss.llm_status = ("ok" if ok else "missing", available)
        except LLMError:
            ss.llm_status = ("down", [])
        ss.llm_key = (base_url, model)
    status, available = ss.llm_status
    if status == "ok":
        st.success(f"Connecté : {model}")
        llm = LLMClient(LLMConfig(base_url=base_url, model=model))
    else:
        if status == "missing":
            st.warning(f"Modèle « {model} » absent. Disponibles : {', '.join(available) or 'aucun'}")
        else:
            st.warning("Serveur injoignable. Lancez Ollama.")
        st.info("Mode démo : réponses simulées, pas d'IA.")
        llm = DemoLLM()

    st.subheader("📂 Exigences et AMDEC")
    data_mode = st.radio("Source", ["Exemple (BMS)", "Mes fichiers"], horizontal=True, label_visibility="collapsed")
    load_errors = []
    if data_mode == "Mes fichiers":
        up_reqs = st.file_uploader("Exigences (.csv, .xlsx)", type=["csv", "xlsx"])
        up_fmea = st.file_uploader("AMDEC (.csv, .xlsx)", type=["csv", "xlsx"])
        if up_reqs or up_fmea:
            data_key = tuple((f.name, f.size) for f in (up_reqs, up_fmea) if f)
            try:
                project, load_errors = load_uploaded(
                    (up_reqs.name, up_reqs.getvalue()) if up_reqs else None,
                    (up_fmea.name, up_fmea.getvalue()) if up_fmea else None)
            except ValueError as e:
                st.error(str(e))
                st.stop()
        else:
            st.info("Déposez au moins un fichier.")
            st.stop()
    else:
        data_key = ("exemple",)
        project, load_errors = load_examples()
    st.caption(f"{len(project.requirements)} exigences · {len(project.fmea)} lignes AMDEC")

    st.subheader("📚 Base documentaire")
    kb_mode = st.radio("Documents", ["Exemples", "Dossier", "Téléverser", "Aucune"], horizontal=True,
                       label_visibility="collapsed")
    kb = None
    with st.spinner("Lecture des documents…"):
        if kb_mode == "Exemples":
            kb = build_kb_from_paths((str(EXAMPLES / "documents"),), folder_signature(EXAMPLES / "documents"))
        elif kb_mode == "Dossier":
            folder = st.text_input("Chemin du dossier", help="Dossier sur la machine qui fait tourner la page.")
            if folder and Path(folder).is_dir():
                kb = build_kb_from_paths((folder,), folder_signature(Path(folder)))
            elif folder:
                st.error("Dossier introuvable.")
        elif kb_mode == "Téléverser":
            docs = st.file_uploader("Documents", type=[s.lstrip(".") for s in sorted(SUPPORTED)],
                                    accept_multiple_files=True)
            if docs:
                kb = build_kb_from_uploads(tuple((d.name, d.getvalue()) for d in docs))
    if kb:
        failed = [d for d in kb.documents if "error" in d]
        st.caption(f"{len(kb.documents)} document(s) · {len(kb.chunks)} extraits")
        for d in failed:
            st.warning(f"{d['path']} illisible : {d['error']}")


# ----------------------------------------------------------------------------- helpers

def register(props: list[Proposal]) -> list[str]:
    ids = []
    for p in props:
        pid = proposal_id(p)
        ss.proposals.setdefault(pid, p)
        ids.append(pid)
    return ids


def proposal_card(pid: str, where: str) -> None:
    p: Proposal = ss.proposals[pid]
    icon = {"À VALIDER": "🟡", ACCEPTED: "✅", REJECTED: "❌"}.get(p.status, "🟡")
    with st.container(border=True):
        st.markdown(f"{icon} **{p.kind.replace('_', ' ')}** · `{p.target}` · *{p.status}*")
        st.write(p.content)
        if p.rationale:
            st.caption(f"Justification : {p.rationale}")
        if p.data.get("sources"):
            with st.expander("Sources envoyées au modèle"):
                for s in p.data["sources"]:
                    st.write(s)
        if p.status == "À VALIDER":
            comment = st.text_input("Commentaire (facultatif)", key=f"c_{where}_{pid}")
            c1, c2, _ = st.columns([1, 1, 4])
            for col, label, decision in ((c1, "✅ Valider", ACCEPTED), (c2, "❌ Rejeter", REJECTED)):
                if col.button(label, key=f"{decision}_{where}_{pid}", disabled=not user.strip()):
                    record_decision(p, decision, user, comment, model if status == "ok" else "démo")
                    st.rerun()
            if not user.strip():
                st.caption("Indiquez votre nom dans le panneau de gauche pour valider ou rejeter.")


def show_findings(findings, key: str) -> None:
    if not findings:
        st.success("Aucun constat.")
        return
    df = findings_df(findings)
    levels = st.multiselect("Niveaux affichés", list(LEVEL_LABELS), default=["error", "warning"],
                            format_func=LEVEL_LABELS.get, key=f"lv_{key}")
    df = df[df["Niveau"].isin(levels)].copy()
    df["Niveau"] = df["Niveau"].map(LEVEL_LABELS)
    st.dataframe(df, hide_index=True, width="stretch")


# ----------------------------------------------------------------------------- page

if isinstance(llm, DemoLLM):
    st.warning("**Mode démo** : aucun modèle connecté, les réponses de l'IA sont simulées. "
               "Les contrôles automatiques et la recherche documentaire fonctionnent normalement.")

tabs = st.tabs(["🔎 Contrôles", "✍️ Relecture IA", "⚠️ Modes de défaillance", "💬 Agent",
                "✅ Propositions", "📚 Documents"])

# --- 1. Automatic checks
with tabs[0]:
    findings = load_errors + run_all_checks(project)
    count = {lv: sum(f.level == lv for f in findings) for lv in Level}
    aps = fmea_df(project)["AP"].value_counts() if project.fmea else {}
    c = st.columns(4)
    c[0].metric("Erreurs", count[Level.ERROR])
    c[1].metric("Avertissements", count[Level.WARNING])
    c[2].metric("Informations", count[Level.INFO])
    c[3].metric("Lignes AMDEC en priorité H", int(aps.get("H", 0)) if len(aps) else 0)
    show_findings(findings, "checks")
    if project.requirements:
        st.subheader("Matrice de traçabilité")
        st.dataframe(matrix_df(project), hide_index=True, width="stretch")
    with st.expander("Voir les exigences"):
        st.dataframe(requirements_df(project), hide_index=True, width="stretch")
    with st.expander("Voir l'AMDEC"):
        st.dataframe(fmea_df(project), hide_index=True, width="stretch")
    st.download_button("⬇️ Télécharger le rapport (Markdown)", markdown_report(project, findings),
                       "rapport_controles.md", "text/markdown")

# --- 2. Requirement review
with tabs[1]:
    st.write("L'IA évalue chaque exigence selon l'ISO 26262-8 §6.4 et propose une reformulation.")
    flagged = sorted({f.target for f in findings if f.code.startswith("REQ-02") and f.target in project.requirements})
    ids = st.multiselect("Exigences à relire", list(project.requirements), default=flagged[:2],
                         help="Par défaut : celles où les contrôles automatiques ont trouvé un problème de formulation.")
    if st.button("Lancer la relecture", type="primary", disabled=not ids):
        bar = st.progress(0.0, "Relecture…")
        res_findings, res_props = review_requirements(
            llm, project, ids, kb=kb,
            on_progress=lambda n, t, rid: bar.progress((n - 1) / t, f"Relecture de {rid} ({n}/{t})…"))
        bar.empty()
        ss.review = (res_findings, register(res_props))
    if ss.review:
        res_findings, pids = ss.review
        show_findings(res_findings, "review")
        for pid in pids:
            proposal_card(pid, "review")

# --- 3. Failure mode suggestions
with tabs[2]:
    with st.form("suggest_form"):
        item = st.text_input("Élément", "Capteur de courant pack")
        function = st.text_input("Fonction", "Mesurer le courant batterie")
        context = st.text_input("Contexte", "BMS 400 V, véhicule électrique")
        go = st.form_submit_button("Proposer des modes de défaillance", type="primary")
    if go:
        with st.spinner("L'IA analyse… (plusieurs minutes sans carte graphique)"):
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
            st.download_button("⬇️ Exporter au format AMDEC (CSV)", out.read_bytes(), "propositions_amdec.csv", "text/csv")
        for pid in ss.suggest_ids:
            proposal_card(pid, "suggest")

# --- 4. Agent
with tabs[3]:
    agent_key = (data_key, id(kb), base_url, model, status)
    if ss.get("agent_key") != agent_key:
        ss.agent = SafetyAgent(llm, project, kb=kb)
        ss.agent_key = agent_key
        ss.chat = []
    col1, col2 = st.columns([4, 1])
    col1.write("Posez vos questions sur les exigences, l'AMDEC et les documents. L'agent cite ses sources.")
    if col2.button("🗑️ Nouvelle conversation"):
        ss.agent = SafetyAgent(llm, project, kb=kb)
        ss.chat = []
        st.rerun()
    for msg in ss.chat:
        with st.chat_message(msg["role"]):
            if msg.get("tools"):
                with st.expander(f"🔧 {len(msg['tools'])} outil(s) utilisé(s)"):
                    for name, args in msg["tools"]:
                        st.code(f"{name} {args or ''}", language=None)
            st.markdown(msg["content"])
    question = st.chat_input("Ex. : Quelles lignes AMDEC de gravité 9 ou 10 n'ont pas d'action ?")
    if question:
        ss.chat.append({"role": "user", "content": question})
        tools: list = []
        ss.agent.on_tool = lambda name, args: tools.append((name, args))
        before = len(ss.agent.proposals)
        with st.spinner("L'agent réfléchit…"):
            try:
                answer = ss.agent.ask(question)
            except LLMError as e:
                answer = f"⚠️ {e}"
        new = register(ss.agent.proposals[before:])
        if new:
            answer += f"\n\n*{len(new)} proposition(s) enregistrée(s) : voir l'onglet « Propositions ».*"
        ss.chat.append({"role": "assistant", "content": answer, "tools": tools})
        st.rerun()

# --- 5. Proposals and journal
with tabs[4]:
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
        st.download_button("⬇️ Télécharger le journal (CSV)", jdf.to_csv(sep=";", index=False).encode("utf-8-sig"),
                           "journal_validations.csv", "text/csv")
    else:
        st.caption("Aucune décision enregistrée pour l'instant.")

# --- 6. Document search
with tabs[5]:
    if not kb:
        st.info("Aucune base documentaire : choisissez une source dans le panneau de gauche.")
    else:
        st.dataframe(pd.DataFrame(kb.documents)[["path", "chunks"]].rename(
            columns={"path": "Document", "chunks": "Extraits"}), hide_index=True)
        query = st.text_input("Rechercher dans les documents", placeholder="ex. dérive capteur de courant")
        if query:
            hits = kb.search(query, k=5, llm=llm if status == "ok" else None)
            if not hits:
                st.caption("Aucun extrait trouvé.")
            for n, c in enumerate(hits, 1):
                with st.container(border=True):
                    st.markdown(f"**[{n}] {c.citation()}**")
                    st.write(c.text)
