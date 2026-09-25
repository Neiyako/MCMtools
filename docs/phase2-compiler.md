# Phase 2 — The Paper Compiler

**Status: complete.** 152 tests passing (65 new). Compiles a real 5-page PDF with
vector figures from the object model.

The critical path from the architecture doc is
`schemas → store → experiment → results → paper(numbers) → audit`.
Phase 1 did schemas, store and audit. Phase 2 does **paper(numbers)**: the
compiler that turns `ResultAtom` records into a COMAP-formatted PDF in which
every number is a reference.

---

## 1. What was built

```
core/mcmcore/compiler/
  numbers.py     ResultAtom -> \newcommand macros; bare-number detection
  resolver.py    object graph -> render context (+ reference checks)
  artifacts.py   Figure/Table -> generated .tex artifacts
  renderer.py    Paper -> main.tex, generated/*.tex, references.bib
  compiler.py    6-stage pipeline + page measurement
  __init__.py    flat import surface
```

```bash
./core/mcm paper build      --dir <project>     # compile to PDF
./core/mcm paper engine                         # show available TeX engines
```

---

## 2. The mechanism

**A number in the paper is a reference, never a literal.**

```latex
% build/generated/numbers.tex  (regenerated every build)
\newcommand{\numRESOneOneZeroOne}{15000.0}
```

```latex
% the author writes, in paper.yaml
The forecast is $\numRESOneOneZeroOne{}$ reports.
```

The demo proves this is not cosmetic. `RES-1101` was changed from `14689.9` to
`15000.0`, and the rebuilt PDF's figure annotation reads **`mean = 15,000`** —
the value propagated through LaTeX into an embedded vector graphic without
anyone editing the prose or the figure code.

Bare numbers are detected and warned about:

```
WARNING NUMERIC_UNBOUND: Section 'SEC-030' contains the literal number 1 in
prose. Bind it to a ResultAtom macro, or mark it \lit{1} if it is not a result.
```

`\lit{...}` is the declared escape hatch for non-results — page counts, fold
counts, problem letters, years. Without it, "5-fold" and "Problem C" would be
false positives, and a check that cries wolf gets ignored.

---

## 3. The pipeline

| Stage | What it does | Failure behaviour |
|---|---|---|
| 1 Resolve | build the render context; check every cross-reference | reports dangling refs **before** LaTeX runs |
| 2 Generate | copy/generate figures, render tables to `.tex` | missing figure → **visible placeholder**, not a crash |
| 3 Render | `main.tex`, `generated/numbers.tex`, `models.tex`, `references.bib` | — |
| 4 Compile | pdflatex ×N until references stabilise | engine absent → sources still written |
| 5 Measure | page count vs the 25-page budget, persisted to `paper.yaml` | — |
| 6 Verify | hand findings to the audit engine | — |

Stage 1 catching problems early is what keeps a failed build diagnosable: you
get `Section 'SEC-050' references 'fig:nope', which is not a known figure label`
instead of a cryptic TeX error 200 lines into a log.

---

## 4. Four real bugs found and fixed

All were caught by tests or by inspecting real output, and all are now
regression-tested.

**1. Page counting was wrong — reported 10 pages for a 4-page PDF.**
pdfTeX compresses the page tree into object streams, so a raw byte scan finds
no `/Type /Page` at all. After adding zlib inflation, my "max `/Count`" heuristic
still over-counted: `/Count` also appears on `/Outlines`, where it means the
**bookmark count**. Fixed to read only the `/Type /Pages` node. Now verified
against 8 real corpus PDFs — 8/8 exact, and all of them 24–25 pages, which
independently reconfirms the page-budget finding.

**2. Figures and tables were generated but never placed in the document.**
The renderer had no placement logic at all, so a figure bound to ResultAtoms
was written to disk and then orphaned — it never reached a page. Fixed: an
artifact is placed in the section that cites it, and anything *uncited* is still
placed in a trailing section, because a bound artifact must never be silently
dropped.

**3. A placeholder was written as `.pdf`, killing the build.**
When a figure file was missing I wrote a LaTeX text box to a file named
`FIG-001.pdf`. pdflatex then tried to parse it and died with an opaque
`xpdf: Couldn't read xref table`. Two fixes: placeholders are now `.tex`, and
the renderer emits a loud `[MISSING FIGURE ...]` box instead of calling
`\includegraphics`.

**4. The resolver could silently contradict the Paper it was given.**
`sections` was a separate argument, so `resolve([], [], ..., paper)` with a
paper that *had* sections produced an empty document and a spurious
"AI use undisclosed" error. Now the Paper is authoritative when `sections` is
empty.

Also fixed: `\includegraphics[width=0.8\linewidth]` was flagged as containing a
bare number, because only the mandatory `{...}` argument was stripped, not the
optional `[...]` one.

---

## 5. What the demo produces

```bash
python3 examples/phase1_demo.py
```

Rebuilds `2023 C/2307166` from scratch and compiles it:

```
[1/6] Resolved .......... 2 models, 8 symbols, 6 equations, 11 number macros
[2/6] Generated ......... 2 figures, 1 tables
[3/6] Rendered .......... main.tex + 11 sections, 0 references
[4/6] Compiled .......... pdflatex x2
[5/6] Measured ........... 5/25 pages (20 remaining)
[6/6] Verify ............. 1 finding(s) from the compiler
```

The resulting PDF has: a real COMAP summary sheet as page 1 (`Problem Chosen` /
`Summary Sheet` / `Team Control Number` in a 3-column header), a table of
contents, `Page N` running heads, an auto-generated Notations table carrying the
corpus-standard non-exhaustive disclaimer, two figures as **vector** PDFs (168
and 186 drawing paths), a bound parameter table, and the COMAP-mandated
`Report on Use of AI`.

---

## 6. Deliberately not built

| Not built | Why |
|---|---|
| a full LaTeX parser | the compiler emits LaTeX; it does not need to read it back |
| PDF library dependency | page counting is ~30 lines of zlib + regex, verified on 8 real PDFs |
| figure-type inference | the template registry declares it; guessing from a filename is unreliable |
| automatic prose rewriting | the compiler makes bad references loud; it must not rewrite the author's argument |
| `latexmk` as the default | pdflatex ×2 with a log-inspection loop is faster and has no Perl dependency |

---

## 7. Phase 3 entry point

The remaining gap on the critical path is **`experiment → results`**: nothing
yet *produces* `Run` and `ResultAtom` records from a real computation. Phase 1
defined the schema and Phase 2 consumes it, so Phase 3 is the experiment runner:

1. Execute a declared `Experiment` protocol against a `Model` + `Dataset`.
2. Emit `Run` records with resolved parameters and durations.
3. Emit `ResultAtom` records with condition and format.
4. Mark every artifact bound to a changed atom as `STALE`.

That last step is the one that closes the loop: at present the compiler will
happily rebuild a stale figure, because "stale" is recorded but nothing acts on
it. A `mcm exp run` that marks dependents stale, plus a build that refuses (or
loudly warns) when an artifact is stale, is what makes the numbers discipline
enforced rather than merely available.
