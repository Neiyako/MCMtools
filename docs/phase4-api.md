# Phase 4 — The API Layer and the Submission Gate

**Status: complete.** 276 tests passing (72 new). A real HTTP server serves the
whole toolchain, `--strict` turns the audit into a submission gate, and
competition mode is now **enforced** rather than merely recorded.

Phases 1–3 built the mechanism. Phase 4 exposes it — and, in doing so, exposed
one real defect: **the auditor could not see stale artifacts**, so the gate that
was supposed to block a submission would have waved through a paper whose figures
no longer matched its results.

---

## 1. What was built

```
core/mcmcore/state.py      the Overview payload (Core, shared by CLI and API)
core/mcmcore/api.py        32 endpoints, thin delegation to Core
core/mcmcore/mode.py       competition-mode enforcement
core/tests/test_api.py     48 tests
core/tests/test_mode.py    24 tests
```

```bash
./core/mcm overview [--json]           # phase, counts, steps, blockers
./core/mcm serve [--port 8420]         # the API, plus /docs
./core/mcm validate --strict           # the submission gate
./core/mcm mode [--set competition]    # switch mode, with real enforcement
```

---

## 2. The gate

```bash
$ ./core/mcm validate --strict
WARNINGS (3)
  ...
STRICT (2) - these block submission under --strict
  WARNING ARTIFACT_NOT_CITED [FIG-002]: ...
  WARNING NUMERIC_UNBOUND [SEC-030]: ...
  -> DO NOT SUBMIT: 2 blocking warning(s).
$ echo $?
1
```

Exit 0 normally, exit 1 under `--strict`. So this already works as a
pre-commit or pre-submission hook.

**Which warnings get promoted, and why.** A gate that blocks on taste gets
disabled, and then it blocks nothing. So promotion is limited to cases where the
document makes a claim the toolchain can *prove* is unsupported, or where COMAP
compliance is at stake:

| Code | Why it blocks |
|---|---|
| `FIG_STALE` / `TAB_STALE` | the artifact displays numbers the experiment no longer produces |
| `ARTIFACT_FILE_MISSING` | the PDF would contain a placeholder box |
| `NUMERIC_UNBOUND` | prose states a number with no `ResultAtom` behind it |
| `ARTIFACT_NOT_CITED` | 100% of references are cited; a figure nobody cites is decoration |
| `PARAMETER_NO_PROVENANCE` | an unsourced number is an invented number |
| `SYMBOL_REDEFINED` | the same glyph means two things |

Deliberately **not** promoted: `PAGE_BUDGET_UNDERUSED` (an unfinished paper is
not a compliance failure), `ARTIFACT_UNBOUND`, and every INFO finding.

---

## 3. The defect this phase found

`paper build` reported `FIG_STALE`. `audit_project` — the function the gate
trusts — reported `ready_for_human_review` on the same project.

The compiler injected the finding into its own `BuildResult`; the auditor had no
staleness check at all. Since the gate reads the auditor, it would have said
"submit" about a paper whose figures disagreed with its results — precisely the
divergence this whole toolchain exists to prevent.

Fixed by adding the check to `check_artifact()`, so the auditor detects staleness
**independently of whether a build has been run**. There is now a test asserting
the two agree, because a gate that contradicts the auditor is worse than no gate.

---

## 4. Design decisions

**The Overview payload is Core, not API.** The CLI and the API render the same
`build_overview()` output. If the UI computed its own counts, it would eventually
disagree with the auditor — and the auditor is the one that decides whether the
paper is submittable.

**Every blocker carries an action.** A blocker without a next step is a
complaint. `_ACTIONS` maps each code to a concrete instruction, and a test
asserts no blocker ships without one.

**The project is bound at app construction, not per request.** A client cannot
point the server at a different directory, which would make the findings it
returns unattributable.

**Errors sort before warnings**, stably — so the panel's top line is always the
thing to fix first.

**The API is thin.** If an endpoint contains logic, that logic belongs in Core
where the CLI can reach it. The one exception is `paper/build`, which is
synchronous because it is bounded (seconds) and the user is waiting.

---

## 5. The constraint that is actually enforced

The architecture doc states: *"No endpoint mutates a `ResultAtom`."* This is the
constraint that makes the single source of truth trustworthy — if an HTTP client
could edit a result, the number in the paper would stop being the number the
experiment produced.

It is enforced structurally, and tested:

```
Routes that could write a result atom:
  (none - no result-write routes at all)

PUT /api/results/{id} -> 405
POST /api/results     -> 405
atom value still 119299.92  (must not be 999)
```

A test walks the route table and fails if any endpoint with a write method
mentions `results`, so this cannot regress by someone adding a convenience
endpoint later.

---

