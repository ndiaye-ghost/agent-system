"""Company knowledge base (RAG): procedures, guides, past FMEAs, lessons learned.

Documents are split into short passages ("chunks") and stored in a JSON index.
At question time the most relevant passages are found and given to the model,
which cites them as [1], [2]...

Search works in two ways, combined when both are available:
- keyword search (BM25): pure Python, no model needed, works on any PC;
- semantic search (embeddings): optional, needs an embedding model on the
  LLM server (e.g. `ollama pull bge-m3`), better for paraphrases.

Supported files: .pdf, .docx, .xlsx, .csv, .md, .txt
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import unicodedata
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree

SUPPORTED = {".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".md", ".txt"}
MAX_CHARS = 1000

_STOPWORDS = set("""
le la les un une des du de d l au aux et ou en dans sur pour par avec sans ce cet cette ces qui que quoi dont
est sont etre a ont avoir il elle ils elles on se sa son ses leur leurs ne pas plus doit doivent tout tous
the a an of to in on for by with and or is are be shall must this that these those it its from as at
""".split())


@dataclass
class Chunk:
    id: str
    source: str
    location: str
    text: str
    embedding: list[float] | None = None

    def citation(self) -> str:
        return f"{self.source} — {self.location}" if self.location else self.source


# ----------------------------------------------------------------------------- extraction

def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", _norm(text))
    out = []
    for t in tokens:
        if t in _STOPWORDS or len(t) < 2:
            continue
        if len(t) > 4 and t[-1] in "sx" and not t[-2].isdigit():  # light plural stemming
            t = t[:-1]
        out.append(t)
    return out


def _paragraphs_docx(path: Path) -> list[tuple[str, str]]:
    """(section, paragraph) pairs from a .docx, using only the standard library."""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    w = "{%s}" % ns["w"]
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    body = root.find("w:body", ns)
    out, section = [], ""
    for el in body if body is not None else []:
        if el.tag == w + "p":
            text = "".join(t.text or "" for t in el.iter(w + "t")).strip()
            if not text:
                continue
            style = el.find("w:pPr/w:pStyle", ns)
            style_name = (style.get(w + "val") if style is not None else "") or ""
            if re.match(r"(heading|titre|title)", style_name, re.I):
                section = text
            else:
                out.append((section, text))
        elif el.tag == w + "tbl":
            for row in el.iter(w + "tr"):
                cells = ["".join(t.text or "" for t in c.iter(w + "t")).strip() for c in row.iter(w + "tc")]
                if any(cells):
                    out.append((section, " | ".join(cells)))
    return out


def _paragraphs_text(path: Path) -> list[tuple[str, str]]:
    out, section, buf = [], "", []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        heading = re.match(r"^\s*#{1,6}\s+(.*)", line)
        if heading or not line.strip():
            if buf:
                out.append((section, " ".join(buf)))
                buf = []
            if heading:
                section = heading.group(1).strip()
            continue
        buf.append(line.strip())
    if buf:
        out.append((section, " ".join(buf)))
    return out


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts, cur = [], ""
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        while len(sentence) > max_chars:  # no punctuation: hard split
            parts.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if cur and len(cur) + len(sentence) + 1 > max_chars:
            parts.append(cur)
            cur = ""
        cur = f"{cur} {sentence}".strip()
    if cur:
        parts.append(cur)
    return parts


def _group(paragraphs: list[tuple[str, str]], location_prefix: str = "") -> list[tuple[str, str]]:
    """Merge consecutive paragraphs of the same section into chunks of ~MAX_CHARS."""
    chunks, cur_sec, cur = [], None, ""
    for section, para in paragraphs:
        for piece in _split_long(para, MAX_CHARS):
            if cur and (section != cur_sec or len(cur) + len(piece) + 1 > MAX_CHARS):
                chunks.append((cur_sec, cur))
                cur = ""
            cur_sec = section
            cur = f"{cur}\n{piece}".strip()
    if cur:
        chunks.append((cur_sec, cur))
    loc = lambda s: " / ".join(x for x in (location_prefix, s) if x)  # noqa: E731
    return [(loc(sec or ""), (f"[{sec}] " if sec else "") + text) for sec, text in chunks]


def extract(path: Path) -> list[tuple[str, str]]:
    """Return (location, text) passages for one file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader  # optional dependency

        out = []
        for n, page in enumerate(PdfReader(str(path)).pages, 1):
            text = page.extract_text() or ""
            paras = [("", re.sub(r"\s+", " ", p).strip()) for p in re.split(r"\n\s*\n", text) if p.strip()]
            out += [(f"page {n}" + (f" / {loc}" if loc else ""), t) for loc, t in _group(paras)]
        return out
    if suffix == ".docx":
        return _group(_paragraphs_docx(path))
    if suffix in {".md", ".txt"}:
        return _group(_paragraphs_text(path))
    if suffix in {".csv", ".xlsx", ".xlsm"}:
        from .loaders import _read_rows

        out = []
        for n, row in enumerate(_read_rows(path), 2):  # line 1 = header
            text = " | ".join(f"{k}: {v}" for k, v in row.items() if k and v and str(v).strip())
            if text:
                out += [(f"ligne {n}", piece) for piece in _split_long(text, MAX_CHARS)]
        return out
    raise ValueError(f"Format non pris en charge : {path.name}")


