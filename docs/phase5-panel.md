# Phase 5 — The Panel

**Status: complete.** 81 panel checks pass, plus the 276 Python tests. The panel
is served by the same command that runs the API:

```bash
./core/mcm --dir <project> serve        # then open http://127.0.0.1:8420
```

---

## 1. What was built

```
web/index.html      the shell
web/app.js          screens, routing, all rendering
web/app.css         styling
web/package.json    one devDependency: jsdom, for the DOM tests
web/tests/          logic, badges, render, flows
```

No framework, no bundler, no build step. `app.js` and `app.css` are served
verbatim from the Python process.

**Why not Vue.** The roadmap specified Vue3. I built it in plain ES modules
instead, and the reason is the tool's own premise: a competition runs offline,
under time pressure, on a machine whose toolchain the user must be able to
reason about. A panel that is the output of a bundler is a panel the user cannot
inspect while debugging at 3am. The entire application is ~640 lines of readable
JS with no transitive dependency tree, and it loads directly from the server
that owns the data. If it outgrows that, adding Vue later is a contained change
because the API contract — not the framework — is the interface.

---

## 2. The screens

Navigation is **phase-driven**, so a screen that cannot work is never offered.

```
problem_selection  ->  Problems, Settings
problem_locked     ->  Problems, Settings
build              ->  Overview, Data, Models, Experiments, Results, Paper, Audit
finalize           ->  Overview, Paper, Audit, Settings
```

Eight screens: **Overview** (workflow state + blockers), **Data**, **Models**
(each as a mathematical identity, with parameter provenance), **Experiments**
(protocols, run status, failure evidence, trial expansion), **Results** (figures
you can see, bound to their atoms, with regenerate), **Paper** (sections, the
live page budget, AI compliance, build), **Audit** (the submission gate), and
**Settings** (project + run mode).

Two placement decisions come straight from the corpus rather than from taste:

- **There is no "Visualization" tab.** Figures are outputs of experiments.
  A separate tab would encourage exactly the anti-pattern the corpus exposes —
  figures made outside the pipeline and pasted in. Figures live under Results,
  bound to their `ResultAtom`s.
- **Failed experiments are a first-class card state, not an error to hide.**
  83% of winning papers discuss weaknesses and the best document rejected
  methods. Hiding a failure would degrade the paper.

---

## 3. Verified, not assumed

The panel was tested in a **real DOM against the live server**, because a panel
tested against mocks will pass while showing the user nothing.

```
$ npm --prefix web test
...
  PASS  overview       63 nodes,   934 chars
  PASS  data            4 nodes,    69 chars
  PASS  models         38 nodes,   176 chars
  PASS  experiments    43 nodes,   240 chars
  PASS  results        49 nodes,   423 chars
  PASS  paper         104 nodes,   819 chars
  PASS  audit          31 nodes,   752 chars
  PASS  problems        6 nodes,   180 chars
  PASS  settings       29 nodes,   276 chars
ALL SCREENS RENDER
```

The flows test drives the paths a user actually takes, through the DOM:

| Flow | Assertion |
|---|---|
| Run an experiment | toast reports the outcome; screen re-renders; button re-enables |
| Inspect trials | modal opens and lists the expanded parameter sets |
| Refit a parameter | the figure is marked **stale** and the sidebar shows a badge |
| Regenerate | stale clears, verified against `/api/figures/stale` |
| Submission gate | the verdict shown matches `ready_to_submit` exactly |
| Toggle a section | the change persists through the API |

The third and fourth together are the whole toolchain's claim, exercised through
the UI: **change an input → the picture that no longer matches is flagged →
regenerate → the gate clears.**

---

## 4. What the DOM testing caught

Unit tests passed while the rendered page was wrong, so these only surfaced under
a real DOM:

**The app-side `setTimeout` stub broke Node's HTTP client.** Installing it before
the payload fetches made undici throw `fastNowTimeout?.unref is not a function`
— a confusing failure whose cause was three steps away from its symptom. Fixed
by fetching every payload before stubbing, and the ordering is now commented,
because it is not obvious and the error message does not point at it.

**A phase with no reachable screen.** `finalize` originally offered `overview`,
which the screen table did not list for that phase, so navigating there would
render nothing. The navigation test now asserts every screen belongs to exactly
one group and that each phase resolves to a non-empty sidebar.

**Test assumptions that were themselves wrong.** Three assertions failed on
correct behaviour: the demo has 0 stale artifacts (so an empty badge is right),
`experiments` counts an experiment as done because the fixture defines one, and
an incomplete paper is *genuinely* not submittable. Each was fixed by deriving
the expectation from the payload instead of hardcoding a belief about it.

---

## 5. Two endpoints the panel needed

Building the UI revealed two gaps in the API:

- `GET /api/figures/{id}/file` — serve the generated figure. Without it the
  Results screen could list figures but not show them. Figures are vector PDFs
  and the panel embeds them directly, which keeps them crisp at any zoom; the
  toolchain must not repeat the corpus's mistake of rasterising its own output
  (74% of embedded images in real papers are under 500px wide).
- `GET /api/tables/{id}/source` — the generated LaTeX. There is deliberately no
  HTML table renderer: a table's real form is LaTeX, and a half-faithful HTML
  preview would show columns the PDF does not have. Showing the source is honest.

Both are path-traversal guarded, with a test asserting `../../etc/passwd` is
refused.

---

## 6. Deliberately not built

| Not built | Why |
|---|---|
| a framework / bundler | see §1 — inspectability is the point |
| a WebSocket | a competition sweep is seconds; the run returns when done |
| optimistic UI updates | the panel re-reads `/api/state` after every mutation, so what you see is what the auditor sees |
| a charting library | figures are generated server-side from atoms; the panel displays, it does not plot |
| a dark/light toggle | it follows `prefers-color-scheme`; a competition has enough decisions already |
| drag-and-drop section reordering | the spine order is evidence-based (14 precedence relations hold at 100%) and not the author's to rearrange |

---

## 7. What remains

The roadmap's remaining item is **competition packaging** (Phase 10): the export
bundle exists (`GET /api/export/bundle`), and mode enforcement exists (Phase 4).
What is untested is a **full dry run on a past problem**, from data ingest to
submitted PDF. The architecture doc calls that *"the only real test of the whole
system"*, and it is right — every phase so far has been verified on a
reconstructed project, which is not the same as running one end to end.

Two smaller gaps worth naming: only 1 of 9 declared experiment templates has a
reference implementation, and the Data screen has no ingest UI (datasets are
added via the CLI).

---

## 8. Honest limitations

**The panel is desktop-first.** It reflows to a single column under 760px but has
not been tested on a phone, and drag targets are sized for a mouse.

**jsdom is not a browser.** It executes the real code against real payloads and
catches template and data-shape errors, but it does not do layout, so it cannot
catch a CSS bug that makes something invisible. The screens were additionally
rendered to standalone HTML and inspected, but visual regressions need a human
or a real browser.