## 6. Verified over real HTTP

```
$ ./core/mcm --dir examples/demo_pcql serve --port 8437
$ curl -s localhost:8437/api/health
{"ok":true,"project":".../demo_pcql","version":"0.4.0"}
$ curl -s localhost:8437/api/state          -> phase: build | 7 steps | 3 blockers
$ curl -s localhost:8437/api/experiments/EXP-001/trials -> 3 trials
$ curl -s -o bundle.zip localhost:8437/api/export/bundle -> 200, 175274 bytes
  zip: solution.pdf, latex/main.tex, latex/figures/FIG-001.pdf,
       latex/tables/TAB-001.tex, audit.json, project/project.yaml, README.txt
```

The full loop also works through HTTP: `PUT /api/models/M01` (refit gamma) →
`POST /api/experiments/EXP-001/run` (202, 15 atoms changed, `FIG-001` stale) →
gate blocks with `FIG_STALE` → `POST /api/figures/FIG-001/regenerate` → gate
clears.

---

## 7. Deliberately not built

| Not built | Why |
|---|---|
| WebSocket progress | a competition sweep is seconds; polling a finished run is simpler and has fewer failure modes |
| auth | it binds to `127.0.0.1` and the tool is offline by design |
| a database | the store is files; adding a DB would break diffability for no gain |
| background task queue | one user, one project, short runs |
| auto-regenerating stale figures on build | the build must report, not silently rewrite the user's figures |
| a Vue3 frontend | Phase 9 in the roadmap; the API must be stable first |

---

## 8. Competition mode is now enforced

I wrote in an earlier draft of this document that competition mode was *"the most
important unbuilt piece"*. Building it confirmed that. The tool detects AI use
during the competition (`AI_USED_DURING_COMPETITION`) but until now nothing
*prevented* it, and nothing stopped a network call. The project's entire premise
is that the competition runs offline with no AI, so a recorded intent is not
enough.

```
$ ./core/mcm mode
project mode : development
process mode : development
net guard    : not installed

$ ./core/mcm mode --set competition
mode: development -> competition
  Network access is blocked while competition mode is active.
  AI-assisted commands are refused.
```

Three strengths of enforcement, chosen deliberately:

**1. Network guard — a hard block.** `socket.connect`, `connect_ex` and
`getaddrinfo` are patched to raise on non-loopback addresses. The tests hit a
**real socket** rather than a mock, because the failure mode being guarded
against is a charting library quietly fetching a font at 2am — that only appears
at the real syscall boundary.

Loopback is explicitly allowed. Blocking `127.0.0.1` would break local tooling
for no benefit, and a guard that breaks unrelated things gets removed. There is a
test that opens a real loopback connection *inside* the guard to prove this.

```
>>> with enforce_network_block():
...     socket.getaddrinfo("example.com", 80)
NetworkBlocked: Competition mode blocks DNS lookups: DNS lookup of 'example.com'.
>>> socket.getaddrinfo("127.0.0.1", 80)      # allowed
```

An experiment that phones home now **fails loudly**:

```
def run(params):
    socket.getaddrinfo('example.com', 80)    # -> run status: failed
```

**2. Provenance stamping — blocks nothing, enables honesty.** Every result
records `produced_in_mode` and `produced_at`. A number computed during the
competition is permanently distinguishable from one computed beforehand, so a
reviewer does not have to trust anyone's memory about which is which. This is
the half of enforcement that matters most for disclosure, and it cannot be
achieved by blocking.

**3. AI-assist block.** `require_development(feature)` raises in competition
mode. There are no AI features to call today, so this is a guard against ones
added later — and every refusal is recorded.

Everything blocked is recorded with a timestamp and surfaced through
`GET /api/mode`, so the panel can show what the guard caught rather than merely
asserting that it is on.

---

## 9. What remains

The API is stable enough to build the UI against.

1. **Vue3 panel** (roadmap Phase 9) — the phase-driven navigation of §14. The
   API already returns everything the five key screens need: `GET /api/state`
   for Overview, `/api/models/{id}` for the model-as-identity view, the trials
   endpoint for the experiment DAG, `/api/figures/stale` for Results,
   `/api/paper/budget` for the live page budget, and `/api/mode` for the mode
   badge.
2. **More experiment templates** — nine declared, one implemented.

**Remaining honest limitations.** The network guard is process-level, so it
protects the CLI, the API and experiment code that runs in this process; it
cannot stop a subprocess that re-execs Python fresh, because that process would
need to install the guard itself. And `mode` is enforced from `project.yaml` at
run time — a user who switches the setting mid-competition is not prevented from
doing so, only recorded. Both are acceptable for a single-user local tool whose
purpose is to make the honest path the default, not to defend against its owner.