# ----------------------------------------------------------------------------- index

@dataclass
class KnowledgeBase:
    chunks: list[Chunk] = field(default_factory=list)
    documents: list[dict] = field(default_factory=list)  # path, sha256, chunks: for configuration management
    embed_model: str | None = None
    created: str = ""

    # ---- build / persist
    @classmethod
    def build(cls, paths: list[str | Path], llm=None, embed_model: str | None = None,
              on_progress=None) -> "KnowledgeBase":
        files: list[Path] = []
        for p in map(Path, paths):
            if p.is_dir():
                files += sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED and not f.name.startswith("~$"))
            elif p.exists():
                files.append(p)
            else:
                raise FileNotFoundError(p)
        kb = cls(embed_model=embed_model, created=dt.datetime.now(dt.timezone.utc).isoformat())
        for f in files:
            if on_progress:
                on_progress(f.name)
            try:
                passages = extract(f)
            except Exception as e:  # one unreadable file must not stop the indexing
                kb.documents.append({"path": f.name, "sha256": _sha256(f), "chunks": 0, "error": str(e)})
                continue
            for i, (loc, text) in enumerate(passages):
                kb.chunks.append(Chunk(f"{f.name}#{i}", f.name, loc, text))
            kb.documents.append({"path": f.name, "sha256": _sha256(f), "chunks": len(passages)})
        if llm is not None and embed_model:
            texts = [c.text for c in kb.chunks]
            for start in range(0, len(texts), 32):
                vectors = llm.embed(texts[start:start + 32], embed_model)
                for c, v in zip(kb.chunks[start:start + 32], vectors):
                    c.embedding = v
        return kb

    def save(self, path: str | Path) -> None:
        data = {"version": 1, "created": self.created, "embed_model": self.embed_model,
                "documents": self.documents, "chunks": [asdict(c) for c in self.chunks]}
        Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "KnowledgeBase":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Chunk(**c) for c in data["chunks"]], data.get("documents", []),
                   data.get("embed_model"), data.get("created", ""))

    # ---- search
    def _bm25_ranking(self, query: str) -> list[int]:
        if not hasattr(self, "_bm25"):
            docs = [Counter(tokenize(c.text + " " + c.source)) for c in self.chunks]
            df = Counter(t for d in docs for t in d)
            lengths = [sum(d.values()) for d in docs]
            self._bm25 = (docs, df, lengths, (sum(lengths) / len(lengths)) if lengths else 1.0)
        docs, df, lengths, avgdl = self._bm25
        n, k1, b = len(docs), 1.5, 0.75
        scores = []
        q_terms = set(tokenize(query))
        for i, d in enumerate(docs):
            s = 0.0
            for t in q_terms:
                if t in d:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    s += idf * d[t] * (k1 + 1) / (d[t] + k1 * (1 - b + b * lengths[i] / avgdl))
            if s > 0:
                scores.append((s, i))
        return [i for _, i in sorted(scores, reverse=True)]

    def _vector_ranking(self, query: str, llm) -> list[int]:
        if not (llm is not None and self.embed_model and hasattr(llm, "embed")):
            return []
        indexed = [(i, c.embedding) for i, c in enumerate(self.chunks) if c.embedding]
        if not indexed:
            return []
        q = llm.embed([query], self.embed_model)[0]
        qn = math.sqrt(sum(x * x for x in q)) or 1.0
        sims = []
        for i, v in indexed:
            vn = math.sqrt(sum(x * x for x in v)) or 1.0
            sims.append((sum(a * b for a, b in zip(q, v)) / (qn * vn), i))
        return [i for s, i in sorted(sims, reverse=True) if s > 0.3]

    def search(self, query: str, k: int = 5, llm=None) -> list[Chunk]:
        """Top-k passages. Keyword and semantic rankings are fused (reciprocal rank fusion)."""
        fused: Counter = Counter()
        for ranking in (self._bm25_ranking(query), self._vector_ranking(query, llm)):
            for rank, i in enumerate(ranking[:50]):
                fused[i] += 1 / (60 + rank)
        return [self.chunks[i] for i, _ in fused.most_common(k)]


def format_context(chunks: list[Chunk]) -> str:
    if not chunks:
        return "Aucun extrait pertinent trouvé dans la base documentaire."
    return "\n\n".join(f"[{n}] ({c.citation()})\n{c.text}" for n, c in enumerate(chunks, 1))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
