"""Read-only view of a repository at one commit.

Everything an agent is allowed to see about the codebase comes through here, and
it is all served from git object storage at the *parent* commit -- the state in
which the bug is still present. Nothing in this module can reach the fix commit,
which is what makes the evaluation honest rather than merely well-intentioned.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_CHARS = 60_000


@dataclass
class RepoView:
    repo_dir: Path
    sha: str

    def _git(self, *args: str, check: bool = False) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.repo_dir), *args],
            capture_output=True, text=True, check=check,
        )
        return proc.stdout

    def list_files(self, subdir: str = "", suffix: str = ".py") -> list[str]:
        out = self._git("ls-tree", "-r", "--name-only", self.sha)
        files = [f for f in out.splitlines() if f]
        if subdir:
            prefix = subdir.rstrip("/") + "/"
            files = [f for f in files if f.startswith(prefix)]
        if suffix:
            files = [f for f in files if f.endswith(suffix)]
        return sorted(files)

    def read_file(self, path: str, start: int | None = None,
                  end: int | None = None) -> str:
        content = self._git("show", f"{self.sha}:{path}")
        if not content:
            return f"[no such file at this commit: {path}]"
        if start is None and end is None:
            if len(content) > MAX_FILE_CHARS:
                return content[:MAX_FILE_CHARS] + "\n[... truncated ...]"
            return content
        lines = content.splitlines()
        lo = max(0, (start or 1) - 1)
        hi = min(len(lines), end or len(lines))
        numbered = [f"{i + 1:>5}| {lines[i]}" for i in range(lo, hi)]
        return "\n".join(numbered)

    def grep(self, pattern: str, glob: str | None = None, max_hits: int = 60) -> str:
        args = ["grep", "-n", "-I", "--fixed-strings"
                if not any(ch in pattern for ch in "\\[](){}|+*?^$") else "-E",
                pattern, self.sha]
        if glob:
            args += ["--", glob]
        out = self._git(*args)
        hits = out.splitlines()
        if not hits:
            return f"[no matches for {pattern!r}]"
        shown = hits[:max_hits]
        # git grep prefixes every hit with the tree-ish; it is noise to the agent.
        cleaned = [h[len(self.sha) + 1:] if h.startswith(self.sha + ":") else h
                   for h in shown]
        suffix = "" if len(hits) <= max_hits else f"\n[{len(hits) - max_hits} more matches]"
        return "\n".join(cleaned) + suffix

    def file_exists(self, path: str) -> bool:
        proc = subprocess.run(
            ["git", "-C", str(self.repo_dir), "cat-file", "-e", f"{self.sha}:{path}"],
            capture_output=True, check=False,
        )
        return proc.returncode == 0

    def test_files(self) -> list[str]:
        return [f for f in self.list_files()
                if "/test" in f or f.startswith("test") or "/tests/" in f]
