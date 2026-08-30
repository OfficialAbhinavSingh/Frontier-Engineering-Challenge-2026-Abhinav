"""Deterministic repository map.

Cheap models do not fail at this task because their context is too small. They
fail because it is full of the wrong things -- a flat file listing tells them
nothing about how this project's tests are actually written, so they invent an
API and a fixture that never existed.

Nothing in this module calls a model. It reads the repository at the buggy commit
and answers three questions the author agent otherwise has to guess at: which
modules plausibly relate to this report, how this project's tests import and set
themselves up, and which fixtures exist. Being deterministic also means it costs
nothing and behaves identically on every run.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass, field

from ratchat.repo import RepoView

WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

# Words that appear in every bug report and discriminate nothing.
STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "not",
    "but", "you", "are", "was", "when", "then", "there", "here", "would",
    "should", "could", "expected", "actual", "result", "results", "error",
    "issue", "bug", "python", "version", "code", "using", "use", "used",
    "following", "example", "output", "input", "returns", "return", "value",
    "test", "tests", "line", "file", "raise", "raises", "get", "set",
}


def tokens(text: str) -> Counter:
    return Counter(
        w.lower() for w in WORD.findall(text or "")
        if w.lower() not in STOPWORDS
    )


@dataclass
class RepoMap:
    ranked_modules: list[tuple[str, float]] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    ranked_test_files: list[tuple[str, float]] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    import_idiom: list[str] = field(default_factory=list)

    def brief(self, n_modules: int = 12, n_tests: int = 8) -> str:
        """A compact, model-facing rendering of the map."""
        mods = "\n".join(f"  {p}  (relevance {s:.2f})"
                         for p, s in self.ranked_modules[:n_modules])
        tests = "\n".join(f"  {p}  (relevance {s:.2f})"
                          for p, s in self.ranked_test_files[:n_tests])
        fixtures = ", ".join(self.fixtures[:25]) or "none found"
        idiom = "\n".join(f"  {line}" for line in self.import_idiom[:8]) or "  (none)"
        return (
            f"Source modules most related to this report:\n{mods}\n\n"
            f"Test files most related to this report:\n{tests}\n\n"
            f"Fixtures available to tests in this project:\n  {fixtures}\n\n"
            f"How this project's existing tests import it:\n{idiom}"
        )


def _symbols(source: str) -> list[str]:
    """Top-level names defined in a module, used as extra ranking signal."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
            if isinstance(node, ast.ClassDef):
                names.extend(
                    child.name for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
    return names


def _score(query: Counter, path: str, symbols: list[str]) -> float:
    """Overlap between the report's vocabulary and a file's path and symbols.

    Path components are weighted above symbols: a report that names a module is
    usually right about it, whereas symbol names collide across a codebase.
    """
    path_tokens = tokens(path.replace("/", " ").replace("_", " ").replace(".py", ""))
    symbol_tokens = tokens(" ".join(s.replace("_", " ") for s in symbols))
    score = 0.0
    for term, count in query.items():
        if term in path_tokens:
            score += 3.0 * min(count, 3)
        if term in symbol_tokens:
            score += 1.0 * min(count, 3)
    return score


def _collect_fixtures(view: RepoView, test_dir: str) -> list[str]:
    """Fixture names declared in the conftest files that cover the test directory."""
    found: list[str] = []
    parts = test_dir.split("/")
    candidates = ["conftest.py"] + [
        "/".join(parts[: i + 1]) + "/conftest.py" for i in range(len(parts))
    ]
    for path in dict.fromkeys(candidates):
        if not view.file_exists(path):
            continue
        source = view.read_raw(path)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                text = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                if "fixture" in text:
                    found.append(node.name)
                    break
    return sorted(set(found))


def _import_idiom(view: RepoView, test_files: list[str], limit: int = 6) -> list[str]:
    """The import lines this project's tests actually use, most common first."""
    counter: Counter = Counter()
    for path in test_files[:limit]:
        source = view.read_raw(path)
        for line in source.splitlines()[:60]:
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and "__future__" not in stripped:
                counter[stripped] += 1
    return [line for line, _ in counter.most_common(10)]


def build_map(view: RepoView, issue_text: str, test_dir: str) -> RepoMap:
    query = tokens(issue_text)
    all_files = view.list_files()
    test_files = [f for f in all_files if f in set(view.test_files())]
    source_files = [f for f in all_files if f not in set(test_files)]

    ranked_modules = []
    for path in source_files:
        if path.endswith("__init__.py"):
            continue
        symbols = _symbols(view.read_raw(path))
        ranked_modules.append((path, _score(query, path, symbols)))
    ranked_modules.sort(key=lambda item: (-item[1], item[0]))

    ranked_tests = []
    for path in test_files:
        symbols = _symbols(view.read_raw(path))
        ranked_tests.append((path, _score(query, path, symbols)))
    ranked_tests.sort(key=lambda item: (-item[1], item[0]))

    return RepoMap(
        ranked_modules=ranked_modules,
        test_files=test_files,
        ranked_test_files=ranked_tests,
        fixtures=_collect_fixtures(view, test_dir),
        import_idiom=_import_idiom(view, [p for p, _ in ranked_tests]),
    )


def sample_tests(view: RepoView, test_path: str, count: int = 2,
                 max_chars: int = 2600) -> list[str]:
    """Extract whole test functions from a real test file, to use as in-repo examples.

    Style, fixtures and helper usage come from the project itself rather than from
    the model's priors about how tests are usually written.
    """
    source = view.read_raw(test_path)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()
    out: list[str] = []

    def emit(node: ast.AST, prefix: str = "") -> None:
        start = getattr(node, "lineno", 1) - 1
        end = getattr(node, "end_lineno", start + 1)
        snippet = "\n".join(lines[start:end])
        if len(snippet) <= max_chars:
            out.append(prefix + snippet)

    for node in tree.body:
        if len(out) >= count:
            break
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name.startswith("test"):
            emit(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in node.body:
                if len(out) >= count:
                    break
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                        child.name.startswith("test"):
                    emit(child, prefix=f"# inside class {node.name}:\n")
    return out


def focused_excerpt(view: RepoView, path: str, issue_text: str,
                    max_chars: int = 6000) -> str:
    """The parts of a module that plausibly relate to the report.

    Large projects have files far bigger than a cheap model's useful attention
    span, and pasting a whole module in mostly buys noise. This keeps the module
    docstring and imports for orientation, then adds whole top-level definitions
    in order of how well their names and bodies match the report's vocabulary.
    """
    source = view.read_raw(path)
    if len(source) <= max_chars:
        return source
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source[:max_chars] + "\n[... truncated ...]"

    lines = source.splitlines()
    query = tokens(issue_text)
    header: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            header.append("\n".join(lines[node.lineno - 1:node.end_lineno]))

    scored: list[tuple[float, str, str]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        block = "\n".join(lines[node.lineno - 1:node.end_lineno])
        body_tokens = tokens(block)
        name_tokens = tokens(node.name.replace("_", " "))
        score = sum(
            (3.0 if term in name_tokens else 0.0) + (1.0 if term in body_tokens else 0.0)
            for term in query
        )
        scored.append((score, node.name, block))
    scored.sort(key=lambda item: (-item[0], item[1]))

    out = [f"# {path} (excerpt: definitions most related to the report)"]
    out.extend(header[:15])
    used = sum(len(part) for part in out)
    for score, name, block in scored:
        if used + len(block) > max_chars:
            out.append(f"# ... omitted: {name}")
            continue
        out.append(block)
        used += len(block)
    return "\n\n".join(out)
