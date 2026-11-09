"""Command line: safety-agent {check,review,suggest,chat}."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .checks import run_all_checks
from .llm import LLMClient, LLMConfig, LLMError
from .loaders import load_project
from .models import Level
from .report import markdown_report, write_proposals_csv


def _llm(args) -> LLMClient:
    cfg = LLMConfig()
    if args.base_url:
        cfg.base_url = args.base_url
    if args.model:
        cfg.model = args.model
    return LLMClient(cfg)


def _write(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"Rapport écrit : {out}", file=sys.stderr)
    else:
        print(text)


def _kb(args):
    if not getattr(args, "kb", None):
        return None
    from .knowledge import KnowledgeBase

    kb = KnowledgeBase.load(args.kb)
    print(f"Base documentaire : {len(kb.chunks)} extraits de {len(kb.documents)} document(s)", file=sys.stderr)
    return kb


def cmd_index(args) -> int:
    from .knowledge import KnowledgeBase

    llm = _llm(args) if args.embed_model else None
    kb = KnowledgeBase.build(args.docs, llm=llm, embed_model=args.embed_model,
                             on_progress=lambda name: print(f"  lecture {name}", file=sys.stderr))
    kb.save(args.out)
    for d in kb.documents:
        status = f"ERREUR : {d['error']}" if "error" in d else f"{d['chunks']} extrait(s)"
        print(f"  {d['path']} : {status}", file=sys.stderr)
    print(f"Base écrite : {args.out} ({len(kb.chunks)} extraits)", file=sys.stderr)
    return 0


def cmd_search(args) -> int:
    kb = _kb(args)
    llm = _llm(args) if kb.embed_model else None
    for n, c in enumerate(kb.search(args.query, k=args.k, llm=llm), 1):
        print(f"[{n}] {c.citation()}\n    {c.text[:400]}\n")
    return 0


def cmd_check(args) -> int:
    project, findings = load_project(args.reqs, args.fmea)
    findings += run_all_checks(project)
    if args.format == "json":
        _write(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2), args.out)
    else:
        _write(markdown_report(project, findings), args.out)
    errors = sum(f.level == Level.ERROR for f in findings)
    warnings = sum(f.level == Level.WARNING for f in findings)
    print(f"{errors} erreur(s), {warnings} avertissement(s).", file=sys.stderr)
    if args.fail_on == "error" and errors:
        return 1
    if args.fail_on == "warning" and (errors or warnings):
        return 1
    return 0


def cmd_review(args) -> int:
    from .ai import review_requirements

    project, findings = load_project(args.reqs, args.fmea)
    findings += run_all_checks(project)
    ids = args.ids.split(",") if args.ids else None
    unknown = [i for i in ids or [] if i not in project.requirements]
    if unknown:
        print(f"Exigence(s) inconnue(s) : {', '.join(unknown)}", file=sys.stderr)
        return 2
    ai_findings, proposals = review_requirements(
        _llm(args), project, ids, on_progress=lambda n, t, rid: print(f"[{n}/{t}] relecture {rid}...", file=sys.stderr),
        kb=_kb(args))
    _write(markdown_report(project, findings + ai_findings, proposals, "Relecture des exigences de sécurité"), args.out)
    return 0


def cmd_suggest(args) -> int:
    from .ai import suggest_failure_modes

    project, _ = load_project(args.reqs, args.fmea)
    proposals = suggest_failure_modes(_llm(args), project, args.item, args.function or "", args.context or "",
                                      kb=_kb(args))
    if args.csv:
        write_proposals_csv(proposals, args.csv)
        print(f"{len(proposals)} proposition(s) écrite(s) dans {args.csv}", file=sys.stderr)
    for p in proposals:
        print(f"- {p.content}\n  Justification : {p.rationale}\n")
    return 0


def cmd_chat(args) -> int:
    from .agent import SafetyAgent

    project, _ = load_project(args.reqs, args.fmea)
    agent = SafetyAgent(_llm(args), project, on_tool=lambda n, a: print(f"  · outil {n} {a or ''}", file=sys.stderr),
                        kb=_kb(args))
    questions = [args.question] if args.question else None
    if not questions:
        print("Agent sûreté prêt. Posez vos questions (ligne vide ou Ctrl-D pour quitter).", file=sys.stderr)
    while True:
        if questions is not None:
            if not questions:
                break
            q = questions.pop()
        else:
            try:
                q = input("\n> ").strip()
            except EOFError:
                break
            if not q:
                break
        print("\n" + agent.ask(q))
    if agent.proposals:
        out = args.out or "propositions_agent.md"
        Path(out).write_text(markdown_report(project, [], agent.proposals, "Propositions de l'agent"), encoding="utf-8")
        print(f"\n{len(agent.proposals)} proposition(s) à valider écrite(s) dans {out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="safety-agent", description="Assistant IA AMDEC et exigences ISO 26262")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, llm=True):
        p.add_argument("--reqs", help="Fichier d'exigences (.csv ou .xlsx)")
        p.add_argument("--fmea", help="Fichier AMDEC (.csv ou .xlsx)")
        p.add_argument("--out", help="Fichier de sortie (Markdown)")
        if llm:
            p.add_argument("--kb", help="Base documentaire créée avec la commande 'index' (.json)")
            p.add_argument("--base-url", help="URL du serveur LLM (défaut : $SAFETY_AGENT_BASE_URL ou Ollama local)")
            p.add_argument("--model", help="Nom du modèle (défaut : $SAFETY_AGENT_MODEL ou qwen2.5:14b)")

    p = sub.add_parser("check", help="Contrôles automatiques, sans IA")
    common(p, llm=False)
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.add_argument("--fail-on", choices=["error", "warning", "never"], default="never",
                   help="Code de retour 1 si anomalies (pour l'intégration continue)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("review", help="Relecture IA des exigences (ISO 26262-8 §6)")
    common(p)
    p.add_argument("--ids", help="Liste d'identifiants séparés par des virgules (défaut : toutes)")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("suggest", help="Proposer des modes de défaillance pour un élément")
    common(p)
    p.add_argument("--item", required=True, help="Élément (ex. 'Capteur de courant')")
    p.add_argument("--function", help="Fonction de l'élément")
    p.add_argument("--context", help="Contexte (système, environnement...)")
    p.add_argument("--csv", help="Export CSV des propositions au format AMDEC")
    p.set_defaults(func=cmd_suggest)

    p = sub.add_parser("chat", help="Agent conversationnel sur les données")
    common(p)
    p.add_argument("--question", "-q", help="Question unique (sinon mode interactif)")
    p.set_defaults(func=cmd_chat)

    p = sub.add_parser("index", help="Créer la base documentaire (procédures, AMDEC passées, REX)")
    p.add_argument("docs", nargs="+", help="Dossiers ou fichiers (.pdf .docx .xlsx .csv .md .txt)")
    p.add_argument("--out", default="base_documentaire.json", help="Fichier de sortie")
    p.add_argument("--embed-model", help="Modèle d'embeddings pour la recherche sémantique (ex. bge-m3). "
                                         "Sans cette option : recherche par mots-clés uniquement")
    p.add_argument("--base-url", help="URL du serveur LLM")
    p.add_argument("--model", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", help="Chercher dans la base documentaire")
    p.add_argument("query", help="Question ou mots-clés")
    p.add_argument("--kb", default="base_documentaire.json")
    p.add_argument("-k", type=int, default=5, help="Nombre d'extraits")
    p.add_argument("--base-url", help="URL du serveur LLM")
    p.add_argument("--model", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_search)

    args = parser.parse_args(argv)
    if args.command not in {"index", "search"} and not (args.reqs or args.fmea):
        parser.error("indiquez au moins --reqs ou --fmea")
    try:
        return args.func(args)
    except (LLMError, ValueError, FileNotFoundError) as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
