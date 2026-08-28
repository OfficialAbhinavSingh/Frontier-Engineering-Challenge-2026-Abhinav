"""Per-repository memory carried across cases.

Within one repository the same mistakes recur: the wrong import path, a fixture
that does not exist, a helper every test in the project uses. Without memory the
agent rediscovers each of them case by case and pays a repair round for it every
time.

Memory is scoped to a repository, never to a case, and it is written only after a
case that actually went wrong -- a run that succeeded first try has nothing to
teach. Lessons are capped and evicted oldest-first so the prompt cannot grow
without bound, and every lesson records which case produced it so a bad one can
be traced back.

Because memory makes later cases depend on earlier ones, it is reset at the start
of every evaluation run and cases are always processed in a fixed order. Without
that, two runs of the same variant would not be comparable.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from reprobot.llm.client import LLMClient

MAX_LESSONS = 10

DISTILL_SYSTEM = """You are keeping notes for an agent that writes regression tests
in one specific Python repository.

Read what went wrong on this case and write at most two short lessons that would
have prevented the wasted attempts, and that will still be true for a different
bug in the same repository.

Write about this project's conventions: import paths, helper functions, fixture
names, how its tests are structured, API shapes that are easy to get wrong.
Do not write about this particular bug, and do not write generic testing advice.

Reply with a JSON array of strings. Reply with [] if there is no durable lesson."""


class RepoMemory:
    """Lessons about one repository, persisted between cases."""

    def __init__(self, root: Path | str, repo_name: str, enabled: bool = True) -> None:
        self.enabled = enabled
        self.repo_name = repo_name
        self.path = Path(root) / f"{repo_name}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lessons: list[dict] = []
        if enabled and self.path.exists():
            try:
                self.lessons = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                self.lessons = []

    def reset(self) -> None:
        self.lessons = []
        if self.path.exists():
            self.path.unlink()

    def brief(self) -> str:
        if not self.enabled or not self.lessons:
            return ""
        body = "\n".join(f"- {item['text']}" for item in self.lessons)
        return (
            "Notes from earlier bugs in this same repository:\n"
            f"{body}"
        )

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.lessons, indent=2))

    def add(self, texts: list[str], case_id: str) -> list[str]:
        added = []
        existing = {item["text"].strip().lower() for item in self.lessons}
        for text in texts:
            text = (text or "").strip()
            if not text or text.lower() in existing or len(text) > 300:
                continue
            self.lessons.append(
                {"text": text, "from_case": case_id, "added_at": time.time()}
            )
            existing.add(text.lower())
            added.append(text)
        # Oldest lessons are evicted first; the prompt has a fixed budget.
        if len(self.lessons) > MAX_LESSONS:
            self.lessons = self.lessons[-MAX_LESSONS:]
        if added:
            self._save()
        return added

    def distill(self, client: LLMClient, case_id: str, issue_title: str,
                attempts: list[dict]) -> list[str]:
        """Ask the model what it should remember, given how the case actually went."""
        if not self.enabled or not attempts:
            return []
        # A case solved on the first attempt produced no evidence of a pitfall.
        if len(attempts) == 1 and attempts[0].get("verdict") in (
            "reproduced_exception", "reproduced_assertion"
        ):
            return []

        history = "\n\n".join(
            f"Attempt {i + 1}: verdict={a.get('verdict')} "
            f"exception={a.get('exception_type')}\n"
            f"why: {a.get('reason')}\n"
            f"pytest said:\n{(a.get('output') or '')[-900:]}"
            for i, a in enumerate(attempts)
        )
        user = (
            f"Repository: {self.repo_name}\n"
            f"Bug report title: {issue_title}\n\n"
            f"{history}"
        )
        reply = client.chat(
            [{"role": "system", "content": DISTILL_SYSTEM},
             {"role": "user", "content": user}],
            max_tokens=400,
        )
        text = reply.text.strip()
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            return []
        try:
            items = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return []
        if not isinstance(items, list):
            return []
        return self.add([str(x) for x in items][:2], case_id)
