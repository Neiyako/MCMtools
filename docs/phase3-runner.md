# Phase 3 — The Experiment Runner and the Staleness Loop

**Status: complete.** 204 tests passing (52 new). The chain from input to PDF is
now closed in both directions.

Phases 1 and 2 defined and consumed the result model. Nothing *produced* it — the
numbers in `paper.yaml` were typed by hand, so the "single source of truth" claim
was a convention, not a mechanism. Phase 3 makes it a mechanism:

```
model parameter → experiment run → ResultAtom → LaTeX macro → PDF
       ↑                                                      │
       └──────────── change here invalidates that ────────────┘
```

---

## 1. What was built

```
core/mcmcore/runner.py    protocol expansion, execution, staleness
core/mcmcore/figures.py   stale figure regeneration from current atoms
examples/experiments/pcql_sensitivity.py   a real, runnable ODE experiment
```

```bash
./core/mcm exp trials EXP-001          # what the protocol expands to
./core/mcm exp run EXP-001 --dry-run   # same, without executing
./core/mcm exp run EXP-001             # execute, record, mark stale
./core/mcm result show RES-EXP001-PEAK-ACTIVE-001
./core/mcm artifact list               # every artifact + status + bindings
./core/mcm artifact stale              # what a result change invalidated
./core/mcm artifact regenerate         # re-render stale figures
```

---

## 2. The demonstration

`python3 examples/phase1_demo.py` builds the project, runs the sweep, and
**asserts** each step rather than printing a claim:

```
1. Run the sensitivity sweep on the paper's fitted parameters.
   experiment EXP-001: 3 run(s), 15 result atom(s)
     RUN-001-001  success  0.012s  beta=0.1,   gamma=0.0177, lambda=0.00104, phi=0.00114
     RUN-001-002  success  0.012s  beta=0.177, gamma=0.0177, lambda=0.00104, phi=0.00114
     RUN-001-003  success  0.012s  beta=0.25,  gamma=0.0177, lambda=0.00104, phi=0.00114

2. Rerun with IDENTICAL inputs: nothing may become stale.
   changed atoms: 0  ->  stale: 0

3. Refit gamma in the model and rerun. The figure MUST go stale.
   gamma 0.0177 -> 2.50e-02
   15 atom(s) changed -> 1 artifact(s) stale
     STALE: FIG-001

4. Regenerate the stale figure from the NEW atom values.
   regenerated: FIG-001
   still stale: 0
```

The experiment is not a stub. It integrates the paper's actual PCQL ODE system
with RK4 at the paper's actual fitted parameters, and reproduces the expected
epidemic behaviour — higher `beta` gives a **higher and earlier** peak:

| condition | peak active | peak day |
|---|---|---|
| `beta=0.1` | 151,782 | 89.25 |
| `beta=0.177` | 197,870 | 50.35 |
| `beta=0.25` | 219,831 | 36.10 |

After the `gamma` refit those become `119,300 / 172,429 / 198,780`, and the
rebuilt PDF contains **only** the new values:

```
new value   119,300 present: True
OLD value   151,782 present: False
```

---

## 3. The property that makes staleness useful

**Rerunning identical inputs must not mark anything stale.**

This is not a nicety. A warning that fires on every rerun is noise, and noise
gets ignored — which is exactly the failure the mechanism exists to prevent.

Getting this right required a real fix. My first implementation derived the atom
id from a hash of the condition string:

```python
# WRONG
h = hashlib.sha1(condition.encode()).hexdigest()[:5]
return f"RES-{slug}-{h}"
```

Refitting `gamma` changed the condition string, so it produced a **new** atom id
instead of updating the existing atom. The old atoms stayed behind, nothing was
recognised as changed, and **the stale mechanism silently never fired** — the one
thing it is for. The test caught it:

```
experiment EXP-001: 3 run(s), 15 result atom(s)
  15 result(s) changed; no bound artifacts
```

Now the id identifies the **trial slot**, not the values:

```python
def _auto_atom_id(name, trial_index, experiment_id):
    """A sweep over beta in {0.1, 0.177, 0.25} is the same three slots even
    after the values change."""
    return f"RES-{exp_slug}-{slug[:18]}-{trial_index:03d}"
```

