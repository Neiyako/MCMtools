# Phase 1 — Core Schemas, Store, Templates, Validation

**Status: complete.** 87 tests passing. No dependency outside pydantic / pyyaml /
numpy for the Core layer.

Phase 1 delivers the object model and the integrity engine. It does **not**
compile LaTeX, generate figures, or run models — that is Phases 2+.

---

## 1. What was built

```
core/
  mcmcore/
    schemas/
      common.py       enums + MCMBase (all the anti-over-engineering defaults)
      model.py        Symbol Parameter Assumption Equation Model Baseline Coupling
      experiment.py   Varied Perturbation Metric Claim Experiment Run ResultAtom
      dataset.py      Dataset Column Transformation ColumnStats
      paper.py        Figure Table Reference Citation PaperSection AIUsage Paper
      project.py      Problem Task ProjectConfig
      __init__.py     flat import surface
    store.py          YAML round-trip + project layout
    templates.py      Template Registry (loader + schema)
    validate.py       audit engine (30+ checks, severity-calibrated)
    cli.py            argparse CLI (no click/typer, works offline)
  mcm                 launcher
  tests/              87 tests
templates/            35 corpus-grounded templates
examples/
  phase1_demo.py      end-to-end reconstruction of 2023 C/2307166
```

---

## 2. The three decisions that matter

### 2.1 `Result` is split into `Run` + `ResultAtom`

`Run` is a raw execution record (machine-written). `ResultAtom` is **one typed
number** — the single source of truth for every number in the paper.

This is the mechanism behind the whole tool. 69% of papers repeat a precise
number internally, and ~73% of Summary numbers reappear verbatim in the body.
If the paper stores `0.0832` as text, an audit cannot catch the divergence. If
it stores a *reference* to `RES-0142`, the divergence is impossible:

```python
atom = ResultAtom(atom_id="RES-0142", name="rmse", value=0.0791, format="%.4f")
atom.rendered()          # '0.0791'
```

The demo proves the follow-through: change one atom, and every bound figure and
table is reported **STALE**.

### 2.2 Absent values are representable, and default to `unknown`

Every field the modal paper does not supply is `Optional` or defaults to an
`UNKNOWN` enum member. This is measured, not lazy:

| Field | Corpus reality | Why the default must exist |
|---|---|---|
| `Symbol.role` | no paper supplies a state/decision/parameter taxonomy | requiring it breaks the majority |
| `Assumption.scope` | only 11% use model-scoped language | requiring it breaks 89% |
| `Assumption.label` | only 36% number their assumptions | numbering is inconsistent, so store don't derive |
| `Model.validation` | universal in practice, rarely under a heading | must allow an empty list |
| `Experiment.convergence_criterion` | **0 of 237** papers report a tolerance | never require |
| `Experiment.random_seed` | ~5%, mostly inside appendix code | record, never require |
| `NotationTable.exhaustive` | defaults **false** | the table is explicitly not the authority |

### 2.3 Severity is calibrated so a *winning* paper passes

The most important calibration: **uncited figures are a WARNING, not an error.**
Only 37% of figures and 33% of tables are cross-referenced in published papers,
while **100% of references** are. Making uncited figures fatal would fail most
Outstanding papers.

| Check | Severity | Corpus basis |
|---|---|---|
| OAT sweep with no `held_fixed` | **ERROR** | the invariant is the signature of a real experiment |
| AI used, no disclosure section | **ERROR** | COMAP policy; page-limit-exempt section required |
| duplicate equation number | **ERROR** | numbering is a paper-global counter |
| dangling model/atom/template ref | **ERROR** | internal inconsistency |
| summary-sheet placeholder | **ERROR** | must never ship |
| page count > 25 | **ERROR** | 72.1% of recent papers are exactly 25 |
| symbol redefined across models | WARNING | 17/383 papers do this legitimately |
| parameter without provenance | WARNING | 105/237 tabulate it |
| figure/table not cited in text | WARNING | 63% of Outstanding figures are uncited |
| "Literature Review" heading | WARNING | appears in **0 of 415** papers |
| no validation recorded | INFO | often folded into prose |
| roles all `unknown` | INFO | matches the modal paper |

