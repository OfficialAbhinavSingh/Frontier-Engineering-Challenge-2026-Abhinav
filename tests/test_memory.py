"""Memory persistence, and the replay hazard it creates for the narrated demo.

The demo ships a committed cache so it can be replayed for free and always shows
the same run. Repository memory is injected into the author's prompt, so anything
memory writes changes that prompt -- and a changed prompt is a different cache
key. A demo that saves what it learned therefore invalidates its own recording:
the first replay misses the cache, calls the API, and can reach a different
verdict. These tests pin both halves of the fix.
"""

from __future__ import annotations

import json
from pathlib import Path

from ratchat.agents.memory import RepoMemory

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_memory_persists_by_default(tmp_path):
    """The evaluation harness carries lessons between cases, so saving is the default."""
    memory = RepoMemory(tmp_path, "click")
    memory.add(["Import ParamType, not FuncParamType."], "click__3105")

    assert memory.path.exists()
    assert json.loads(memory.path.read_text())[0]["from_case"] == "click__3105"

    reloaded = RepoMemory(tmp_path, "click")
    assert len(reloaded.lessons) == 1


def test_memory_can_be_used_without_writing_to_disk(tmp_path):
    """A single-case run still learns within the run, but leaves no trace behind."""
    memory = RepoMemory(tmp_path, "click", persist=False)
    added = memory.add(["Import ParamType, not FuncParamType."], "click__3105")

    assert added, "the lesson should still be usable for the rest of this run"
    assert memory.brief(), "and it should still reach the prompt"
    assert not memory.path.exists(), "but nothing may be written to disk"


def test_demo_memory_is_empty_so_the_cached_run_replays():
    """Guards the demo's offline replay.

    The committed cache was recorded against a prompt built with no repository
    notes. If a lesson is ever committed under data/memory/demo the prompt gains
    a 'Notes from earlier bugs' block, the cache key changes, and the demo starts
    spending money and drifting. Keep this directory empty.
    """
    demo_memory = REPO_ROOT / "data" / "memory" / "demo"
    for path in sorted(demo_memory.glob("*.json")):
        assert json.loads(path.read_text()) == [], (
            f"{path.relative_to(REPO_ROOT)} holds lessons, which changes the author "
            "prompt and breaks the demo's cached replay"
        )