Atom *identity* is the slot. Atom *content* is the fingerprint, which covers
`value`, `condition`, `unit`, `format`, `name` and `renderings` — and deliberately
excludes `run_id` and `experiment_id`, so a rerun produces the same fingerprint.

---

## 4. Other real bugs found and fixed

**Malformed atoms crashed the whole experiment.** Atom construction sat *outside*
the per-trial `try`, so one bad spec (`{"name": "x"}` with no `value`) took down
the entire runner instead of failing that trial. Moved inside the guard; the test
now asserts the run is marked failed *and* that no null atom is written.

**`held_fixed` was unverifiable.** The field held bare names (`[gamma, lambda,
phi]`), so a trial record could say a parameter was held without recording *at
what value* — and `condition_string` rendered `gamma=None`. Now
`resolve_held_values()` reads them from the owning model's `Parameter` records,
so conditions read `beta=0.1, gamma=0.0177(fixed), lambda=1.04e-03(fixed)`,
which is what makes the OAT invariant checkable.

**Condition formatting misread the fitted parameters.** The scientific-notation
cutoff was `1e-3`, so `lambda=1.04e-03` printed as `0.00104` — three leading
zeros hiding the significant digits. Raised to `1e-2`: these rate constants are
routinely ~1e-3, while `0.0177` still reads better than `1.77e-02`.

---

## 5. Design decisions

**A failed run is data, not a crash.** The best paper in the corpus documents two
abandoned methods (KKT: *"250 variables ... we have to give up"*; plain PSO:
*"takes a very long time to converge"*). Failed trials are recorded with
`status: failed`, their stderr tail, and a traceback log under `results/logs/`,
so that argument stays reconstructable.

**The protocol declares; the runner expands.** `varied: [beta in {0.1, 0.177,
0.25}]` with `held_fixed: [gamma, ...]` is a declaration. `expand_trials()` turns
it into concrete runs, flattening two-axis OAT to one-axis-at-a-time because
that is what OAT means — the corpus states it verbatim: *"In each parameter
analysis, we only varied that parameter while keeping the other parameters at
their default values."*

**Figures regenerate from atoms, not from saved arrays.** `FigureGenerator`
dispatches on `template_id` and reads values from the bound atoms at render
time. A sensitivity figure even derives its x-positions by parsing the swept
parameter out of each atom's `condition`, so the plot follows the sweep with no
hand-maintained x-array to fall out of sync.

**The build surfaces staleness.** `paper build` emits `FIG_STALE` / `TAB_STALE`
warnings, so a stale artifact is visible at the moment you would otherwise
submit.

---

## 6. Deliberately not built

| Not built | Why |
|---|---|
| parallel / distributed execution | a competition sweep is 3–30 ODE solves; `concurrent.futures` would add failure modes for no measurable gain |
| an experiment DSL | a Python function is more expressive than any YAML I would invent, and the user already knows Python |
| automatic figure-type inference | the template registry declares it; guessing from data shape produces confident wrong plots |
| sandboxing the experiment code | it is the user's own code running on their own machine |
| a database for runs | YAML + JSONL is diffable, greppable and survives a merge conflict; a DB would not |
| auto-fixing stale artifacts during build | the build must report, not silently rewrite the user's figures |

---

## 7. Phase 4 entry point

The critical path is now complete end to end. What remains is *interface*, not
mechanism:

1. **FastAPI + Vue3 panel.** Every command above already returns structured data;
   the panel is a view over `Store`, not new logic. The architecture doc's
   control panel (§16) is the spec.
2. **`mcm validate` as a hard gate.** `validate` and `paper build` both exit
   non-zero on error, so `./core/mcm validate || echo "DO NOT SUBMIT"` already
   works. A `--strict` mode that promotes chosen warnings (stale artifacts,
   uncited figures) to errors would make it a submission gate.
3. **More experiment templates.** Nine are declared in the registry; one has a
   reference implementation. The rest need the same treatment as
   `pcql_sensitivity.py`.

One honest limitation to carry forward: **staleness is recorded, not enforced.**
The build warns and `artifact stale` lists, but nothing *prevents* compiling a
paper with a stale figure. Given the corpus — where 74% of images are low-quality
screenshots and only 37% of figures are ever cited — a loud warning is the right
default, because a hard block would be worked around rather than fixed. Whether
it should become an error is a real question, and it needs a real answer before
this is a submission gate.
