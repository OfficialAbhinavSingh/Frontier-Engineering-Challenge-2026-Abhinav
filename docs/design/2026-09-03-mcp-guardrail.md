# Ratchat as an MCP guardrail

Status: implemented. Corrections found during implementation are marked below.
Date: 2026-09-03

## The problem this solves

A coding agent that fixes a bug has no way to prove it fixed anything. It can
run a test it wrote itself, but a test the agent authored and the agent judged
is not evidence — the same process produced the claim and the verification of
the claim. "The agent fixed it" stays unfalsifiable.

Ratchat already contains the missing half: a deterministic verifier that reads
a pytest run and decides *why* a test failed, not merely that it did. Exposing
that over MCP puts a falsifier in the loop that the agent does not control.

## Scope

Ratchat becomes the thing that proves a reproduction, not the thing that writes
one. The calling agent writes the test. Ratchat executes it in the existing
Docker sandbox and reports whether it failed at the current commit, and whether
it failed for the reason the bug report describes.

No model is called. No API key is read. The same inputs give the same answer.

### Out of scope, deliberately

**Fail-to-Pass.** F2P requires a fix commit to score the "passes after the fix"
half. In real use there is no fix commit yet — that is the entire point of the
tool. Reporting F2P here would mean reporting a number that cannot have been
measured, so the tool reports what execution established and names what it did
not.

**Test generation.** `solve()` is not exposed. Agents are already good at
writing tests and bad at proving their own claims; the value is in the half they
cannot do for themselves. A generator tool remains a strict superset that can be
added later as "call the model, then call this" — nothing here forecloses it.

## Tool surface

Two tools. Preparation is explicit because building a repository image takes
minutes, and a tool call that blocks that long trips client timeouts and gives
the agent no signal about why it stalled. Making the cost a separate, named
call keeps it visible, which is how the rest of this project reports its costs.

### `prepare_repo`

```
prepare_repo(repo_path: str, force: bool = False)
  -> { repo_name, image, pin_sha, built: bool, duration_s }
```

Builds `ratchat-env:<repo_name>` from `envs/Dockerfile.repo` at the clone's
HEAD, via the existing `build_image()`. Idempotent: returns `built: false`
immediately when `image_exists()` and `force` is false.

**Correction.** The design claimed `build_image` was already generic and that no
new machinery was needed. That is wrong in a way that matters: it computes
`repo_name = repo.split("/")[1]` and the Dockerfile runs
`git clone https://github.com/$REPO_URL`, so it needs a GitHub `owner/name`
slug, not a local path. It is generic across GitHub repositories, not across
directories.

So `prepare_repo` reads the slug from the clone's `origin` remote, and refuses
when there is not a GitHub one:

```
{ "error": "no GitHub origin", "repo_name": "<name>", "fix": "..." }
```

A repository with no GitHub origin cannot be imaged today. Copying the working
tree instead of cloning would lift that limit and is a larger change than this
one.

**Second correction.** `build_image` tags the image after the *slug's* name
while the clone directory supplies its own, and those differ as soon as a clone
is renamed — which would mean checking for one image while building another.
Both tools therefore key on the slug's name when one is resolvable, falling back
to the directory name.

### `verify_reproduction`

```
verify_reproduction(
    repo_path: str,
    bug_report: str,
    test_source: str,
    test_rel_path: str | None = None,
    timeout_s: int = 180,
) -> {
    reproduces: bool,
    verdict: str,
    verdict_meaning: str,
    exception_type: str | null,
    source_frames: [str],
    test_frames: [str],
    reason: str,
    reported_symbol_matched: str | null,
    overspecified: object | null,
    ungrounded_literals: [str],
    outcome: str,
    exit_code: int,
    duration_s: float,
    not_established: [str],
}
```

On an unprepared repository it refuses rather than building:

```
{ "error": "repo not prepared", "fix": "call prepare_repo first",
  "repo_name": "<name>" }
```

**Third correction, found by calling the tool rather than reading it.**
`pin_sha_for` runs git with `check=True`, so a path that is not a repository
raised `CalledProcessError` straight through the protocol layer, which reported
only `Error executing tool verify_reproduction`. This is reachable in practice:
the image lookup is keyed on a name, so a stale image from another clone of the
same name passes the first gate. Both tools now validate the path first — before
the image gate, because a wrong path is more useful to report than the
preparation state of an unrelated image:

```
{ "error": "not a git repository", "path": "<path>", "fix": "..." }
```

The response also carries `test_rel_path`, so a caller that let the path default
knows which file the verdict describes.

Refusing is the chosen behaviour. An implicit build turns a fast call into a
multi-minute one exactly once per repository, at an unpredictable moment, and
the agent cannot tell that stall apart from a hang.

## What the response means

Three existing functions carry most of the value, and none of them is about
whether the test failed:

| Field | Source | What it catches |
| --- | --- | --- |
| `reported_symbol_matched` | `failure_is_named_in_report(output, issue_text)` | The failure mentions an identifier the report itself asks about. Returns which one, so a reviewer can check the link rather than trust a boolean. |
| `overspecified` | `overspecification(test_source, issue_text)` | The test failed on more claims than the report makes, so it would keep failing after a correct fix. |
| `ungrounded_literals` | `ungrounded_literals(test_source, issue_text)` | Asserted string values the reporter never wrote, i.e. invented expectations. |

