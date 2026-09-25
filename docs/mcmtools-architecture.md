# MCMtools Architecture

> **Status:** design report, v1. Derived from the local MCM/ICM Outstanding paper corpus.
> **Scope:** this document specifies the system. It does not implement it.
> **Revision note:** every structural claim below is traceable to the corpus analysis in
> `docs/findings-*.md` (raw reports retained in `.analysis/`). Where the evidence contradicted an
> obvious design instinct, the evidence wins and the instinct is recorded as rejected.

---

## 0. How to read this document

The task asked for a tool that supports the real MCM/ICM production workflow. The single most
important thing the corpus taught us is that **most of the obvious design instincts are wrong**, and
the corpus says so quantitatively:

| Instinct | What the corpus actually shows | Consequence |
|---|---|---|
| "The paper template is Intro/Model/Results/Conclusion" | Only **2** headings exceed 80% presence (References 92.0%, Introduction 87.5%). 132 distinct heading variants exist. There are **83 distinct orderings across 152 papers**, but the *pairwise precedence* is **100%** for 14 relations. | Template the **spine order**, not the membership. |
| "Experiment = a Python script" | 86% of modern papers run a sensitivity analysis; the unit is a **sweep with a declared invariant** ("we only varied that parameter while keeping the other parameters at their default values"). | `Experiment` is a **sweep + protocol**, not a script. |
| "Model = model.py" | Papers present **2–4 named models** ("Model I: Lamprey Population Iteration Model"), with acronyms (APGM, PCQL, ESE), typed coupling, and an explicit baseline relation. | `Model` is a **mathematical identity** with symbols, equations, assumptions, coupling. |
| "Store results, format them at the end" | **69% of papers repeat a precise number within the paper**; **73% of Summary numbers reappear verbatim in the body**. `R²=0.8377` appears as `83.77%`, as `0.8377`, in a table cell, in prose, and in the abstract. | Numbers must be **single-sourced and rendered**, never typed twice. |
| "Figures are screenshots put into LaTeX" | **74% of embedded images are <500px wide.** Figures have doubled 2004→2024 (median 9→15). | Figures must be **generated artifacts** with a registry and provenance. |
| "Audit checks the paper compiles" | Only **37% of figures and 33% of tables are ever cross-referenced in text**, while references are **100%** cited. | Cross-reference integrity is a **real, measurable defect class**. |
| "Required sections are Abstract, Assumptions, Notations, Sensitivity, Strengths/Weaknesses..." | **"Literature Review" appears in 0 of 415 papers.** A Conclusion section *collapsed* from 67.2% to 36.0%. | Do not template conventions that don't exist. |
| "Papers are ~20 pages, be flexible" | **72.1% of 2022–2025 papers are exactly 25 pages** (IQR = [25,25]). | 25 pages is a **hard budget to compile against**. |
| "The contest is AI-free" | COMAP's own AI policy **permits** AI, **requires** disclosure, and mandates a page-limit-exempt **"Report on Use of AI"** section. | The AI boundary is a **compliance feature**, not just a design principle. |

**The one-sentence thesis:** MCMtools is a local, reproducible, traceable competition production
toolchain whose core value is that **the paper cannot silently disagree with the experiment**.

---

## 1. Current project structure analysis

### 1.1 What exists today

```
MCMtools/
├── start  start.sh  start.bat   # 启动入口（三平台，逻辑共用）
├── core/                        # 核心包 + pytest 测试
├── web/                         # 面板（原生 ES module，无构建步骤）
├── templates/                   # 模板库（101 个）
├── docs/                        # 文档
└── examples/                    # 示例项目
```

> 早期版本里还有 `MCM-ICM-master/`（433 篇往届论文语料）和
> `.analysis/`（分析脚本）。它们是**研究输入，不是软件本体** ——
> 每个模板的 `observed_in` 和 `evidence` 说法都来自那里。
> 现在已移出仓库（1.1G），分析结论保留在模板声明里。

**Finding: there is no MCMtools code.** No `frontend/`, no `backend/`, no Python package, no
`package.json`, no `pyproject.toml`, no `tests/`, no existing CLI. The repository is a **greenfield
project that happens to contain a research corpus**.

This is important for the migration story: **there is nothing to break and nothing to migrate.**
Every "do not delete existing functionality" constraint is vacuously satisfied. The risk profile is
therefore entirely about *building the wrong thing*, which is what this document exists to prevent.

### 1.2 The corpus, quantified

