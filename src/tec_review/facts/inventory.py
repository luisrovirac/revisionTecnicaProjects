"""Inventario del proyecto auditado y guarda de rutas (I1: read-only sobre el target)."""

from __future__ import annotations

import os
from pathlib import Path

import pathspec
from pydantic import BaseModel

DEFAULT_EXCLUDED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", "site-packages", ".idea",
    ".vscode", "vendor", "target", ".next", "coverage", ".nuxt", ".output", ".svelte-kit",
    ".turbo", ".cache", ".parcel-cache", ".gradle", "bin", "obj",
})
LANGUAGE_BY_EXT = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".java": "java", ".go": "go", ".rs": "rust",
    ".php": "php", ".sql": "sql", ".swift": "swift", ".kt": "kotlin", ".cs": "csharp",
}
MAX_FILE_BYTES = 1_000_000


class PathGuardError(Exception):
    """Intento de escribir dentro del proyecto auditado."""


class PathGuard:
    """Rechaza cualquier ruta de escritura bajo la raíz del target (symlinks resueltos)."""

    def __init__(self, target_root: Path) -> None:
        self.target_root = target_root.resolve()

    def check_writable(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved == self.target_root or self.target_root in resolved.parents:
            raise PathGuardError(
                f"Escritura bloqueada (I1): {resolved} está dentro del proyecto auditado "
                f"{self.target_root}. Usa --out fuera del proyecto."
            )
        return resolved


class Inventory(BaseModel):
    root: Path
    files: list[str]  # rutas relativas con "/", ordenadas
    languages: dict[str, int]  # lenguaje -> nº de archivos
    skipped_binary: int = 0
    skipped_large: int = 0
    total_lines: int = 0

    def files_of(self, language: str) -> list[str]:
        return [f for f in self.files if LANGUAGE_BY_EXT.get(Path(f).suffix) == language]


class _IgnoreRules:
    """Reglas .gitignore anidadas: cada archivo aplica a su subárbol, como en git."""

    def __init__(self) -> None:
        self._specs: list[tuple[str, pathspec.PathSpec]] = []

    def load(self, directory: Path, prefix: str) -> None:
        gitignore = directory / ".gitignore"
        if gitignore.is_file():
            lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
            self._specs.append((prefix, pathspec.PathSpec.from_lines("gitignore", lines)))

    def ignored(self, rel: str) -> bool:
        return any(rel.startswith(prefix) and spec.match_file(rel[len(prefix):])
                   for prefix, spec in self._specs)


def _is_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"\x00" in handle.read(8192)


def _walk(root: Path):
    rules = _IgnoreRules()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if rel_dir == "." else f"{rel_dir}/"
        rules.load(Path(dirpath), prefix)
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in DEFAULT_EXCLUDED_DIRS and not rules.ignored(f"{prefix}{d}/")
        )
        for name in sorted(filenames):
            rel = f"{prefix}{name}"
            if not rules.ignored(rel) and not (Path(dirpath) / name).is_symlink():
                yield rel


def build_inventory(root: Path) -> Inventory:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"La ruta a auditar no existe o no es un directorio: {root}")
    files, languages = [], {}
    counters = {"binary": 0, "large": 0, "lines": 0}
    for rel in _walk(root):
        _classify(root / rel, rel, files, languages, counters)
    return Inventory(
        root=root, files=sorted(files), languages=dict(sorted(languages.items())),
        skipped_binary=counters["binary"], skipped_large=counters["large"],
        total_lines=counters["lines"],
    )


def _classify(path: Path, rel: str, files: list, languages: dict, counters: dict) -> None:
    if path.stat().st_size > MAX_FILE_BYTES:
        counters["large"] += 1
        return
    if _is_binary(path):
        counters["binary"] += 1
        return
    files.append(rel)
    language = LANGUAGE_BY_EXT.get(path.suffix)
    if language:
        languages[language] = languages.get(language, 0) + 1
        counters["lines"] += path.read_text(encoding="utf-8", errors="replace").count("\n") + 1


def read_lines(root: Path, rel: str) -> list[str]:
    return (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
