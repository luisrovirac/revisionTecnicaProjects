"""Duplicación por n-gramas de tokens (check.kind: duplication).

Tokens normalizados: los literales pasan a STR/NUM y los comentarios se descartan; los
identificadores se conservan (clones tipo 1-2: copiar y pegar con valores cambiados). Una ventana
de `min_tokens` que aparece en dos sitios sin solaparse es semilla; las semillas consecutivas se
funden en bloques. Un bloque se reporta si abarca al menos MIN_LINES líneas.
"""

from __future__ import annotations

import io
import re
import time
import tokenize
from collections import defaultdict
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from tec_review import __version__
from tec_review.domain.models import Location, RawFact
from tec_review.domain.ports import AnalyzerResult
from tec_review.facts.inventory import LANGUAGE_BY_EXT
from tec_review.facts.patterns import is_test_file
from tec_review.rules.capabilities import C_LIKE
from tec_review.rules.catalog import Rule

TOOL = "tec-review-dup"
MIN_LINES = 5
MAX_AVG_LINE = 300  # archivos minificados o generados
SKIP_PY = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
           tokenize.ENCODING, tokenize.ENDMARKER}
C_TOKEN = re.compile(r"//[^\n]*|/\*.*?\*/|\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`[^`]*`|"
                     r"\d+(?:\.\d+)?|\w+|[^\s\w]", re.DOTALL)


class Token(BaseModel):
    text: str
    line: int


class Block(BaseModel):
    path: str
    start: int  # índice de token
    end: int    # índice de token, exclusivo


def python_tokens(source: str) -> list[Token]:
    result = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in SKIP_PY:
            continue
        text = {tokenize.STRING: "STR", tokenize.NUMBER: "NUM"}.get(tok.type, tok.string)
        result.append(Token(text=text, line=tok.start[0]))
    return result


def c_like_tokens(source: str) -> list[Token]:
    result, line = [], 1
    position = 0
    for match in C_TOKEN.finditer(source):
        line += source.count("\n", position, match.start())
        position = match.start()
        text = match.group(0)
        if not text.startswith(("//", "/*")):
            normalized = "STR" if text[0] in "\"'`" else "NUM" if text[0].isdigit() else text
            result.append(Token(text=normalized, line=line))
    return result


def tokens_for(rel: str, source: str) -> list[Token]:
    language = LANGUAGE_BY_EXT.get(PurePosixPath(rel).suffix)
    lines = source.count("\n") + 1
    if language is None or len(source) / lines > MAX_AVG_LINE:
        return []
    if language == "python":
        return python_tokens(source)
    return c_like_tokens(source) if language in C_LIKE else []


def _seeds(streams: dict[str, list[Token]], window: int) -> list[tuple[str, int, str, int]]:
    """Pares (archivo A, i, archivo B, j) de ventanas idénticas: primera aparición frente al resto."""
    index: dict[tuple[str, ...], list[tuple[str, int]]] = defaultdict(list)
    for path in sorted(streams):
        texts = [t.text for t in streams[path]]
        for i in range(len(texts) - window + 1):
            index[tuple(texts[i : i + window])].append((path, i))
    pairs = []
    for places in index.values():
        first = places[0]
        pairs += [(first[0], first[1], p, j) for p, j in places[1:]
                  if p != first[0] or j - first[1] >= window]
    return sorted(pairs)


def _merge(pairs, window: int) -> list[tuple[Block, Block]]:
    blocks: list[tuple[Block, Block]] = []
    for a_path, i, b_path, j in pairs:
        last = blocks[-1] if blocks else None
        if last and last[0].path == a_path and last[1].path == b_path \
                and i <= last[0].end - window + 1 and j - i == last[1].start - last[0].start:
            last[0].end, last[1].end = i + window, j + window
            continue
        blocks.append((Block(path=a_path, start=i, end=i + window),
                       Block(path=b_path, start=j, end=j + window)))
    return blocks


class DuplicationAnalyzer:
    name = TOOL

    def __init__(self, rules: list[Rule]) -> None:
        self.rule = next((r for r in rules if r.check.kind == "duplication"), None)
        self.window = int(getattr(self.rule.check, "min_tokens", 50)) if self.rule else 50

    def run(self, root: Path, files: list[str]) -> AnalyzerResult:
        started = time.perf_counter()
        facts, warnings = [], []
        if self.rule is not None:
            streams = {}
            for rel in (f for f in files if not is_test_file(f)):  # en tests se acepta repetir
                try:
                    streams[rel] = tokens_for(rel, (root / rel).read_text(encoding="utf-8", errors="replace"))
                except (tokenize.TokenError, SyntaxError, ValueError, IndentationError):
                    warnings.append(f"parse_error {rel}: duplicación")
            facts = self._facts(streams)
        return AnalyzerResult.ok(TOOL, __version__, started, facts, warnings)

    def _facts(self, streams: dict[str, list[Token]]) -> list[RawFact]:
        """Un hallazgo por par de archivos, con el primer bloque como ubicación."""
        groups: dict[tuple[str, str], list[tuple[Block, Block]]] = {}
        for a, b in _merge(_seeds(streams, self.window), self.window):
            ta = streams[a.path][a.start : a.end]
            if ta[-1].line - ta[0].line + 1 >= MIN_LINES:
                groups.setdefault((a.path, b.path), []).append((a, b))
        return [self._group_fact(pair, blocks, streams) for pair, blocks in sorted(groups.items())]

    def _group_fact(self, pair, blocks, streams) -> RawFact:
        def span(block: Block) -> tuple[int, int]:
            tokens = streams[block.path][block.start : block.end]
            return tokens[0].line, tokens[-1].line

        (a_start, a_end), (b_start, b_end) = span(blocks[0][0]), span(blocks[0][1])
        lines = sum(span(a)[1] - span(a)[0] + 1 for a, _ in blocks)
        extra = f" (+{len(blocks) - 1} bloques más, {lines} líneas en total)" if len(blocks) > 1 else ""
        message = (f"Bloque de {a_end - a_start + 1} líneas duplicado en "
                   f"`{pair[1]}:{b_start}-{b_end}`{extra}.")
        return RawFact(tool=TOOL, tool_version=__version__, tool_rule=self.rule.id,
                       location=Location(path=pair[0], start_line=a_start, end_line=a_end),
                       message=message, identity=f"{pair[0]}|{pair[1]}")
