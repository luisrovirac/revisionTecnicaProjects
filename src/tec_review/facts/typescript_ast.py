"""Reglas de TypeScript con tree-sitter, en proceso: no ejecuta eslint ni plugins del target (I2).

ts_explicit_any: cada anotación o aserción `any` (`x: any`, `as any`, `Array<any>`). Las
apariciones en comentarios o strings no cuentan porque no son nodos de tipo. Las directivas
`eslint-disable` del target no se respetan (I10).
"""

from __future__ import annotations

import time
from pathlib import Path

from tree_sitter_language_pack import get_parser

from tec_review import __version__
from tec_review.domain.models import Location, RawFact
from tec_review.domain.ports import AnalyzerResult
from tec_review.rules.catalog import Rule

TOOL = "tec-review-ts"
PARSER_BY_SUFFIX = {".ts": "typescript", ".tsx": "tsx"}


def explicit_any_lines(source: bytes, grammar: str) -> list[int]:
    tree = get_parser(grammar).parse(source)
    lines, pending = [], [tree.root_node]
    while pending:
        node = pending.pop()
        if node.type == "predefined_type" and node.text == b"any":
            lines.append(node.start_point[0] + 1)
        pending.extend(node.children)
    return sorted(lines)


class TypeScriptAnalyzer:
    name = TOOL

    def __init__(self, rules: list[Rule]) -> None:
        self.rule = next((r for r in rules if r.check.metric == "ts_explicit_any"), None)

    def run(self, root: Path, files: list[str]) -> AnalyzerResult:
        started = time.perf_counter()
        facts = []
        targets = [f for f in files if Path(f).suffix in PARSER_BY_SUFFIX and not f.endswith(".d.ts")]
        for rel in targets if self.rule else []:
            for line in explicit_any_lines((root / rel).read_bytes(), PARSER_BY_SUFFIX[Path(rel).suffix]):
                facts.append(RawFact(tool=TOOL, tool_version=__version__, tool_rule=self.rule.id,
                                     location=Location(path=rel, start_line=line, end_line=line),
                                     message="Uso explícito de `any`.", identity="any"))
        return AnalyzerResult.ok(TOOL, __version__, started, facts)