Together these are the "your agent's test is lying to you" detectors. They are
why this is a guardrail and not a test runner.

`verdict` and `reproduces` come from `verify(run, test_rel_path, issue_text)`
and its `REPRODUCING` membership. `verdict_meaning` is read from
`artifact.VERDICT_MEANING`, which is the live vocabulary.

`not_established` is a fixed list, stated on every successful response. Its
first entry is the one that matters: a passing verdict does not establish that
the asserted value is the value a fix will produce. That needs an oracle the
pipeline does not have, and it is the most common way a generated reproduction
is wrong.

## Test path selection

When `test_rel_path` is omitted, the path is
`default_test_dir(view)/test_ratchat_<slug>.py`, where `<slug>` is the first 12
hex characters of the SHA-256 of `bug_report`. A hash rather than sanitised
report text: it is stable across calls for the same report, cannot collide by
truncation of two different reports in practice, and cannot produce an invalid
Python module name from arbitrary prose.

`default_test_dir(view)` is reused: it infers the project's own test directory
from repository layout. `LEGACY_TEST_PREFIX` is **not** reused — it is
`test_reprobot_`, frozen naming from the competition dataset, and the MCP surface
gets its own `MCP_TEST_PREFIX = "test_ratchat_"`. Changing the legacy constant
would rename paths inside a frozen result set.

The path must not already exist, so the resulting patch can only ever add a
file and can never modify an existing test. If it does exist — a caller-supplied
`test_rel_path` pointing at a real file, or a repeat call for the same report
after the previous test was committed — the tool refuses:

```
{ "error": "test path already exists", "path": "<rel path>",
  "fix": "pass a test_rel_path that does not exist in the repository" }
```

Refusing rather than overwriting or auto-suffixing: silently writing a
different path than the caller asked for would make the returned verdict
describe a file the caller does not know about.

`run_test` is called directly rather than `run_candidate`, because
`run_candidate` hardcodes `timeout_s=180` and the tool exposes a timeout.

## Files

| Path | Change |
| --- | --- |
| `ratchat/mcp/__init__.py` | new — holds `missing_sdk_message`, imports no SDK |
| `ratchat/mcp/guardrail.py` | new — every decision; no SDK, no Docker to import |
| `ratchat/mcp/server.py` | new — both tools, import-guarded |
| `docs/design/2026-09-03-mcp-guardrail.md` | this document |
| `pyproject.toml` | `[project.optional-dependencies] mcp`; console script |
| `tests/test_mcp.py` | new |
| `README.md` | short MCP section |

The design put both tools in `server.py`. They are split: `guardrail.py` holds
the decision and imports neither the SDK nor Docker, so the tests can exercise
it in the `harness unit tests` CI job, which installs no extras. `server.py` is
protocol wiring only.

`dependencies = []` stays empty. The MCP SDK is an optional extra installed as
`pip install 'ratchat[mcp]'`, behind an import guard that names the fix when the
extra is missing.

**Fourth correction.** The extra pins `mcp>=2`, not `>=1.28`. The SDK renamed
`FastMCP` to `MCPServer` in 2.0, and the server is written against v2 — a 1.x
install would resolve and then fail at import. The guard tells the two apart:
an absent SDK and an SDK too old are different problems, and reporting "not
installed" for a package that is installed sends the reader to fix the one
thing already true. That is the same failure this project exists to catch,
so it does not get to live in the project's own plumbing. It raises
`ImportError` rather than the `SystemExit` the design sketched, because a
library should not exit the interpreter on import. This keeps REPRODUCTION.md's claim — "There are no Python
dependencies to install" — literally true for the replay path that anyone can
verify at zero cost.

## Testing

Unit tests construct a `RunResult` directly and assert:

- each verdict maps to the documented response shape
- an unprepared repository yields the refusal, not a build
- `not_established` is present on every success
- the detector fields are surfaced, including the `None` cases
- the generated test path is new and carries the MCP prefix, not the legacy one

No Docker. This matches `tests/test_verifier.py`, which already builds
`RunResult` values by hand, and keeps the `harness unit tests` CI job fast and
runnable on a machine with no daemon. Docker-dependent behaviour stays covered
by the existing `metric controls` job, which this change does not touch.

## Known defect, tracked separately

`verifier.VERDICTS` lists six verdicts. `artifact.VERDICT_MEANING` lists eight.
Missing from the tuple: `overspecified` and `reproduced_signature` — the latter
is produced at `verifier.py:171`, is a member of `REPRODUCING`, and is asserted
in `tests/test_verifier.py:134`.

`VERDICTS` is referenced nowhere. It is declared at `verifier.py:36` and never
read, so the drift is invisible and harmless today. It is the same fact recorded
twice, which is how it drifted.

This design reads `VERDICT_MEANING`, the live one, so it is unaffected. The
tuple is fixed in its own commit rather than folded into a feature.