---

## 3. Templates — the layer you asked to start from

35 templates, **every one carrying verbatim corpus evidence**. The registry
refuses to load a template that has none (enforced by a test), because a
template that is not grounded in the corpus is just an opinion.

| Kind | Count | Examples |
|---|---|---|
| `model` | 7 | ode_system, optimization_lp, evaluation_ahp, prediction_timeseries |
| `experiment` | 9 | sensitivity_oat, sensitivity_grid, robustness_noise, convergence_study |
| `figure` | 12 | sensitivity_line, heatmap_matrix, convergence, model_structure |
| `table` | 5 | parameter_settings, notation_table, metric_comparison |
| `paper` | 2 | comap_latex (with the official `.tex` bundled), section_spine |

### Two templates encode findings that reversed my instincts

**`paper.section_spine`** templates the *order*, not the *membership*. 83
distinct full orderings appear across 152 papers, but 14 pairwise precedence
relations hold at **100%**. So the spine is fixed and membership is free.

**`exp.sensitivity_oat`** requires `held_fixed`. 86% of modern papers run a
sensitivity analysis, overwhelmingly one-at-a-time with an explicit invariant:
*"we only varied that parameter while keeping the other parameters at their
default values."* An OAT sweep without a declared invariant is not
interpretable, so the validator errors on it.

The spine also records `never_template: [literature_review]`.

---

## 4. Two real bugs found and fixed

Both were caught by the tests, and both are now regression-tested.

**1. `SummarySheet.is_placeholder()` rejected valid input.** The original
implementation treated any single letter A–F as filler, so a correctly
filled-in problem letter `"C"` failed the audit. Fixed to check *absence*
rather than membership, and to detect filler team numbers by repeated-digit and
non-numeric patterns. `2307166` now passes; `1111111` and `ABCDEF` do not.

**2. In-place list mutation bypassed validation.** `validate_assignment=True`
catches attribute assignment but **not** `m.validation.append({...})` — the raw
dict survives inside a typed list and later serialises with a warning. Fixed by
re-validating on save (and via `MCMBase.revalidate()`), rebuilding from
`__dict__` rather than `model_dump()` so no warning fires before coercion. A
test confirms invalid data still raises.

---

## 5. Try it

```bash
python3 examples/phase1_demo.py          # end-to-end, on a real paper

./core/mcm --dir examples/demo_pcql status
./core/mcm --dir examples/demo_pcql model list
./core/mcm --dir examples/demo_pcql template show exp.sensitivity_oat
./core/mcm --dir examples/demo_pcql validate -v
```

`validate` exits non-zero on error, so it works as a pre-submission gate:

```bash
./core/mcm validate || echo "DO NOT SUBMIT"
```

Run the tests:

```bash
cd core && python3 -m pytest tests -q      # 87 passed
```

---

## 6. Deliberately NOT built in Phase 1

Each of these was considered and rejected on corpus evidence, not on effort:

| Rejected | Evidence |
|---|---|
| Sobol / Morris indices | Sobol <2%; Morris 2/237 with zero "elementary effects" |
| required convergence tolerance | **0 of 237** papers report one |
| ROC/AUC in the default metric registry | only **4 of 237** papers (a naive grep's 231 was false positives from "process") |
| Literature Review section template | **0 of 415** papers |
| data-versioning DAG with branching | papers show linear pipelines only |
| `environment` / conda spec capture | 0 papers |
| making uncited figures an error | 63% of Outstanding figures are uncited |
| a `Model` per script | papers present 2–4 named models |

---

## 7. Phase 2 entry point

The critical path from the architecture doc is
`schemas → store → experiment → results → paper(numbers) → audit`.
Phase 1 completes the first two and the last.

Phase 2 should build the **experiment runner** and the **LaTeX paper compiler**
with number macros, in that order, because the compiler can only be verified
once atoms exist. The runner's job is to populate `Run` and `ResultAtom`
records from a real computation and mark bound artifacts stale.