| Item | Count |
|---|---|
| PDFs total | 502 |
| Actual solution papers | **415** (87 are problem statements, results lists, judges' commentary) |
| Year span | 2004–2025 (2024 has 5 papers, 2025 has 0 in the O-award set) |
| Award composition | Outstanding 383, Meritorious 17, Honorable 8, Successful 4, Finalist 3 |
| Problem letters (tagged) | A 90, C 78, B 74, E 38, D 36, F 30; 69 untagged (2018/2019 dirs) |
| Median paper | **25 pages, 8,367 words, 12 figures, 4 tables, 8 numbered equations, 11 references** |

### 1.3 Reference assets inside the corpus worth extracting into MCMtools

These are **directly reusable specifications**, not just background reading:

| Asset | Path | Why it matters |
|---|---|---|
| **Official COMAP LaTeX template** | `2021美赛特等奖/problems/MCM-ICM_2021_Summary.tex` | The literal summary-sheet layout: `\Problem`, `\Team`, `newtxtext`/`newtxmath`, `fancyhdr` with `\rhead{Page \thepage}`, the `\thispagestyle{empty}` + `\vspace*{-16ex}` header table. This is the **page-1 contract**. |
| **Official Word template** | `problems/MCM-ICM_Summary.docx` | Secondary; confirms the summary sheet is a *form*. |
| **COMAP AI policy (2pp)** | `2025美赛特等奖/problems/Contest_AI_Policy.pdf` | Defines the **"Report on Use of AI"** compliance requirement. |
| **Triage judging guides (6 files)** | `2019美赛特等奖/2019年美赛初评标准/*.pdf` | COMAP's own statement of the five required modeling elements and, per problem, the specific scoring cliffs. |
| **Real competition datasets** | `problems/*.csv|xlsx|zip`, `2019.../2018_MCMProblemC_DATA/` | Ground truth for the Data Engine's real formats (ACS census CSVs with `_with_ann`/`_metadata` pairs, `.mat`, `.xlsx`, zipped multi-file). |
| **Problem statements, 2004–2025** | `*/problems/*.pdf` | Input side of the workflow; needed for the Problems module. |

The official COMAP triage guide states the required elements verbatim, and this is the authority the
Audit Engine must encode:

> "the MCM/ICM supports and advocates an iterative mathematical modeling process consisting of major
> elements that include: **Problem Restatement, Assumptions & Justifications, Model Construction and
> Application, Model Testing and/or Sensitivity Analysis, Analysis of Strengths & Weaknesses**."

---

## 2. Local paper structure analysis

Full evidence in `.analysis/findings-sections.md`, `-models.md`, `-experiments.md`, `-figures.md`.

### 2.1 Section structure — what is actually stable

**Methodological caveat, stated prominently.** The first-pass index under-detected headings
(recall 16.8% of all numbered headings, 42.9% of top-level). All conclusions below use a corrected
extractor or a manually validated sample. **Presence figures are lower bounds.**

**Vocabulary is not standardized (132 distinct variants).** The opening section is
**"Summary" (52.3%)**, not "Abstract" (13.7%). "Conclusion" 167 vs "Conclusions" 52. "Notations" 127
vs "Symbols" 45 vs "Notation" 31.

**Order *is* standardized.** Despite 83 distinct full orderings, the pairwise precedence relations
are near-deterministic:

```
Introduction → Assumptions → Notations → Sensitivity Analysis → Strengths & Weaknesses
Conclusion → References              (15/15, 100%)
Introduction is first in 108/152 (71.1%)
```
14 relations hold at **100%**. The single unstable relation is Conclusion vs Strengths&Weaknesses
(60%/40%).

**Presence tiers (N=415):**

| Tier | Sections | Template treatment |
|---|---|---|
| **MANDATORY >80%** | References 92.0%, Introduction 87.5% (+ the Summary sheet *form*, 76.6%) | Always emitted |
| **COMMON 40–80%** | Abstract/Summary 64.6%, Assumptions 57.1%, Conclusion 53.0%, Model 48.9%, Sensitivity 47.0%, Notations 45.1% | Toggles, **default on** |
| **OPTIONAL <40%** | Strengths&Weaknesses 38.6%, Restatement 37.8%, Our Work 36.4%, Appendix 33.0%, Background 30.6%, Data 12.0%, Model Evaluation 11.3% | **Free — never forced** |
| **ABSENT** | **Literature Review 0.0%** | **Never template** |

**Drift is real and directional (2004–10 → 2022–25):** Notations 9.3%→83.7%; Our Work 11.6%→72.1%;
Sensitivity 9.3%→66.3%; Restatement 11.6%→68.6%; Data 0%→26.7%; Model Evaluation 0%→34.9%.
Conclusion **collapsed** 67.2%→36.0%. The modern paper is more structured, more notation-driven, and
more evaluation-heavy than the historical average.

### 2.2 The 25-page constraint is the dominant design constraint

| Era | Median pages | IQR |
|---|---|---|
| 2004–2010 | 25 | (18.0, 33.0) |
| 2011–2016 | 23 | (20.0, 32.0) |
| 2017–2021 | 25 | (24.0, 29.0) |
| **2022–2025** | **25** | **(25.0, 25.0)** — 72.1% are *exactly* 25 |

**Implication:** the Paper Compiler must report a **live page count against the 25-page budget** as a
first-class number, and the TOC (universal: 100% of 2022–2025 papers) consumes budget.

### 2.3 Model structure

Typical paper: **2–4 named models**, one per task.

- **Naming:** `Model <N>: <Domain> <Function> Model`, e.g. *Lamprey Population Iteration Model*,
  *BDS Assessment Model*, *Adaptive Periodic Grid Model (APGM)*. Both `Model I/II/III` (209 tokens)
  and `Model 1/2/3` (701 tokens) are current — **sometimes mixed in one paper**.
- **Acronyms** are common for coined names: APGM, PCQL, ESE, I-ESE, LPRA, LPA, DIGNP, TCTM, GSRF.
- **Coupling is real and typed**, with four distinct kinds observed:
  1. **Decomposition** — parent *is* the union of children (ESE = economic + social + ecological)
  2. **Pipeline** — child consumes sibling output ("sub-model iii ... serves as a bridge between
     sub-models i and ii")
  3. **Shared-resource / feedback** — siblings exchange a named quantity (EEE model's tax variables)
  4. **Baseline/extension** — "From SIR Model to Our PCQL Model"
- **Baselines are named, cited, and reproduced with their own equations**, then modified. The
  improvement verb carries meaning: *inherits, based on, builds on, improving, extends, modified for,
  inspired by, adapts, optimizes, supplement to*.
- **Assumptions have two scopes** and the best papers say so: "The assumptions that are used in
  every model are summarized below. The additional assumptions for each individual model will be
  detailed along with the introduction and description of that model." (2016 A/44845; 2019 B/1908286
  even has a literal "**Assumptions in This Model**" heading).
  **But this is a minority practice: only 36% number assumptions, 39% justify them, 26% have an
  "Assumptions and Justification" heading, and only 11% use explicit model-scoped language.**
  → `scope` must exist and must default to `unknown`. A flat list is wrong; a *required* scope is
  equally wrong.
- **Notation tables exist in 56% of papers and are explicitly declared NON-EXHAUSTIVE** — five
  separate papers carry the disclaimer "There are some variables that are not listed here and will be
  discussed in detail in each section." **The notation table is not the symbol authority.**
- **Symbol collision is measurable**: 17/383 (4%, a conservative lower bound) literally redefine a
  symbol with two distinct meanings — `Chi` = genre-central-node vs artist-central-node
  (2021 D/2124497); `L` = lanes vs lanes-feeding-toll-plaza (2005 B/770) — plus a documented
  table-vs-body contradiction (`r1` in the 2024 A paper). **Hence model-scoped symbols with a
  `redefines` link.**
- **Equation numbers are a paper-global counter spanning models**, but **56% of papers never
  cross-reference an equation in prose** (median 0 explicit `Eq. (n)` references) — so equation
  *ownership* must be stored, never inferred from usage.

### 2.4 Experiment structure

- **86% of modern papers run a sensitivity analysis.** It is the most reliable anchor for "computation
  happened here." (Contrast: the heading "Numerical Simulation" appears **once** in 346 papers.)
- **The dominant design is one-at-a-time (OAT)**, with an explicitly stated invariant.
- **`parameters` must be first-class with provenance.** 105/237 papers have a parameter-captioned
  table; one paper declares **26 parameters + 6 initial conditions**; and papers carry an explicit
  provenance taxonomy verbatim: *"from literature (in a peer-edited research paper), from data (in
  official data sets), or calculated (constructed from our model and assumptions)."* Papers also
  openly flag weak values: *"endowed with a strong artificiality"*, *"merely an arbitrary given
  constant, since no such real data could be found"*.
- **Metrics are problem-type-dependent.** RMSE is C-only (49 of 53 occurrences); MAE is C-only
  (27/27); E/F use entropy weight (128) and TOPSIS; A uses Shannon diversity. **ROC/AUC appears in
  only 4 of 237 papers.** A fixed metric enum is wrong.
- **Seeds are almost never reported** (~5%, mostly inside appendix code). **Convergence tolerance is
  reported in 0 of 237 papers.** Trial counts *are* reported (30% of papers). **Do not require seeds.**
- **Failure reporting is load-bearing.** 83% of papers discuss weaknesses; 45% have a dedicated
  section. The best paper documents **two rejected methods** (KKT: "250 variables ... we have to give
  up"; plain PSO: "takes a very long time to converge and does not produce the optimal values")
  before the accepted one. Without a `failed` status, that argument is unreconstructable.
- **Every experiment has an anchor** and results are expressed as a **delta against it**.

### 2.5 The result→claim chain (the traceability contract)

Four fully transcribed chains (bootstrap→survival; cost sweep→self-limiting trading; 5-model metric
table→Stacking selection; growth-rate OAT→non-linear resilience) share a six-element shape:

```
protocol → baseline anchor → artifact (Fig/Table) → result atom (1–3 scalars) → claim sentence → downstream consumer
```

Example, fully traced (`2023 C/2310767.pdf`):

```
EXP: cross-validation of 5 models × 4 metrics
  ↓
TAB-003: Stacking | 1.6768 | 1.2949 | 0.8623 | 0.8377
  ↓
RES-ATOM: R² = 0.8377   (also reported as "83.77 %")
  ↓
CLAIM (body):   "the R2 of the Stacking model improves, and MSE, RMSE, and MAE all decrease"
CLAIM (abstract): "improves the goodness of fit of the prediction results to 83.77 %"
  ↓
DOWNSTREAM: the Stacking model is then used to predict the EERIE distribution [0,0,9,18,26,37,10]
```

**The minimum linkable unit is `(experiment → result_atom → sentence)`.** A script-plus-stdout model
reproduces none of these links. This is the core justification for the object model in §5.

### 2.6 Numbers are duplicated across carriers — the central hazard

| Measurement | Result |
|---|---|
| Papers with a ≥4-significant-digit value recurring within the paper | **164/237 = 69%** |
| Summary numbers that reappear verbatim in the body | **~73%** (8-paper validated sample) |
| Figures ever cross-referenced in body text | **37.3%** (751 figures, 60 papers) |
| Tables ever cross-referenced in body text | **32.6%** (239 tables, 60 papers) |
| References cited in text | **100.0%** (707 refs) |

Concrete case: `2024 A/2400996.pdf` reports `R = 73.3%` in the **Summary**, in **§4.2.1**, and derives
it from `S1 = 3.7175·10⁻⁴` / `S2 = 6.4414·10⁻⁴` computed in the experiment. Three carriers, one
source value, zero enforcement.

### 2.7 Figure and visualization findings

- Figure count has **nearly doubled**: median 9 (2004–2010) → 15 (2022–2025). Median 12 overall.
- **74% of embedded raster images are <500px wide** — most figures are low-quality screenshots.
- Captions are mostly terse; 61.5% carry no classifying keyword. Table captions *do* carry protocol
  detail ("mean and standard deviation ... of 30 independent runs", "1% random noise of initial value").
- Figure types observed (by caption + content): line/trend, bar, scatter, heatmap/correlation matrix,
  sensitivity/sweep, flow/process diagram, network/graph, map/geographic, model-structure diagram,
  convergence curve, prediction-fit, residual/error, box plot, 3D surface, schematic/photo.

---

## 3. The actual MCM workflow (as observed)

Reconstructed from paper structure, COMAP's triage guides, and the AI policy:

```
Contest opens
   ↓
Read problem statement(s) A–F  ──┐
Understand data / attachments    │  ~0–12h
Choose ONE problem               │
   ↓                             ┘
Problem restatement
   ↓
Assumptions (paper-scope)
   ↓
Data acquisition + cleaning ────────────┐
   ↓                                    │
Notations (grows as models appear)      │
   ↓                                    │
Model I  (mathematics)                  │  ~12–60h, iterative
   ↓                                    │  and non-linear:
Experiment(s) on Model I                │  results force model
   ↓                                    │  revision
Result atoms → Figures/Tables           │
   ↓                                    │
Model II consumes Model I's output      │
   ↓                                    │
... repeat per task ...                 │
   ↓                                    │
Sensitivity / Robustness analysis ──────┘
   ↓
Strengths & Weaknesses
   ↓
Conclusion
   ↓
References + Appendix (+ Memorandum, optional)
   ↓
Fit to 25 pages ───────────────────────┐
   ↓                                   │  hardest constraint;
Compile PDF                            │  forces cuts and
   ↓                                   │  re-verification
Submit                                 ┘

[post-report] "Report on Use of AI" — page-limit exempt, COMAP-mandated if AI was used
```

**Key observations that shape the design:**

1. **The process is iterative, not linear.** Results force model revision. The tool must tolerate
   re-running an experiment and *propagating* the change, not assume append-only.
2. **Model II consuming Model I's output is structural**, not incidental — it is stated in the
   summaries.
3. **The 25-page limit is an active agent in the process.** It drives which sensitivity analyses are
   shown ("to save space, the sensitivity analysis graphs of the multiple population model were not
   listed") and which sections survive.
4. **Sensitivity analysis is the universal "did you actually test it" signal.**
5. **Problem choice happens once, at the start.** After the lock, the other problems are irrelevant.

---

## 4. MCMtools workflow

MCMtools mirrors the above but makes each arrow **explicit, recorded, and checkable**:

```
Problems ──→ Analysis ──→ [HUMAN CHOOSES] ──→ LOCK
                                                │
                                                ▼
   ┌────────────────────────────────────────────────────────┐
   │  Datasets ──→ Model(s) ──→ Experiment(s) ──→ Result     │
   │                    ▲              │              │      │
   │                    └──────────────┘              ▼      │
   │                     (revision loop)     Figure / Table  │
   │                                                │        │
   │                                                ▼        │
   │                              Paper Sections ← Content   │
   │                                     │                   │
   │                                     ▼                   │
   │                              Paper Compiler → PDF       │
   │                                     │                   │
   │                                     ▼                   │
   │                              Audit Engine → verdict     │
   └────────────────────────────────────────────────────────┘
```

**Division of labour, stated once and enforced everywhere:**

```
HUMAN      makes every mathematical decision:
           which model, which assumptions, which parameters,
           what the result means, what the conclusion is.

MCMTOOLS  executes, records, checks, propagates, renders:
           runs the code, stores provenance, verifies that the
           number in the abstract equals the number the
           experiment produced, renders figures, compiles LaTeX,
           and refuses to silently ship an inconsistency.
```

The tool must never pretend to choose a model. Its value is **not lying**.

---

## 5. MCMtools Object Model

### 5.1 Verdict on the proposed object list

| Proposed | Verdict | Reason |
|---|---|---|
| `Problem` | **Keep** | Needed pre-lock; gains a `status` (candidate/analysed/chosen/rejected). |
| `Model` | **Keep, greatly expand** | Cannot be a file. Needs symbols, equations, assumptions, coupling (§6). |
| `Dataset` | **Keep** | But must be a *versioned* object with lineage (§8). |
| `Experiment` | **Keep, redefine** | Not a script — a sweep with protocol and invariant (§7). |
| `Result` | **Split** | Becomes `Run` (raw execution) + `ResultAtom` (a single typed number). This is the key correction. |
| `Figure` | **Keep** | Generated artifact with registry provenance (§9). |
| `Table` | **Keep** | Same, plus numeric binding to ResultAtoms. |
| `Equation` | **Keep** | Paper-global numbering, model-scoped ownership. |
| `PaperSection` | **Keep** | The unit that binds prose to ResultAtoms. |
| `Citation` | **Keep** | 100% cited-in-text, so integrity is enforceable. |
| `Audit` | **Keep** | But an *engine producing a report*, not an object. |

**Missing objects that the corpus requires:**

| New object | Why the corpus demands it |
|---|---|
| **`Symbol`** | Notation tables (56% of papers), symbol collision (4%), redefinition, unit columns. A paper-level flat list is provably wrong. |
| **`Assumption`** | Has `scope` (paper/model/section), optional `label`, optional `justification`, and is *referenced by* derivations. A text blob loses all of this. |
| **`Parameter`** | 26 parameters in one paper, each with provenance (`literature`/`data`/`fitted`/`assumed`), a source citation, sometimes candidate values and an explicit selection. |
| **`Claim`** | The sentences a ResultAtom supports. This is the traceability join that makes numeric auditing possible. |
| **`Task`** | COMAP problems have explicit sub-tasks ("Part 1", "(1)...(4)", "task 2"), and models are organized one-per-task. |
| **`Reference/Template`** | Templates are first-class reusable knowledge (§12). |
| **`AuditFinding`** | Audit output needs severity, location, and a machine-readable code to be actionable. |

**Objects deliberately NOT created** (anti-over-engineering, evidence-backed):

| Rejected | Why |
|---|---|
| `Agent` / `LLMCall` | Competition mode is offline by design; no runtime AI object needed. |
| `Environment` / conda spec | **0 papers state one.** 48% name only a tool (MATLAB/Python). Model `software` as a string. |
| `ConvergenceTolerance` | **0/237 papers report one.** Can be an internal run property; never a required field. |
| `Ablation` (as a distinct type) | The word appears **0 times** in the modern corpus. Model it as `variant_of` + `removed_components`. |
| `KnowledgeGraph` | No evidence papers need it. The typed relations already in `Model.coupling` and `ResultAtom.claims` suffice. |
| `AutoML` / `ModelSelector` | Directly contrary to the tool's positioning. Human decides. |

### 5.2 The object graph

```
Task ──────┐
           │
Problem ───┼──→ Model ──┬──→ Symbol ────┐
           │            ├──→ Equation   │ (model-scoped)
           │            ├──→ Assumption │
           │            └──→ Parameter ─┘
           │                  │
Dataset ───┴──────────────────┼──→ Experiment ──→ Run ──→ ResultAtom
                              │        │                        │
                              │        └──→ Figure             │
                              │        └──→ Table ─────────────┤
                              │                                 │
PaperSection ────────────────┴──→ Claim ─────────────────────────┘
   │
   ├──→ Citation ──→ Reference
   └──→ Equation (paper-global numbering)
                              │
                              ▼
                     Paper Compiler ──→ PDF
                              │
                              ▼
                        Audit Engine ──→ AuditFinding[]
```

### 5.3 Object summary table

| Object | What it is | Saves | Relations (out) | Created by | Modified by | Read by |
|---|---|---|---|---|---|---|
| **Problem** | A competition problem statement | id, year, letter, title, statement ref, tasks, status | → Task[], → Dataset[] | Human (import) | Human | Analysis, Paper |
| **Task** | A numbered sub-question | id, text, requirement refs | → Model[] | Human | Human | Model, Audit |
| **Model** | A mathematical identity | id, label, name, acronym, purpose, kind, symbols, equations, assumptions, params, coupling, baseline | → Symbol[], → Equation[], → Assumption[], → Parameter[], → Model[] | Human | Human | Experiment, Paper, Audit |
| **Symbol** | A mathematical symbol | id, glyph, meaning, role, unit, domain, redefines | → Model | Human | Human | Paper (Notations), Audit |
| **Parameter** | A named constant of a model | id, name, value, unit, source_kind, source_ref, candidates, confidence, scope | → Model, → Citation | Human | Human, Experiment(fit) | Experiment, Paper, Audit |
| **Assumption** | A modelling assumption | id, text, scope, label, justification | → Model/PaperSection | Human | Human | Paper, Audit |
| **Equation** | A numbered equation | id, number, latex, role, is_numbered, conditions, uses | → Model, → Equation[] | Human | Human | Paper, Audit |
| **Dataset** | A versioned data asset | id, name, source, version, stage, schema, lineage, stats | → Dataset (parent) | Human, DataEngine | DataEngine | Experiment, Paper |
| **Experiment** | A protocol: what varies, what's fixed | id, kind, model, dataset, varied, held_fixed, method, n_runs, software, status, motivation | → Model, → Dataset, → Experiment[] | Human, Template | Human | Run, Paper |
| **Run** | One execution of an Experiment | id, experiment, params_resolved, seed, started, duration, exit, artifacts | → Experiment | **Core (automatic)** | — | ResultAtom |
| **ResultAtom** | **One typed number** | id, name, value, unit, format, condition, run, metric_def | → Run, → Experiment | **Core (automatic)** | — | Figure, Table, Claim, Audit |
| **Figure** | A generated visual artifact | id, template_id, inputs, file, format, caption, width, dpi | → ResultAtom[], → Experiment | Core + Template | Human (caption) | Paper, Audit |
| **Table** | A generated tabular artifact | id, template_id, columns, rows, caption, label | → ResultAtom[] | Core + Template | Human | Paper, Audit |
| **PaperSection** | A section of the paper | id, kind, title, level, order, template_ref, body | → Claim[], → Figure[], → Table[], → Citation[] | Human + Template | Human | Compiler, Audit |
| **Claim** | A sentence supported by results | id, text, claim_type, result_atoms, location | → ResultAtom[] | Human | Human | Audit |
| **Citation** | An in-text reference marker | id, key, section, context | → Reference | Human | Human | Compiler, Audit |
| **Reference** | A bibliography entry | id, key, bibtex, type, ai_generated | — | Human | Human | Compiler, Audit |
| **Template** | Reusable knowledge/程序 | id, kind, version, inputs, outputs, entrypoint | — | Developer | Developer | Everything |
| **AuditFinding** | One audit result | id, code, severity, object, message, evidence | → any | **Audit Engine** | — | Human, UI |

**The critical row is `ResultAtom`.** It is the single source of truth for every number in the paper.
Everything downstream *renders* it; nothing re-types it.

---

## 6. Model Schema

The corpus analysis (`findings-models.md`) shows a single `model.py` cannot express what papers
actually contain. Full schema, with a `[REQ]`/`[COM]`/`[OPT]` marker justified by corpus frequency.

```yaml
# model.yaml  — lives at models/M03/model.yaml
model_id: M03
label: "Model III"            # [REQ] papers use both "Model III" and "Model 3", sometimes mixed
label_style: roman            # [REQ] roman | arabic | mixed | none
name: "Adaptive Periodic Grid Model"          # [REQ] 86% of papers name models
acronym: APGM                 # [COM] coined names almost always get one (APGM, PCQL, ESE, GSRF)
title_form: plain             # [OPT] plain | numbered-hyphenated | prefixed-acronym
one_line_purpose: >           # [REQ] papers state this in one sentence
  Adapt grid boundaries and position using ARIMA/MA prediction
  and backtest-driven parameter updates.

# --- position in the paper ---
section_ref: "5"              # [REQ]
order: 3                      # [REQ]
task_refs: [T1, T2]           # [REQ] the dominant organizing principle is one model per task
section_split:                # [COM] papers split "Establishment" from "Solution" per model
  establish: "5.3"
  solve: "5.4"

# --- structural role ---
kind: prediction              # [REQ] simulation | optimization | prediction | evaluation
                              #       | classification | assessment | accounting
                              #       | equilibrium | composite
parent_model_id: null         # [COM] composite models are real ("combination of three submodels")
role_in_parent: null          # [COM] component | output_producer | input_consumer
                              #       | bridge | baseline | extension
relation_to_siblings: sequential   # [REQ] sequential | parallel | independent | hybrid

# [REQ] four distinct coupling kinds are observed in real papers
coupling:
  - from: M03.predictor
    to: M03.decision
    via: "ARIMA forecast p̂(t)"
    kind: output
  - from: M03.decision
    to: M03.backtest
    kind: feedback

# --- baseline positioning ---
baseline:                     # [REQ] universal: "From SIR Model to Our PCQL Model"
  ref: "Forex Grid strategy"
  citation: "[7]"
  is_internal_model_id: null  # baseline may be external-with-citation OR a sibling model
improvement_verb: extend      # [REQ] inherit|build_on|extend|modify|improve|adapt
                              #       |optimize|inspire|supplement
improvement_delta: >
  Added moving-average and ARIMA prediction to shift grid boundaries
  according to forecast trend.
is_baseline_for: [M04]        # [COM] a model can be both baseline AND an independent entry
                              #      ("three independent, generic mathematical models" yet one
                              #       "serve[s] as a good baseline for comparison")
# [COM] SEPARATE from `baseline`: real papers express both relations at once.
# 2021/B/2102199: "This model is actually a supplement to Model I ... utilize the
# method of Model I to rebuild the drone network" — a relation ("supplement") AND a
# method transfer ("uses_method_of") in one sentence. Collapsing them loses the
# distinction between "I extend X" and "I reuse X's technique on a new object".
uses_method_of: [M01]

# --- mathematics ---
symbols:                      # [REQ] model-scoped, NOT paper-scoped
  - symbol: "p_max"
    meaning: "upper grid boundary price"
    role: parameter           # state|decision|parameter|derived|index|exogenous|metric|unknown
                              #   ^ DEFAULT MUST BE `unknown`: only a minority of papers
                              #     separate these, so requiring a taxonomy breaks them
    unit: "USD"
    domain: null
    redefines: null           # [COM] 4% of papers literally redefine a symbol
    time_varying: false

# [REQ] The Notations table is a paper-level VIEW over model-scoped symbols.
# Near-universal corpus disclaimer: "There are some variables that are not listed
# here and will be discussed in detail in each section." (5 papers verbatim).
# => the table must NEVER be treated as the authoritative symbol scope.
notation_table:
  exhaustive: false           # default false; drives the standard disclaimer
  disclaimer: "There are some variables that are not listed here and will be
               discussed in detail in each section."
  unit_column: true           # [COM] a real minority carry units ("/" = dimensionless)

parameters:
  - name: "G/B ratio"
    value: null               # computed per period
    unit: "/"
    source_kind: derived      # [REQ] literature|dataset|fitted|assumed|derived|semi_educated_guess
    source_ref: null
    candidate_values: []      # [COM] papers print REJECTED candidates too (k=0.3,0.21,0.5*,0.543)
    confidence: null          # [REQ] papers admit "strong artificiality", "arbitrary given constant"
    scope: null               # [COM] per-region / per-species / per-scenario parameter sets

assumptions:                  # [REQ] TWO SCOPES; the best papers state the distinction explicitly
  - label: "Assumption 3"
    text: "Transaction costs are proportional to trade volume."
    scope: model              # paper | model | section   <-- the crucial distinction
    justification: "Brokerage fees in the provided dataset are volume-based."

equations:
  - number: "7"               # [REQ] paper-GLOBAL counter spanning models
    latex: "p_{\\max} = \\lambda_3 p_{\\max}(T_1, T_i)"
    role: definition          # governing|definition|constraint|objective
                              # |transformation|metric|calibration
    is_numbered: true         # [COM] some governing equations are display-unnumbered
    conditions: null          # [COM] initial/boundary conditions are part of the model statement
    uses: ["M03:5"]           # [COM] only 44% of papers cross-reference, but those rely on it

objective:                    # [COM] some models have TWO competing objectives, some none
  expressions: ["min \\sum_i W_i"]
  sense: min                  # min | max | dual | none

constraints: []               # [COM] present and separately listed in optimization models
decision_variables: []        # [COM] explicit in optimization papers

solution_method: "Nelder-Mead over backtest MSE"   # [REQ] papers name it ("Using Lingo")
algorithm: null               # [OPT] some papers print a formal Algorithm block
software: "Python"            # [REQ] 48% of papers name a tool

validation:                   # [COM] validation is universal in practice, often inline
  - kind: held_out            # external_data|literature|held_out|cross_validation
                              # |statistical_test|internal_agreement|bootstrap_interval
                              # |transfer_case_study|sensitivity|none_stated
    description: "Backtested on 5 years of historical prices"
    metric: "profit ratio"
    value: 42.271

sensitivity_analysis:         # [REQ] 86% of modern papers run one
  parameters: ["cost_gold", "cost_btc"]
  ranges: "cost ∈ {0.01, 0.02, 0.03}"
  conclusion: "Model self-limits high-frequency trading as costs rise."

limitations:                  # [REQ] model-scoped, distinct from paper-level weaknesses
  - text: "Backtest performance depends on regime stability."
    kind: parameter_uncertainty

strengths: []                 # [COM] attributed per model by name in papers
limitations_kind: []          # structural|formula_ungrounded|parameter_uncertainty
                              # |aggregation_loss|data_insufficiency|temporal_scope
                              # |validation_weakness|underperforms_baseline|other

shared_symbols_with:          # [COM] integrity field — enables collision warning
  - model_id: M01
    symbol: "r1"
    relation: redefined        # identical | redefined | derived

consumes: []                  # [COM] enables the pipeline DAG
produces: ["grid_state", "positions"]

figure_refs: ["FIG-005"]      # [COM] models are introduced with a mindmap/framework figure
table_refs: []
data_sources: ["DS-001"]
citations: ["[7]", "[10]"]
```

**Design notes:**

- `role` on symbols, `scope` on assumptions, and `label` on models all default to
  `unknown`/`none`. **64% of papers do not number assumptions and 44% have no notation table**;
  requiring these would make the schema unusable on the majority of real papers. This is an
  anti-over-engineering decision grounded in measurement.
- `symbols` is **model-scoped**, not paper-scoped. The Notations *page* is a paper-level *view*
  generated by merging model-scoped symbols — which also lets the tool detect collisions.
- `validation` may be an empty list. Validation is near-universal **in practice but almost never
  under a heading called "Validation"** — it is folded inline into results prose. Six distinct kinds
  are attested and they are not interchangeable: (a) external data/literature ("Pearson correlation
  coefficient is 0.8002"), (b) held-out / cross-validation ("K-Fold Cross Validation with k=3"),
  (c) significance tests ("R² and p-values ... 0.767, 4.13×10⁻⁴"), (d) **agreement between the
  paper's own models** ("the two models qualitatively agree" — and, importantly, the converse
  "notably inconsistent results"), (e) bootstrap intervals ("1000 Bootstrap samples ... 2.5% and
  97.5% quantiles"), (f) transfer case study ("We examined its application in Yellowstone National
  Park").
- **A distinct act worth its own field: validating an *assumption*, not a model.** 2016 A/44845
  validates against an external tool — "This assumption was validated using property values from the
  XSteam MATLAB function". This is `assumption_validation`, not `validation`.
- **Dimensional analysis was not observed** in the corpus. Do not build a checker for it.

---

## 7. Experiment Schema

**The redefinition.** An Experiment is **not a script**. It is a *protocol*: a declared variation
applied to a model+dataset, producing typed result atoms.

```yaml
# experiments/EXP-026/experiment.yaml
experiment_id: EXP-026
label: "Transaction cost sensitivity"
kind: sensitivity_oat        # [REQ] controlled enum — see below
model_id: M03
dataset_id: DS-001
task_refs: [T2]
section_ref: "7.1"           # [REQ] every experiment lives under a numbered section

# --- lineage: the DAG, not a list ---
parent_experiment_ids: [EXP-021]   # [REQ] experiments consume other experiments' outputs
variant_of: EXP-021                # [COM] ablations are 34% of papers but never called "ablation"
removed_components: []             #       model them via variant_of, not a separate type
supersedes: null
superseded_by: null

# --- motivation: REQUIRED, because papers always give one ---
motivation: >
  Transaction cost rate has a large impact on profit; traditional grid
  strategy produces meaningless losses without frequency limits.
uncertainty_rationale: >
  Cost parameters are external and likely to drift.

# --- the protocol ---
varied:                      # [REQ] THE defining axis of a non-trivial experiment
  - name: "cost_gold"
    values: [0.01, 0.02]
    range: null
    step: null
  - name: "cost_btc"
    values: [0.01, 0.02, 0.03]
    range: null
held_fixed:                  # [REQ] the OAT invariant, stated verbatim in real papers
  - "grid model logic"
  - "historical price series"
  - "5-year backtest window"
varied_axis: parameter       # [COM] parameter | model_identity | input_data | structure | none

method: backtest             # [REQ] named in nearly every computation
baseline_ref:                # [REQ] every chain is expressed as a DELTA against an anchor
  kind: experiment
  ref: EXP-021
  description: "default cost assumption"

n_runs: 6                    # [REQ] 30% of papers state an explicit count (9…10000)
n_folds: null                # [COM] cross-validation
aggregation: mean            # [COM] always stated where multiple runs exist
perturbation: null           # [COM] robustness always declares the kernel:
                             #       {distribution: gaussian, magnitude: 0.01, applies_to: input}
readout_condition: "end of 5-year window"   # [REQ] "t=1000", "year 50", "March 1, 2023"

max_iterations: null         # [COM]
convergence_criterion: null  # [OPT] 0/237 papers report a numeric tolerance
converged_at: null           # [COM] papers use this as a RESULT ("converges after 50 iterations")
hyperparameters: {}          # [COM] GA: population 200, mutation 0.4, crossover 0.1
train_test_split: null       # [COM] "80% training / 20% testing"

software: "Python 3.11"      # [REQ] 48% name a tool
random_seed: null            # [OPT] only ~5% of papers; NEVER require it
runtime_seconds: null        # [OPT] 3%; but decisive when a method was rejected for slowness

# --- outcome ---
status: completed            # [REQ] planned | running | completed | failed | rejected | superseded
                             #   ^ `failed`/`rejected` is load-bearing: the best paper documents
                             #     two rejected methods before the accepted one
failure_reason: null
metrics:                     # [REQ] problem-type-dependent, NOT a fixed enum
  - name: "trade_count"
    value: 42
    unit: "count"
    direction: lower_is_better
outputs: {}                  # [REQ] typed result atoms (see below)
figures: [FIG-011]           # [REQ]
tables: [TAB-008]
claims: [CLM-014]            # [REQ] the sentences this experiment supports

caveats:                     # [REQ] 83% of papers discuss weaknesses
  - kind: regime_dependence
    text: "Results may not transfer to a different market regime."
```

### 7.1 The Experiment kind registry

From the corpus, with the fraction of modern papers using each:

| `kind` | Frequency | What varies | What's fixed | Templatable? |
|---|---|---|---|---|
| `sensitivity_oat` | **~42%** | 1 parameter over a range | all else + data | **YES — primary template** |
| `sensitivity_grid` | ~5% | 2 parameters | all else | **YES** |
| `model_comparison` | 14% | model identity | data, protocol, metrics | **YES** |
| `robustness_noise` | 5% (heading), 10% (practice) | input values + noise kernel | model, data | **YES** |
| `monte_carlo` | 6% | random draw, N times | structure, N | **YES** |
| `cross_validation` | 5% | fold assignment | model, data | **YES** |
| `optimization_run` | 10% (GA), 4% (SA) | search params | objective, constraints | partial |
| `convergence_study` | 22% (discussed) | iterations | model | partial |
| `simulation` | 72% (keyword) | state evolution | structure | partial |
| `train_test` | common in C/D | split ratio | model | **YES** |
| `scenario` | 7% | scenario definition | model | **YES** |
| `backtest` | 1% | time window | strategy rules | domain-specific |
| `error_analysis` | 2% (heading) | — | — | **YES** |
| `ablation` | 34% (practice, unnamed) | removed component | rest | via `variant_of` |
| `sobol` | <2% | all params jointly | — | **NO — do not build** |

**Recommendation:** ship templates for the first eight. Do **not** build Sobol/Morris machinery —
Sobol appears in <2% of papers and Morris appears in 2/237 with zero "elementary effects"
occurrences. Users who need them write a script.

### 7.2 The Core/Interface/Template split for experiments

This is where the task's §13 requirement bites. An Experiment has three distinct layers:

```
TEMPLATE   experiments/templates/sensitivity_oat/
             ├── template.yaml    (declares params, defaults, required model outputs)
             └── run.py           (generic implementation — calls Core only)

CORE       core/experiment/
             ├── runner.py        (resolves params, executes, captures Run record)
             ├── sweep.py         (expands `varied` into concrete trials)
             └── results.py       (emits typed ResultAtoms)

INTERFACE  cli: mcm exp run EXP-026
           api: POST /api/experiments/EXP-026/run
           ui:  Experiment detail → Run button
```

The **template** holds reusable knowledge (what a sensitivity sweep *is*). The **core** executes it.
The **interface** invokes the core. No layer reaches into another's concerns.

---

## 8. Dataset Schema and the Data Engine

### 8.1 Verdict on the proposed pipeline

The proposed `raw → cleaned → processed → features → model input → results` is **broadly right but
incomplete in three evidence-backed ways**:

1. **`results` is not a data stage.** Results are `ResultAtom`s produced by `Experiment`. Mixing them
   into the data lineage conflates two object types. **Drop `results` from the data pipeline.**
2. **Versioning and lineage are missing.** Papers re-derive data across scenarios; the tool must be
   able to answer "which dataset version produced this number?"
3. **EDA is a first-class artifact, not a step.** Papers have explicit data chapters (12% and rising
   to 26.7% in 2022–25) with cleaning sections and summary statistics that go straight into the paper.

### 8.2 Revised data model

```
raw/          immutable, exactly as downloaded (never modified)
  ↓  ingest
staged/       parsed, typed, schema-checked (typed column names, dtypes)
  ↓  clean
cleaned/      missing values handled, outliers flagged, units normalized
  ↓  transform
processed/    normalized/scaled, joined, aggregated
  ↓  derive
features/     model-ready feature matrices
  ↓  (consumed by Experiment)
```

**Every stage is an immutable, hash-addressed Dataset version.** A stage never overwrites its input.

```yaml
# data/DS-001/dataset.yaml
dataset_id: DS-001
name: "Wimbledon featured matches 2023"
source:                     # [REQ]
  kind: competition_provided  # competition_provided | external | derived | simulated
  ref: "2024 MCM Problem C"
  url: null
  retrieved: null
version: 3                  # [REQ] immutable; bump on any change
stage: processed            # [REQ] raw | staged | cleaned | processed | features
parent_dataset_id: DS-001@2 # [REQ] lineage
content_hash: "sha256:..."  # [REQ] reproducibility

files:
  - path: "processed/matches.parquet"
    rows: 4031
    bytes: 512340
schema:                     # [REQ] drives EDA tables and validation
  - name: match_id
    dtype: string
    unit: null
    nullable: false
  - name: p1_distance_run
    dtype: float64
    unit: "m"
    nullable: true
    missing_count: 12
    outlier_count: 3

transformations:            # [REQ] the audit trail: what was done, in order
  - step: drop_duplicates
    params: {subset: [match_id, point_no]}
    rows_before: 4031
    rows_after: 4031
  - step: impute_missing
    params: {column: speed_mph, method: median}
    rows_affected: 12

stats:                      # [COM] feeds the EDA section directly
  numeric:
    - column: p1_distance_run
      mean: 12.4
      std: 5.1
      min: 0.0
      p25: 8.2
      median: 11.1
      p75: 15.9
      max: 42.0

eda:                        # [COM] figures/tables generated from this dataset
  figures: [FIG-001]
  tables: [TAB-001]

used_by_experiments: [EXP-026]
citations: ["[3]"]
```

**What we deliberately do NOT build:** a full data-versioning DAG engine with branching, merging, and
automatic invalidation. Papers show **linear** data pipelines with at most one scenario split. A
simple `parent_dataset_id` chain plus content hashes is sufficient and far cheaper. This is a
deliberate YAGNI call.

---

## 9. Result, Figure, and Table Schemas

### 9.1 Result: Run + ResultAtom (the key split)

```yaml
# Runs are machine-written records of what actually executed
run_id: RUN-026-003
experiment_id: EXP-026
resolved_parameters: {cost_gold: 0.01, cost_btc: 0.02}
random_seed: null             # recorded if the code sets one; never required
started_at: "2025-01-25T14:03:11Z"
duration_seconds: 12.4
exit_code: 0
software: "Python 3.11.4"
artifact_paths: ["runs/RUN-026-003/stdout.log"]

# ResultAtoms are the SINGLE SOURCE OF TRUTH for every number in the paper
result_atom_id: RES-0142
run_id: RUN-026-003
name: "profit_ratio"
value: 42.271
unit: "ratio"
format: "%.3f"                 # the canonical rendering
condition: "cost_gold=0.01, cost_btc=0.02"   # a value is meaningless without its condition
metric_def: "final_equity / initial_equity"
direction: higher_is_better
```

**Why this split matters.** The corpus shows a value must be comparable across four carriers
(abstract, prose, table cell, figure caption) and across two representations (`83.77 %` ↔ `0.8377`).
A `ResultAtom` with a canonical `format` and an explicit `condition` is what makes that comparison
mechanical instead of hopeful.

### 9.2 Figure: a generated artifact, not a screenshot

The corpus shows **74% of embedded images are <500px wide** — the current practice produces poor
figures. MCMtools generates figures as **vector PDF** from `ResultAtom`s.

```yaml
figure_id: FIG-011
template_id: "fig.sensitivity_line"    # from the Figure Template Registry (§12)
experiment_id: EXP-026
inputs:                                 # bound to ResultAtoms, never to raw literals
  - {atom: RES-0142, role: y}
  - {atom: RES-0143, role: x}
  - {atom: RES-0144, role: series_label}
file: "figures/FIG-011.pdf"            # vector
format: pdf                            # pdf (vector) | png (raster, fallback only)
width_in: 6.0
dpi: null
caption: >
  Trading frequency and final profit under different transaction
  cost rates.
caption_source: human                  # human | template_suggested
label: "fig:cost_sensitivity"
referenced_in: ["§7.1"]                # [AUDIT] empty here => a real defect
status: generated                      # generated | stale | missing
```

**`status: stale`** is important: when `RES-0142` changes, every figure bound to it becomes stale
and must be regenerated. This is how figure/result divergence is prevented.

### 9.3 Table

```yaml
table_id: TAB-008
template_id: "tab.metric_comparison"
experiment_id: EXP-026
columns:
  - {header: "Model", source: literal}
  - {header: "MSE",  atom: RES-0201, format: "%.4f"}
  - {header: "RMSE", atom: RES-0202, format: "%.4f"}
  - {header: "MAE",  atom: RES-0203, format: "%.4f"}
  - {header: "R2",   atom: RES-0204, format: "%.4f"}
rows:
  - {literal: "Lasso",    atoms: [RES-0201, RES-0202, RES-0203, RES-0204]}
  - {literal: "Stacking", atoms: [RES-0221, RES-0222, RES-0223, RES-0224]}
caption: "Cross-validation performance of candidate models."
label: "tab:model_comparison"
referenced_in: ["§6.1"]
status: generated
```

**Tables are bound to `ResultAtom`s cell-by-cell.** This is what makes the Table audit in §11
mechanical: a table cell can never disagree with the experiment, because it *is* the experiment's
output rendered.

---

## 10. Paper Schema, Citation Schema

### 10.1 Paper Schema — the Template/Content boundary

This is the task's §4 question, and the corpus answers it precisely.

```yaml
# paper/paper.yaml
paper_id: PAPER-001
problem_id: P-2025-A
locked: true                   # after problem lock, problems A–F leave the UI (§17)

summary:                       # page 1 — the COMAP FORM, not a section
  problem_letter: "A"          # from the official template's \Problem
  team_control_number: "2400996"   # \Team
  body: sections/00-summary.md
  key_words: ["lamprey", "sex ratio", "Lotka-Volterra"]

sections:                      # ORDER IS FIXED TO THE SPINE (§2.1); membership is free
  - {id: S01, kind: introduction,  title: "Introduction",              template: default, enabled: true}
  - {id: S02, kind: restatement,   title: "Restatement of the Problem", template: default, enabled: true}
  - {id: S03, kind: assumptions,   title: "Assumptions and Justifications", template: default, enabled: true}
  - {id: S04, kind: notations,     title: "Notations",                 template: auto_generated, enabled: true}
  - {id: S05, kind: model,         title: "Model I: ...",              template: default, enabled: true}
  - {id: S06, kind: model,         title: "Model II: ...",             template: default, enabled: true}
  - {id: S07, kind: sensitivity,   title: "Sensitivity Analysis",      template: default, enabled: true}
  - {id: S08, kind: strengths_weaknesses, title: "Strengths and Weaknesses", template: default, enabled: true}
  - {id: S09, kind: conclusion,    title: "Conclusion",                template: default, enabled: true}
  - {id: S10, kind: references,    title: "References",                template: auto_generated, enabled: true}
  - {id: S11, kind: appendix,      title: "Appendix",                  template: default, enabled: false}
  - {id: S12, kind: report_on_ai,  title: "Report on Use of AI",        template: auto_generated, enabled: false}

latex:
  documentclass: "[12pt]{article}"
  packages: [geometry, newtxtext, amsmath, amssymb, amsthm, newtxmath, graphicx, fancyhdr]
  engine: pdflatex             # pdflatex | xelatex
  bib: references.bib
  toc: true                    # universal in 2022-2025 (100%)
  page_limit: 25               # HARD — 72.1% of recent papers hit exactly this

build:
  last_built: null
  pdf_path: null
  page_count: null
  pages_remaining: null        # live budget number
```

**The Template/Content boundary, stated explicitly (this is the task's §4 answer):**

| **Paper TEMPLATE owns** (structure, mechanical) | **Paper CONTENT owns** (human, mathematical) |
|---|---|
| Section spine order (`Intro → Assump → Nota → Model → Sens → S&W → Conc → Ref`) | Which models exist and what they are |
| Summary sheet layout (`\Problem`, `\Team`, header table, page-1 form) | The core assumptions |
| LaTeX preamble, fonts, margins, `fancyhdr`, page numbering | Variable relationships and equations |
| Figure/table/equation **numbering** | Model innovation |
| Cross-reference **machinery** (`\ref`, `\label` wiring) | Interpretation of results |
| TOC generation | The final conclusion |
| Citation formatting and the References bibliography | Which literature to cite and why |
| Notations table **rendering** (from model-scoped symbols) | The symbols' meanings |
| "Report on Use of AI" **skeleton** | What AI was actually used for |
| PDF build pipeline | — |
| Page-budget **reporting** | The decision about what to cut |

**Sections that must be AUTO-GENERATED (never hand-written):**
- Notations (merged from `Model.symbols`, with the non-exhaustive disclaimer preserved)
- References (from `references.bib`)
- Table of Contents
- Report on Use of AI (from the AI-usage log)
- All figure/table/equation numbering

**Sections that must NEVER be templated beyond a heading:**
Model chapters, Assumptions, Strengths & Weaknesses, Conclusion, Restatement.

And explicitly: **do not create a Literature Review section** — it appears in **0 of 415** papers.

### 10.2 Citation Schema

References are **100% cited in text**, which makes citation integrity fully enforceable — unlike
figures (37%) and tables (33%).

```yaml
reference_id: REF-007
key: "hansen2016population"
type: article                 # article | book | inproceedings | thesis | techreport | misc | ai_tool
bibtex: |
  @article{hansen2016population, ...}
title: "Population ecology of the sea lamprey..."
authors: ["Hansen, Michael J.", ...]
year: 2016
venue: "Reviews in Fish Biology and Fisheries"
ai_generated: false           # [COM] COMAP requires AI tools cited in References

citation_id: CIT-021
key: "hansen2016population"
section_id: S05
context: "the sea lamprey is an invasive species in the Laurentian Great Lakes"
style: numeric                # numeric ([1]) | author_year — numeric dominates MCM
```

**AI-compliance fields.** COMAP's policy requires inline citations for AI tools, listing in
References, **and** a page-limit-exempt "Report on Use of AI" section:

```yaml
# paper/ai_usage.yaml
ai_used: true
entries:
  - tool: "DeepSeek Harness"
    version: "v4.1-flash"
    purpose: "development"     # development | template_generation | code_generation
                               # | testing | debugging | documentation | polishing
    phase: "pre_competition"   # pre_competition | competition
    queries:
      - query: "Generate a matplotlib template for a sensitivity line plot"
        output_ref: "artifacts/ai/0001.txt"
    in_report: false           # did any AI output land in the 25-page report?
```

`phase: competition` entries are the ones that require disclosure. The tool can **enforce** that if
any `phase: competition` entry exists, `ai_used` is true and the Report on Use of AI section is
enabled. This turns a compliance rule into a build-time check.

---

## 11. Audit Engine

### 11.1 Design principles

1. **The audit never replaces human review.** Its output is `READY FOR HUMAN REVIEW`, never
   `SUBMITTED`. This is stated in the task and is correct: the audit checks *mechanical consistency*,
   not *mathematical validity*.
2. **Every finding is machine-readable** with a `code`, `severity`, and `location`, so it can be
   fixed, suppressed with a reason, or waived.
3. **The audit runs against the object model, not the PDF** — except for the build checks, which must
   read the real compiled artifact.

### 11.2 Audit Schema

```yaml
audit_id: AUD-2025-01-26T09-00-00
paper_id: PAPER-001
started_at: "..."
duration_seconds: 14.2

findings:
  - finding_id: F-0031
    code: "NUMERIC_MISMATCH"
    category: numerical          # structure|figure|table|equation|citation
                                 # |crossref|numeric|build|compliance
    severity: error              # error | warning | info
    object_type: ResultAtom
    object_id: RES-0142
    location: "sections/00-summary.md:14"
    message: >
      Summary reports R = 73.3% but latest experiment EXP-026 produces
      R = 73.1% for the same condition.
    evidence:
      expected: 73.3
      actual: 73.1
      source: "EXP-026/RUN-026-003/RES-0142"
    fix_hint: "Re-render from RES-0142, or re-run EXP-026."
    suppressed: false
    suppression_reason: null

summary:
  errors: 3
  warnings: 11
  info: 4
  verdict: "NOT_READY"           # READY | READY_FOR_HUMAN_REVIEW | NOT_READY
```

### 11.3 The nine check families

#### (a) Structure
| Code | Check | Basis |
|---|---|---|
| `STRUCT_MISSING_MANDATORY` | References and Introduction present | 92.0% / 87.5% presence — the only two >80% |
| `STRUCT_ORDER_VIOLATION` | Spine order respected | 14 pairwise relations at **100%** |
| `STRUCT_SUMMARY_SHEET` | Summary sheet form present with Problem + Team number | 76.6% of papers; required by COMAP |
| `STRUCT_TOC_MISSING` | TOC present | **100%** of 2022–2025 papers |
| `STRUCT_PAGE_LIMIT` | Page count ≤ 25 | **72.1%** of recent papers are exactly 25 |
| `STRUCT_EMPTY_SECTION` | No section with a heading and no body | — |
| `STRUCT_PLACEHOLDER` | No `TODO`/`XXX`/`Lorem`/`TBD` left | — |

#### (b) Numerical consistency — **the core value**
| Code | Check |
|---|---|
| `NUMERIC_MISMATCH` | A `RenderedNumber` disagrees with its bound `ResultAtom` — **beyond formatting tolerance** |
| `NUMERIC_UNBOUND` | A number in prose that matches no `ResultAtom` and is not marked `literal` |
| `NUMERIC_STALE` | A `ResultAtom` changed after its last rendering |
| `NUMERIC_SUMMARY_DRIFT` | Summary/abstract value ≠ body value — **the 73% duplication case** |
| `NUMERIC_INTERNAL_INCONSISTENCY` | Two `ResultAtom`s from the same run disagree under a declared constraint |

**This is the answer to the task's §10 question** ("if EXP-026's RMSE changes from 0.0832 to
0.0791, how does the paper update?"): **it cannot drift, because the paper never stored the number.**
`{{RES-0142}}` in the LaTeX source renders `0.0791`. If a human hard-typed `0.0832`, the audit emits
`NUMERIC_UNBOUND`.

#### (c) Figure
| Code | Check |
|---|---|
| `FIG_MISSING_FILE` | Referenced figure file does not exist |
| `FIG_ORPHAN` | Figure generated but never referenced — **a real defect: 63% of figures are unreferenced** |
| `FIG_NOT_IN_SECTION` | Figure referenced in a section that doesn't own its experiment |
| `FIG_STALE` | A bound `ResultAtom` changed since generation |
| `FIG_RASTER_LOWRES` | Raster figure below resolution threshold — guards the 74% <500px problem |
| `FIG_MISSING_CAPTION` | No caption |
| `FIG_BROKEN_REF` | `\ref{fig:x}` with no matching `\label` |

#### (d) Table
Same family: `TAB_MISSING`, `TAB_ORPHAN`, `TAB_CELL_MISMATCH`, `TAB_STALE`, `TAB_BROKEN_REF`.

#### (e) Equation
| Code | Check |
|---|---|
| `EQ_UNNUMBERED` | Equation referenced but unnumbered |
| `EQ_NUMBER_GAP` | Numbering sequence has gaps/duplicates |
| `EQ_SYMBOL_UNDEFINED` | Symbol used in an equation but absent from that model's `symbols` |
| `EQ_BROKEN_REF` | `\eqref` with no target |

#### (f) Citation
| Code | Check | Basis |
|---|---|---|
| `CITE_UNDEFINED` | `\cite{x}` with no bib entry | — |
| `CITE_UNCITED_REFERENCE` | Bib entry never cited | — |
| `CITE_AI_UNDISCLOSED` | `ai_used: true` but no AI entry in References | COMAP requires it |
| `CITE_AI_NO_SECTION` | AI used in competition but "Report on Use of AI" disabled | COMAP requires the section |
| `CITE_AI_UNVERIFIED` | AI-assisted claim not verified | Policy: "Verify the accuracy ... and correct any errors" |

#### (g) Cross-reference
| Code | Check | Basis |
|---|---|---|
| `XREF_BROKEN` | Any `\ref` with no target | — |
| `XREF_ORPHAN_LABEL` | Label never referenced | — |
| `XREF_FIG_UNCITED` | Figure never cited in text | 37.3% cited — **warning, not error** |
| `XREF_TAB_UNCITED` | Table never cited in text | 32.6% cited — **warning** |

**Severity note:** because only 37% of *Outstanding* figures are explicitly cross-referenced, an
uncited figure must be a **warning**, not an error. Making it an error would fail most winning
papers. This is a deliberate calibration from evidence.

#### (h) Build
| Code | Check |
|---|---|
| `BUILD_LATEX_ERROR` | LaTeX exits non-zero |
| `BUILD_NO_PDF` | No PDF produced |
| `BUILD_MISSING_GRAPHIC` | LaTeX reports a missing image |
| `BUILD_OVERFULL` | Overfull hbox/vbox above threshold |
| `BUILD_UNDEFINED_REFS` | "LaTeX Warning: There were undefined references" |
| `BUILD_RERUN_NEEDED` | "Rerun to get cross-references right" |
| `BUILD_FONT_WARNING` | Missing font substitutions |

#### (i) Compliance
| Code | Check |
|---|---|
| `COMP_ANONYMITY` | No school/advisor/team-member name anywhere (COMAP DQ risk) |
| `COMP_TEAM_NUMBER` | Team control number present and non-placeholder |
| `COMP_PROBLEM_LETTER` | Problem letter present and matches the locked problem |
| `COMP_PAGE_LIMIT` | ≤25 pages **excluding** the Report on Use of AI |
| `COMP_AI_REPORT` | If AI used, the exempt report section exists |

### 11.4 Required output format

```
MCM FINAL AUDIT — PAPER-001
════════════════════════════════════════════════════════
Structure ............ ✓  11/11 checks passed
Figures .............. ✓  14 figures, 1 warning (FIG-009 unreferenced)
Tables ............... ✓   6 tables, all bound to ResultAtoms
Equations ............ ✓  23 equations, numbering continuous
Citations ............ ✓  18 refs, 0 undefined, 0 uncited
Numerical consistency  ✗  2 errors
Cross references ..... ✓  0 broken
Build ................ ✓  PDF 24 pages (1 page under limit)
Compliance ........... ✓  anonymous, team number present

✗ ERRORS (2)
  NUMERIC_MISMATCH   sections/00-summary.md:14
    Summary says R = 73.3%  ·  RES-0142 = 73.1%   [EXP-026]
  NUMERIC_UNBOUND    sections/05-model-ii.md:88
    "stability index S = 3.7e-4" is not bound to any ResultAtom

⚠ WARNINGS (11)
  FIG_ORPHAN         FIG-009 never referenced in text
  XREF_TAB_UNCITED   TAB-004 never referenced in text
  ...

────────────────────────────────────────────────────────
VERDICT: NOT READY — 2 errors must be resolved
This audit checks MECHANICAL CONSISTENCY only.
It does not evaluate mathematical validity, model quality,
or persuasiveness. Human review is required.
════════════════════════════════════════════════════════
```

---

## 12. Template Registry

Templates are the **third layer** (task §13) — reusable knowledge and code, distinct from Core
(execution) and Interface (invocation).

### 12.1 Registry structure

```
templates/
├── registry.yaml
├── models/
│   ├── ode_system/          # ODE/difference-equation dynamical model
│   ├── optimization_lp/     # LP/MILP with objective + constraints
│   ├── evaluation_ahp/      # AHP/entropy-weight/TOPSIS composite index
│   ├── prediction_timeseries/   # ARIMA/Prophet/GRU/LSTM
│   ├── prediction_regression/   # linear/ridge/lasso/XGBoost
│   ├── classification/      # K-means, RF, SVM
│   ├── evaluation_model/    # assessment-index model
│   └── simulation_abm/      # agent-based / Monte Carlo simulation
├── experiments/
│   ├── sensitivity_oat/
│   ├── sensitivity_grid/
│   ├── model_comparison/
│   ├── robustness_noise/
│   ├── monte_carlo/
│   ├── cross_validation/
│   ├── train_test/
│   └── scenario/
├── figures/                 # §12.3
├── tables/
│   ├── parameter_settings/
│   ├── notation_table/
│   ├── metric_comparison/
│   ├── sensitivity_result/
│   └── robustness_mean_std/
└── paper/
    ├── comap_latex/         # derived from the official 2021 template
    └── sections/            # per-section skeletons
```

### 12.2 Template schema

```yaml
# templates/experiments/sensitivity_oat/template.yaml
template_id: "exp.sensitivity_oat"
kind: experiment
version: "1.0.0"
description: "One-at-a-time parameter sweep with a declared invariant"

requires:                     # what the caller must supply
  model: true
  dataset: true
  varied: ["parameter"]
  held_fixed: true

provides:
  result_atoms:
    - {name: "{{param}}_series", type: array, unit: "{{unit}}"}
    - {name: "{{metric}}_at_default", type: scalar}
  figures: ["fig.sensitivity_line"]
  tables: ["tab.sensitivity_result"]

entrypoint: "run.py"
dependencies: ["numpy", "matplotlib"]
```

### 12.3 Figure Template Registry

Derived from the observed figure types and their frequencies:

```yaml
# templates/figures/registry.yaml
- id: "fig.sensitivity_line"
  type: line
  purpose: "Show a metric's response as one parameter varies"
  observed_in: "~15% of papers (sensitivity/sweep captions)"
  inputs:
    - {name: x, role: independent_variable, type: array}
    - {name: y, role: metric, type: array}
    - {name: series, role: grouping, type: array, optional: true}
    - {name: baseline, role: reference_value, type: scalar, optional: true}
  outputs: {format: pdf, width_in: 6.0}
  caption_template: "Effect of varying {x_label} on {y_label}."
  latex: "\\includegraphics[width=0.8\\linewidth]{{{file}}}"

- id: "fig.heatmap_matrix"
  type: heatmap
  purpose: "Two-parameter response surface, or a correlation matrix"
  observed_in: "~1.9% correlation + ~5% grid sweeps"
  inputs: [{name: matrix, type: matrix}, {name: labels, type: array}]
  caption_template: "{title} heat map."

- id: "fig.convergence"
  type: line
  purpose: "Show objective/error against iteration"
  inputs: [{name: iterations, type: array}, {name: objective, type: array}]

- id: "fig.pred_vs_actual"
  type: scatter
  purpose: "Prediction fit with a y=x reference line"
  inputs: [{name: actual, type: array}, {name: predicted, type: array}]

- id: "fig.residual"
  type: scatter
  purpose: "Residual diagnostics"
  inputs: [{name: predicted, type: array}, {name: residual, type: array}]

- id: "fig.bar_comparison"
  type: bar
  purpose: "Compare a metric across models/scenarios"
  inputs: [{name: categories, type: array}, {name: values, type: array},
           {name: errors, type: array, optional: true}]

- id: "fig.boxplot_grouped"
  type: boxplot
  purpose: "Compare distributions with the median-difference annotation"
  inputs: [{name: groups, type: array}, {name: values, type: array}]

- id: "fig.flowchart"
  type: diagram
  purpose: "Algorithm / methodology flow"
  inputs: [{name: nodes, type: array}, {name: edges, type: array}]
  backend: drawio

- id: "fig.model_structure"
  type: diagram
  purpose: "Mindmap / framework of models and data flow"
  inputs: [{name: models, type: array}, {name: flows, type: array}]
  backend: drawio

- id: "fig.network"
  type: graph
  purpose: "Network / node-link structure"
  inputs: [{name: nodes, type: array}, {name: edges, type: array}]

- id: "fig.map_choropleth"
  type: map
  purpose: "Geographic distribution"
  inputs: [{name: regions, type: array}, {name: values, type: array}]

- id: "fig.scatter_matrix"
  type: scatter
  purpose: "Pairwise feature relationships"
  inputs: [{name: frame, type: dataframe}]
```

**Coverage rationale.** These templates cover the types observed across 4,810 figure captions and
content inspection. We deliberately do **not** ship: 3D surface plots (1.1% — matplotlib can do it,
no template needed), Sankey/alluvial (rare), or animation (impossible in a static PDF). Templates
are for **repeated, parameterized, paper-ready** figures only.

---

## 13. Paper Compiler

### 13.1 Pipeline

```
Object Model                       Compiler stages                     Output
─────────────                      ───────────────                     ──────
Model.symbols        ──┐
Assumption[]         ──┼─→ [1] Resolve  ────────────→ paper.tex context
Equation[]           ──┘                                (macros + \label keys)
                                                        │
ResultAtom[]         ──┐                                ▼
Figure[], Table[]    ──┼─→ [2] Generate ──────────→ figures/*.pdf, tables/*.tex
Claim[]              ──┘                                │
                                                        ▼
PaperSection.body    ──┐
Citation[], Reference┴─→ [3] Render ────────────→ main.tex + sections/*.tex
                                                        │
                                                        ▼
                        [4] Compile ─────────────→ main.pdf (latexmk/pdflatex)
                                                        │
                                                        ▼
                        [5] Measure ─────────────→ page_count, budget
                                                        │
                                                        ▼
                        [6] Verify  ─────────────→ Audit Engine (§11)
```

### 13.2 The Single Source of Truth mechanism

**The core mechanism: a number in the paper is a *reference*, never a literal.**

LaTeX-side, the compiler emits macros:

```latex
% generated/numbers.tex  — regenerated on every build
\newcommand{\numRESZeroOneFourTwo}{0.0791}
\newcommand{\numRESZeroOneFourTwoPct}{7.91\%}
```

Prose-side, the author writes:

```markdown
The proposed model achieves an RMSE of \numRESZeroOneFourTwo{}.
```

**Never:**

```markdown
The proposed model achieves an RMSE of 0.0832.   % ← NUMERIC_UNBOUND
```

When the author writes a bare number, the compiler **detects it** (regex over numeric tokens) and the
auditor flags it `NUMERIC_UNBOUND` unless it is explicitly marked as a literal via
`\lit{0.0832}` (for things like "25 pages", "5-fold", "Problem A" — numbers that are not results).

**Formatting and unit normalization.** Because the corpus shows `83.77 %` and `0.8377` are the same
number, the compiler supports declared alternate renderings:

```yaml
- atom: RES-0204
  renderings:
    - {name: fraction, format: "%.4f", value: 0.8377}
    - {name: percent,  format: "%.2f\\%%", value: 83.77}
```

The auditor compares **normalized** values, so a percent/fraction difference is not a false positive.

### 13.3 Other synchronization duties

| Sync task | Mechanism |
|---|---|
| **Figure numbering** | `\label{fig:key}` / `\ref` — LaTeX-native, never hand-numbered |
| **Table numbering** | Same |
| **Equation numbering** | Paper-global `equation` counter; model ownership stored, not inferred |
| **Cross references** | All refs via `\ref`/`\eqref`; `XREF_BROKEN` if unresolvable |
| **Model name sync** | Model name lives in `model.yaml`; emitted as `\newcommand{\modelIII}{...}`. The Summary, TOC, and body all use `\modelIII{}` |
| **Parameter sync** | Parameter table cells bound to `Parameter.value` |
| **Citation** | `references.bib` + `\cite{}` |
| **Notations table** | Auto-generated from model-scoped symbols, with the corpus-standard non-exhaustive note |

### 13.4 Page budget as a live number

```bash
$ mcm paper build
[1/6] Resolving objects ......... 3 models, 47 symbols, 23 equations
[2/6] Generating artifacts ...... 14 figures, 6 tables
[3/6] Rendering sections ........ 11 sections
[4/6] Compiling ................. pdflatex ×3 (latexmk)
[5/6] Measuring ................. 24 pages  (budget 25, 1 remaining)
[6/6] Verifying ................. audit: 7 findings (0 errors, 7 warnings)

PDF: build/main.pdf — 24 pages
```

`26 pages → STRUCT_PAGE_LIMIT (error)`.

---

## 14. Vue3 Control Panel

### 14.1 Verdict on the proposed navigation

The task's proposed `Dashboard | Model | Experiment | Data | Visualization | Paper | Audit |
Settings` is **wrong in one specific, important way: it is a flat list of nouns, but the actual
workflow is a state machine with a one-time decision and a lock.**

After the problem is locked, A/B/C/D/E/F must **not** occupy the main interface. The corpus confirms
problem choice is a start-of-contest event; nothing downstream references the other letters.

### 14.2 Redesigned navigation — phase-driven

```typescript
type Phase =
  | 'problem_selection'   // A–F all visible; the ONLY time they are
  | 'problem_locked'      // analysis, before commitment
  | 'build'               // the main competition phase
  | 'finalize'            // page budget + audit + export
```

**Sidebar is phase-dependent.** This is the central UI decision.

```
PHASE: problem_selection
  Problems                 (A–F cards, statements, data, translation)
  Settings

  → human picks one
  → LOCK (explicit, confirmable, reversible only with a deliberate unlock)

PHASE: build
  Overview                 (workflow state: what's done, what's blocking)
  ─────────────────────
  Data                     (datasets, stages, EDA)
  Models                   (M01, M02, M03 — each a full mathematical identity)
  Experiments              (EXP-001…, with status/provenance)
  Results                  (ResultAtoms, figures, tables)
  Paper                    (sections, summary, compile, page budget)
  Audit                    (findings)
  ─────────────────────
  Problems                 (collapsed; the locked one only)
  Settings

PHASE: finalize
  Paper                    (focus)
  Audit                    (focus)
  Build & Export
```

**Rationale:** "Visualization" is **not** a top-level destination. Figures are *outputs of
experiments*. A separate Visualization tab would encourage the exact anti-pattern the corpus
exposes — figures created outside the experiment pipeline and manually inserted. Instead, figures
live under **Results**, bound to ResultAtoms, with a "regenerate" action.

### 14.3 Key screens

**Overview** — the state machine, visible at a glance:

```
MCM 2025 · Problem A · Team 2400996
──────────────────────────────────────────────────────
✓ Problem locked            A — Testing Time
✓ Data                      2 datasets, 3 versions
✓ Models                    3 defined (M01, M02, M03)
◐ Experiments               7 done · 1 running · 1 failed
◐ Figures/Tables            14 figures · 6 tables · 2 stale
◐ Paper                     11 sections · 24/25 pages
○ Audit                     last run 12 min ago — 2 errors
──────────────────────────────────────────────────────
BLOCKERS
  ⚠ FIG-009 bound to RES-0142 which changed — regenerate
  ✗ NUMERIC_MISMATCH in Summary: R=73.3% vs experiment 73.1%
```

**Models** — each model as a mathematical identity, not a file:

```
M03  Adaptive Periodic Grid Model (APGM)
     kind: prediction · order: 3/3 · task: T2
     ────────────────────────────────────────────
     Baseline:  Forex Grid strategy [7]  (extend)
     Sub-models: predictor → decision → backtest
     Symbols:   14 model-scoped  (2 colliding with M01 ⚠)
     Equations: 9  (5 global numbers: 7–15)
     Assumptions: 4 model-scoped
     Parameters: 8 · 3 literature, 2 fitted, 3 assumed
     Experiments: EXP-021 · EXP-022 · EXP-026 · EXP-027
```

**Experiments** — the DAG, with status and provenance:

```
EXP-026  Transaction cost sensitivity        [sensitivity_oat]
         M03 × DS-001 · 6 runs · completed
         varied: cost_gold{0.01,0.02} × cost_btc{0.01,0.02,0.03}
         held fixed: grid logic, price series, 5y window
         ──→ TAB-008, FIG-011 ──→ §7.1
EXP-027  Regime robustness                   [robustness_noise]
         M03 × DS-001 · 30 runs · FAILED
         reason: "non-convergent for σ > 0.05"
```

**The "Failed" state is a first-class UI affordance** — 83% of winning papers discuss weaknesses and
the best document rejected methods. Hiding failures would actively degrade paper quality.

**Paper** — with the live page budget:

```
Paper  ·  24 / 25 pages  ·  1 remaining
──────────────────────────────────────────────────────
✓ Summary sheet          ✓ Introduction
✓ Assumptions            ✓ Notations (auto)
✓ Model I                ✓ Model II
✓ Model III              ⚠ Sensitivity (FIG-011 stale)
✓ Strengths & Weaknesses ✓ Conclusion
✓ References (18)        ○ Appendix (off)
○ Report on Use of AI (off)  ⚠ AI used in competition — COMAP requires it
```

### 14.4 Interface layer

```
Vue3 (frontend/)  ──HTTP/JSON──→  FastAPI (backend/)  ──Python──→  Core (core/)
      │                                   │                            │
      └── never touches files ────────────┴── thin wrapper ───────────┴── owns all logic
```

**Rule:** the Vue layer contains **no business logic**. It renders state and issues commands. All
validation, propagation, and computation live in Core. This keeps the CLI a true equal of the GUI —
important because during a competition, the CLI is often faster.

---

## 15. CLI

The CLI is a **first-class interface**, not a debug tool. During a 96-hour contest, a competent
teammate types faster than they click.

```bash
# --- problem phase ---
mcm problems list --year 2025
mcm problems show A
mcm problems analyze A              # AI-assisted, pre-lock only
mcm problems lock A --team 2400996  # explicit, confirmed

# --- data ---
# 注意：这一段是当初的设计草案，`mcm data add` 从未实现。
# 实际入口是面板的「数据」页（POST /api/datasets/import），
# 或在脚本里调 store.save_dataset()。
mcm data add ./Problem_C_Data.zip --name "wordle" --stage raw   # 未实现
mcm data clean DS-001 --recipe recipes/wordle.yaml              # 未实现
mcm data eda DS-001                 # 未实现

# --- models ---
mcm model new M03 --from-template ode_system
mcm model validate M03              # schema, symbol collisions, undefined symbols
mcm model list
mcm model notation                  # render the merged Notations table

# --- experiments ---
mcm exp new EXP-026 --kind sensitivity_oat --model M03 --data DS-001
mcm exp run EXP-026                 # executes, records Run + ResultAtoms
mcm exp run EXP-026 --dry-run       # show the sweep without executing
mcm exp status                      # DAG view with statuses
mcm exp compare EXP-024 EXP-025     # emits a comparison table

# --- results / figures ---
mcm result list --experiment EXP-026
mcm figure generate FIG-011 --template fig.sensitivity_line
mcm figure regenerate --stale       # regenerate everything stale
mcm table generate TAB-008 --template tab.metric_comparison

# --- paper ---
mcm paper init --template comap_latex
mcm paper section add model --title "Model III: APGM"
mcm paper notation sync             # rebuild Notations from models
mcm paper build                     # compile + measure + audit
mcm paper budget                    # page budget report only

# --- audit ---
mcm audit                           # full audit
mcm audit --category numerical      # one family
mcm audit --severity error
mcm audit --fix-hints

# --- export ---
mcm export pdf --out submission/2400996.pdf
mcm export bundle                   # reproducible archive: code + data refs + paper
```

**`--dry-run` on `exp run`** matters: it lets a human see the sweep before burning 40 minutes.

---

## 16. FastAPI

Thin. No business logic. Every endpoint maps to a Core function.

```
# --- problems ---
GET    /api/problems?year=2025
GET    /api/problems/{id}
POST   /api/problems/{id}/analyze
POST   /api/project/lock            {problem_id, team_number}

# --- project state ---
GET    /api/state                   # the Overview payload (phase, counts, blockers)

# --- data ---
GET    /api/datasets
POST   /api/datasets                # multipart ingest
GET    /api/datasets/{id}           # incl. schema, stats, lineage, transformations
POST   /api/datasets/{id}/clean     {recipe}
GET    /api/datasets/{id}/eda

# --- models ---
GET    /api/models
POST   /api/models
GET    /api/math                    # 符号表 · 公式 · 假设
PUT    /api/math/symbols/{id}
DELETE /api/math/symbols/{id}
PUT    /api/math/equations/{id}
GET    /api/params                  # 参数及其来源
PUT    /api/params/{name}           # 按名字定位，不是内部 id
DELETE /api/params/{name}
GET    /api/notations               # merged paper-level notation view

# --- experiments ---
GET    /api/experiments             # incl. status, parents, children
POST   /api/experiments
GET    /api/experiments/{id}
POST   /api/experiments/{id}/run    # → 202 {run_id}; progress via WS
GET    /api/experiments/{id}/runs
GET    /api/experiments/{id}/results

# --- results / artifacts ---
GET    /api/results/{atom_id}
GET    /api/figures
POST   /api/figures/{id}/regenerate
GET    /api/figures/stale
GET    /api/tables

# --- paper ---
GET    /api/paper
PUT    /api/paper/sections/{id}
POST   /api/paper/build             # sync build
GET    /api/paper/budget
POST   /api/paper/ai-usage

# --- audit ---
POST   /api/audit                   # → AuditReport
GET    /api/audit/last
POST   /api/audit/findings/{id}/suppress  {reason}

# --- export ---
GET    /api/export/pdf
GET    /api/export/bundle

# --- realtime ---
WS     /api/ws                      # run progress, build progress, state changes
```

**Design constraints:**
- **No endpoint performs long work synchronously** except `paper/build` (bounded, ~seconds).
  Experiment runs return `202` + a `run_id` and stream progress over the WebSocket.
- **No endpoint mutates a `ResultAtom`.** Results are written only by the run pipeline. This is what
  makes the Single Source of Truth trustworthy.
- **Every mutating endpoint returns the affected audit findings**, so the UI can show consequences
  immediately.

---

## 17. Competition Mode vs Development Mode

The task's core positioning — *"AI-assisted development before the contest, local offline operation
during it"* — maps onto a mode switch that is **enforced, not merely documented**.

```yaml
# .mcmtools/config.yaml
mode: competition        # development | competition
```

| Capability | Development | Competition |
|---|---|---|
| Network access (Core) | allowed | **blocked** |
| AI-assisted problem analysis | yes | **no** |
| AI template/code generation | yes | **no** |
| AI log recording | optional | **required for any AI use** |
| Local templates/registry | yes | yes |
| Core execution | yes | yes |
| Paper compiler | yes | yes |
| Audit | yes | yes |
| Export/bundle | yes | yes |

**Implementation of the boundary.** In `competition` mode:
1. `core/` performs **no outbound network calls**. A single guard module wraps every HTTP client.
2. AI-backed skills are **disabled at the tool level**, not just discouraged.
3. Any AI usage that *does* occur (e.g. a teammate uses an external tool) must be **logged** via
   `mcm paper ai-usage add`, which feeds the mandatory "Report on Use of AI" section.
4. The audit **fails** if `ai_used: true` and the report section is missing (COMAP requirement).

**Why this is a real feature and not theatre.** COMAP's policy is explicit:

> "Teams are required to: 1. Clearly indicate the use of LLMs or other AI tools ... Please use inline
> citations and the reference section. Also append the **Report on Use of AI** ... after your
> 25-page solution. 2. Verify the accuracy, validity, and appropriateness of the content ... 3.
> Provide citation and references ... 4. Be conscious of the potential for plagiarism."

and:

> "Solving the problems does not require the use of AI tools, although their responsible use is
> permitted."

So the tool's job is to make **compliance easy and violation visible** — not to pretend AI doesn't
exist.

**The `development` mode is where AI genuinely belongs**, per the task brief:

```
PRE-CONTEST (development mode, AI-assisted)
  ├── Build model templates from the literature
  ├── Build experiment templates
  ├── Build figure/table templates
  ├── Build the COMAP LaTeX template
  ├── Generate and test the Core
  ├── Write tests
  ├── Write documentation
  └── Dry-run a full paper end-to-end on a PAST problem
                                          ↑ this is the key validation
DURING CONTEST (competition mode, no AI)
  └── Human makes every mathematical decision;
      MCMtools executes, records, checks, renders.
```

---

## 18. File and Directory Structure

```
MCMtools/
├── docs/
│   ├── mcmtools-architecture.md        ← this document
│   ├── findings-sections.md            (corpus evidence)
│   ├── findings-models.md
│   ├── findings-experiments.md
│   └── findings-figures.md
├── core/                               # LAYER 1 — pure Python, no HTTP, no UI
│   ├── pyproject.toml
│   ├── mcmcore/
│   │   ├── __init__.py
│   │   ├── schemas/                    # Pydantic models — the object model (§5)
│   │   │   ├── problem.py  task.py
│   │   │   ├── model.py    symbol.py  parameter.py  assumption.py  equation.py
│   │   │   ├── dataset.py
│   │   │   ├── experiment.py  run.py  result.py
│   │   │   ├── figure.py   table.py
│   │   │   ├── paper.py    claim.py   citation.py
│   │   │   └── audit.py
│   │   ├── store/                      # YAML/JSON persistence, one loader per object
│   │   ├── data/                       # Data Engine (§8)
│   │   │   ├── ingest.py  clean.py  transform.py  features.py  eda.py
│   │   ├── model/                      # model validation, symbol merge, collision detect
│   │   ├── experiment/
│   │   │   ├── sweep.py  runner.py  results.py  dag.py
│   │   ├── viz/                        # figure generation; renders Figure Templates
│   │   ├── tables/                     # table generation
│   │   ├── paper/
│   │   │   ├── resolver.py             # objects → LaTeX context
│   │   │   ├── numbers.py              # ResultAtom → \newcommand macros
│   │   │   ├── renderer.py             # sections → .tex
│   │   │   ├── compiler.py             # latexmk invocation
│   │   │   └── budget.py               # page counting
│   │   ├── audit/
│   │   │   ├── structure.py  numerical.py  figure.py  table.py
│   │   │   ├── equation.py   citation.py   crossref.py
│   │   │   ├── build.py      compliance.py
│   │   │   └── engine.py               # runs all families, merges findings
│   │   ├── templates/                  # registry loader + instantiation
│   │   └── net_guard.py                # competition-mode network block
│   └── tests/
├── templates/                          # LAYER 3 — reusable knowledge + code (§12)
│   ├── registry.yaml
│   ├── figures/  experiments/  tables/  paper/
├── interface/
│   ├── cli/                            # LAYER 2a — Typer or argparse
│   │   └── mcmcli/
│   └── api/                            # LAYER 2b — FastAPI
│       └── mcmapi/
├── frontend/                           # LAYER 2c — Vue3 + Vite
│   ├── package.json
│   └── src/
│       ├── views/  components/  stores/  api/
├── projects/                           # ONE DIRECTORY PER COMPETITION ATTEMPT
│   └── mcm2025-A/
│       ├── project.yaml                # phase, locked problem, team number, mode
│       ├── problems/                   # candidate problems + analysis
│       ├── data/
│       │   ├── DS-001/
│       │   │   ├── dataset.yaml
│       │   │   └── raw/ staged/ cleaned/ processed/ features/
│       ├── math/
│       │   └── math.yaml               # 符号表 · 公式 · 假设（项目级，跨全文唯一）
│       ├── params/
│       │   └── parameters.yaml         # 参数及其来源（literature/dataset/fitted/assumed）
│       ├── experiments/
│       │   └── EXP-026/{experiment.yaml, runs/, code/}
│       ├── results/
│       │   └── atoms.yaml              # ALL ResultAtoms for the project
│       ├── figures/                    # FIG-*.pdf + FIG-*.yaml
│       ├── tables/                     # TAB-*.tex + TAB-*.yaml
│       ├── paper/
│       │   ├── paper.yaml
│       │   ├── references.bib
│       │   ├── ai_usage.yaml
│       │   ├── sections/*.md
│       │   ├── generated/              # numbers.tex, notations.tex, toc
│       │   └── build/                  # main.tex, main.pdf, *.log
│       ├── audit/
│       └── export/
└── .mcmtools/config.yaml               # mode, paths
```

**Why one directory per attempt:** the corpus shows each contest is a self-contained artifact with
its own data, models, and paper. A shared global state would make past attempts unreproducible —
which is exactly what the tool exists to prevent.

---

## 18.5 运行归档：code/ · experiments/ · runs/

### 三个顶层目录的分工

```
<项目>/
  code/           建模代码（人写）
  experiments/    实验协议：跑什么、扫哪个参数（人写）
  runs/           每次执行的归档（机器写，不要手改）
  results/        ResultAtom 与 Run 的类型化记录
  build/          编译产物（可再生，不要手改）
```

分家的理由：**改代码不该动实验配置，改配置也不该动代码。**
两者混在一层目录里时，diff 看不出到底改了什么，评审也说不清
"这个数字是哪版代码算的"。

### 一次运行 = 一个文件夹

```
runs/EXP-001/RUN-001-004/
    run.yaml      状态、耗时、原子数、产出清单
    params.json   本次实际用的参数（可直接重跑）
    meta.json     条件、trial 序号、脚本路径与 SHA-256
    stdout.txt / stderr.txt
    artifacts/    脚本产出的文件（复制保存，原文件不动）
```

用复制而非移动：脚本可能还要重读自己的输出，而且用户习惯在原位置找文件。
复制一份是为了让历史运行**自包含** —— 半年后只看这个文件夹就知道产出了什么。

### 运行号只增不复用

运行号在实验内**全局递增**，与 trial 序号无关：

```
第一次跑：RUN-001-001, RUN-001-002, RUN-001-003
再跑一次：RUN-001-004, RUN-001-005, RUN-001-006
```

早期实现用 trial 序号拼编号（`f"RUN-{exp}-{i:03d}"`），重跑实验会拿到同样的
编号，新一轮产物直接倒进旧文件夹。实测连跑三轮后，每个文件夹堆了 3 份产物、
含不同参数的文件混在一起，而 `run.yaml` 只记了 1 份 —— 归档就此失去追溯能力。

**编号复用是归档机制唯一不能犯的错。**

排序靠编号而非时间戳：时钟被调整也不会打乱执行顺序。

### 代码指纹与过期检测

`meta.json` 记录脚本路径与内容哈希。`RunStore.staleness()` 拿**最近一次**运行的
哈希与当前文件比对，不一致就报「结果来自旧代码」：

```
code/pcql.py 在 RUN-001-003 之后被改过，这次运行的结果来自旧代码。请重跑该实验。
```

只比对最近一次：历史运行本来就是旧的，全报出来反而淹没真正的问题。

这条检查补的是一个很常见的失误 —— 跑完实验、拿到结果、又改了脚本。
此时 `runs/` 里的结果来自旧代码，但磁盘上没有任何迹象。

### API 与界面

| 入口 | 说明 |
|---|---|
| `GET /api/runs[?experiment_id=]` | 归档清单，按运行号升序 |
| `GET /api/runs/summary` | 每实验次数 + `stale_runs` |
| 面板「运行记录」页 | 每次运行一行：参数、原子数、产出文件、代码指纹 |
| `mcm exp runs [EXP-ID] [--json]` | 终端查看 |

## 18.6 为什么删掉了「模型层」

早期设计里有一个 `Model` 对象，一篇论文有 2–4 个，每个下面挂着符号、
参数、假设、公式。实现之后发现它是个**壳**，于是拆掉了。

### 壳里装的是什么

| 字段 | 性质 |
|---|---|
| `label` / `label_style`（roman/arabic/mixed） | 记账：论文怎么称呼模型 |
| `title_form`（plain/numbered-hyphenated/prefixed-acronym） | 记账 |
| `relation_to_siblings` / `role_in_parent` / `parent_model_id` | 记账：模型之间的谱系 |
| `baseline` / `is_baseline_for` / `uses_method_of` | 记账：谁改进了谁 |
| `coupling` / `shared_symbols_with` | 记账 |
| `kind`（simulation/prediction/optimization…） | 记账 |

这些字段**不产出任何代码、任何数字、任何检查**。它们描述的是
"论文怎么谈论模型"，而不是"模型是什么"。填了它们不会让论文更好，
漏填了也不会被审计拦住。

### 壳里真正有价值的三样东西

| 内容 | 谁在用 |
|---|---|
| `symbols` 符号表 | 审计查"同一符号两种含义"（读者会被误导）；符号表自动生成 |
| `equations` 公式 | 审计查"公式编号重复"（编号是全文计数器，必须唯一） |
| `assumptions` 假设 | 论文硬性要求逐条给理由 |

还有 `objective` / `constraints`（优化类内容缺约束是常见硬伤）
和 `notation_table`（非穷尽声明近乎通用）。

### 怎么拆的

这三样东西**本来就不该从属于"某个模型"**：一篇论文只有一张符号表、
一套贯穿全文的编号。所以提到项目级，新建 `math/` 区，与 `params/` 平级：

```
math/math.yaml      符号、公式、假设、目标函数、符号表设置
params/parameters.yaml   参数及其来源
```

同步的取舍：

- `SYMBOL_REDEFINED_ACROSS_MODELS`（跨模型，警告）→ `SYMBOL_REDEFINED`
  （项目级，**错误**）。一篇论文一个符号表，两种含义就是硬伤，不该只是警告。
- 删掉了 `DANGLING_PARENT_MODEL`、`DANGLING_USES_METHOD_OF`、
  `OPTIMIZATION_NO_OBJECTIVE`、`SECTION_MODEL_UNRESOLVED` —— 它们检查的
  都是记账字段，字段没了检查也失去意义。
- 保留并强化了 `PARAMETER_NO_PROVENANCE`。**这是当初保留 `Parameter`
  的理由**：105/237 篇现代论文会标注参数来源，缺来源是实打实的缺陷。
- 模型名宏（`\modelI` 这类，让改名一处改、处处生效）改为**按
  `kind=model` 的章节标题**生成 —— 论文里真正的"模型一/模型二"
  就是章节标题，这反而更准。

---

## 19. Module Dependencies

Strictly layered. **Arrows point one way; there are no cycles.**

```
                    ┌──────────────┐
                    │   schemas    │  (leaf — depends on nothing but pydantic)
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┬─────────────┐
              ▼            ▼            ▼             ▼
          ┌───────┐   ┌───────┐   ┌──────────┐  ┌─────────┐
          │ store │   │ data  │   │  model   │  │templates│
          └───┬───┘   └───┬───┘   └────┬─────┘  └────┬────┘
              │           │            │             │
              └───────────┴────────────┴─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  experiment  │  (depends on model + data + store)
                    └──────┬───────┘
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
             ┌────────┐       ┌─────────┐
             │  viz   │       │ tables  │
             └───┬────┘       └────┬────┘
                 └────────┬────────┘
                          ▼
                    ┌──────────┐
                    │  paper   │  (resolver → numbers → renderer → compiler → budget)
                    └────┬─────┘
                         ▼
                    ┌──────────┐
                    │  audit   │  (reads EVERYTHING; writes only findings)
                    └────┬─────┘
                         ▼
        ┌────────────────┼─────────────────┐
        ▼                ▼                 ▼
   ┌────────┐      ┌──────────┐      ┌──────────┐
   │  cli   │      │   api    │      │ frontend │
   └────────┘      └──────────┘      └──────────┘
```

**Enforced rules:**
1. `schemas` depends on nothing internal. It is the contract.
2. `audit` **reads** every module but is **written by** none. No module imports `audit`.
3. `paper` never imports `experiment`; it reads persisted `ResultAtom`s via `store`. This keeps the
   compiler deterministic and re-runnable without re-executing experiments.
4. `experiment` writes `ResultAtom`s; **nothing else may**. Single-writer is what makes the Single
   Source of Truth real.
5. `cli`, `api`, and `frontend` are **siblings**. Neither is privileged. The frontend calls the API;
   the CLI calls Core directly.

---

## 20. MVP Development Order

See §21 for the full phase list. The ordering principle:

> **Build the thing that makes the paper not lie, before building anything that makes the paper
> pretty.**

Rationale: the audit + numeric binding is the differentiator that no other tool provides. A beautiful
UI over an unreliable number pipeline is a worse product than a CLI over a trustworthy one.

**The critical path is:** `schemas → store → experiment → results → paper(numbers) → audit`。
Figures, EDA, FastAPI, and Vue3 all attach to an already-working spine.

---

## 21. Recommended Implementation Order

### Phase 1 — Core schemas  ← *start here*
**Deliverable:** `core/mcmcore/schemas/` with Pydantic models for every object in §5, plus
`store/` for YAML round-tripping.
**Why first:** every other phase depends on this. Getting `ResultAtom` right is 80% of the value.
**Done when:** a hand-written `project.yaml` + `model.yaml` + `experiment.yaml` round-trips, and
`mcm model validate` detects a symbol collision.

### Phase 2 — Template registry
**Deliverable:** `templates/registry.yaml` + loader + the `comap_latex` paper template derived from
the official 2021 file.
**Why now:** templates are pure data; they can be authored while the schemas settle, and the LaTeX
template is needed before any compile test.

### Phase 3 — Experiment engine
**Deliverable:** `sweep.py` (expand `varied`), `runner.py` (execute, record `Run`), `results.py`
(emit `ResultAtom`). Plus `sensitivity_oat`, `model_comparison`, `robustness_noise` templates.
**Why now:** this is where value is created. Everything downstream consumes its output.
**Done when:** `mcm exp run EXP-001` produces a `Run` + typed `ResultAtom`s, and a deliberately
failed run is recorded with `status: failed`.

### Phase 4 — Data engine + EDA
**Deliverable:** ingest/clean/transform/features with hash-addressed versions, lineage, schema,
stats, and EDA figure/table generation.
**Why here:** experiments need datasets, but a synthetic dataset can unblock Phase 3.

### Phase 5 — Visualization
**Deliverable:** the Figure Template Registry (§12.3) + generators bound to `ResultAtom`s.
**Why here:** figures are experiment outputs; they need Phase 3 to exist.

### Phase 6 — Paper compiler
**Deliverable:** resolver → number macros → renderer → latexmk → page budget.
**Done when:** a full paper compiles to PDF and every number comes from a `ResultAtom`.

### Phase 7 — Audit engine
**Deliverable:** the nine check families (§11.3) + the report format.
**Why here:** it needs a compiled paper to check. **But the numeric-binding rules must be designed in
Phase 1** — the audit only works because numbers are references.

### Phase 8 — FastAPI
**Deliverable:** the endpoints in §16.
**Why here:** the CLI already proves the Core works; the API is a thin re-exposure.

### Phase 9 — Vue3
**Deliverable:** the phase-driven navigation (§14) and the five key screens.
**Why last:** the UI is the most expensive layer to change and the least valuable to get early. It
should be built against a stable API.

### Phase 10 — Competition packaging
**Deliverable:** mode switch enforcement, `net_guard`, export bundle, the "Report on Use of AI"
generation, and a **full dry run on a past problem** from data ingest to submitted PDF.
**Why last but mandatory:** the dry run is the only real test of the whole system.

---

## 22. Do this now / Do this later / Do not do this

### ✅ Implement NOW (Phases 1–3 + the LaTeX template)
| Item | Why now |
|---|---|
| **`ResultAtom` + numeric binding** | The entire value proposition depends on it. Retrofitting is a rewrite. |
| **`Experiment` as sweep + protocol** | The corpus proves this is the real unit. A script-based design cannot be fixed later. |
| **`Model` with symbols/equations/assumptions** | Symbol collision detection and the Notations table both depend on model-scoped symbols. |
| **`store` + YAML round-trip** | Cheap, and everything needs it. |
| **COMAP LaTeX template + build pipeline** | Enables the earliest possible end-to-end test. |
| **Page budget reporting** | 72% of recent papers are exactly 25 pages. This is a hard constraint, not a nicety. |
| **`status: failed` on experiments** | 83% of winning papers discuss weaknesses; the best document rejected methods. |
| **The official summary-sheet form** | It is a COMAP requirement (76.6% carry it) and purely mechanical. |

### ⏳ Defer (Phases 4–10, in order)
| Item | Why later |
|---|---|
| Data engine | Valuable, but a synthetic CSV unblocks Phases 3, 5–7. |
| Figure templates | Need ResultAtoms to bind to. |
| Paper compiler polish | Get *one* paper compiling first. |
| Audit families beyond numerical/structure/build | Start with the three that matter most. |
| FastAPI, Vue3 | Additive. Build against a frozen Core. |

### 🚫 Do NOT build (evidence-backed refusals)
| Item | Evidence |
|---|---|
| **Any AI/agent/LLM feature in competition mode** | Task positioning + COMAP disclosure burden. Mode-blocked by design. |
| **AutoML / automatic model selection** | Directly contrary to "human makes every mathematical decision". |
| **Automatic paper *writing*** | The tool renders structure and numbers; it must not invent the mathematics. |
| **A fixed metric enum** | RMSE/MAE are C-only; E/F use entropy weight/TOPSIS. Metrics are a per-problem registry. |
| **Sobol / Morris sensitivity machinery** | Sobol <2%; Morris 2/237 with zero "elementary effects". |
| **`environment` / conda spec as a required field** | **0 papers state one.** |
| **`convergence_tolerance` as required** | **0/237 papers report one.** |
| **`ablation` as a distinct experiment type** | The word appears **0 times** in the modern corpus. Use `variant_of`. |
| **`roc_auc` in the default metric registry** | 4/237 papers. (A naive grep claimed 231 — all false positives from "process".) |
| **A Literature Review template** | **0 of 415 papers** have one. |
| **Mandatory-modeling of every optional section** | Strengths&Weaknesses is only 38.6% — forcing it degrades papers. |
| **A data-versioning DAG with branching/merging** | Papers show linear pipelines. `parent_dataset_id` + hashes suffice. |
| **Making uncited figures an *error*** | Only 37% of *Outstanding* figures are cited. It must be a warning. |

---

## 23. Later Extension Directions

Ordered by evidence-weighted value:

1. **Empirical paper-quality scoring.** We now have 415 O-award papers with extracted structure
   (page counts, figure/table/equation/reference counts, section presence per era). This enables a
   *calibrated* "your paper is unusual in dimension X" check — grounded in the actual distribution,
   never an AI opinion. **Highest value, lowest cost.**
2. **Problem-statement decomposition.** Parse `*/problems/*.pdf` into `Task[]` automatically. Tasks
   are the organizing principle for models, so this closes the loop from problem to model.
3. **Region/parameter-set support.** Papers routinely carry per-region (`A-32150`: three countries),
   per-species (`A/2110178`: three fungi), and per-scenario (`E/2202171`: three climate zones)
   parameter sets. `Parameter.scope` is already in the schema; full UI support is an extension.
4. **A template library grown from the corpus.** Many models recur (Lotka-Volterra, SIR/SEIR, AHP +
   entropy weight, TOPSIS, ARIMA, K-means, GA/PSO). These are legitimate reusable knowledge.
5. **DrawIO/diagram generation** for flowchart and model-structure figures (207 + 51 observed
   captions), which matplotlib cannot produce well.
6. **Reference verification.** Cross-check `references.bib` against a local corpus of the papers'
   own bibliographies for suspicious/duplicate entries.
7. **Multi-attempt history.** Compare this year's attempt to previous attempts in the same project
   tree — a genuine learning aid across seasons.
8. **Judge-perspective completeness check.** Encode the COMAP triage guides' *specific* scoring
   cliffs ("Teams that fail to address both time and geographical dimensions can score no higher
   than a 3 in triage") as explicit checklist items. Very high value per unit of effort, because it
   is a direct transcription of the official rubric.

---

## 24. Summary

**What MCMtools is:** a local, reproducible, traceable competition production toolchain that sits
between a human making mathematical decisions and a submitted 25-page PDF.

**What it is not:** an AI that solves problems, an AutoML system, a paper-writing bot, or an agent.

**The single design commitment that justifies the whole system:**

> Every number in the paper is a reference to a `ResultAtom` produced by a recorded `Run` of a
> declared `Experiment` on a versioned `Dataset` with a model-scoped `Symbol` set — and the Audit
> Engine fails the build when any of those links is broken.

Everything else — the templates, the figure registry, the Vue3 panel, the CLI — is in service of
that one guarantee.

**The evidence that this is the right thing to build:**

- 69% of papers repeat a precise number internally; ~73% of Summary numbers reappear in the body.
  **Nothing prevents divergence today.**
- Only 37% of figures and 33% of tables are ever cross-referenced, while references are 100% cited.
  **Cross-reference integrity is a real, measurable defect class.**
- 74% of embedded images are <500px wide. **Figure quality is a real, measurable problem.**
- 83% of winning papers discuss weaknesses, and the best document two rejected methods.
  **Failure must be a first-class record.**
- 86% of modern papers run a sensitivity analysis with an explicit OAT invariant.
  **The experiment unit is a sweep, not a script.**
- 72% of recent papers are exactly 25 pages. **The page budget is a hard constraint.**

---

*End of design report. No code has been modified. Awaiting review before implementation begins.*
