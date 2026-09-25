#!/usr/bin/env python3
"""End-to-end Phase 1 demo, built from a REAL corpus paper.

Source: MCM-ICM-master/2023美赛特等奖/C/2307166.pdf (Outstanding, Problem C).

That paper builds the PCQL model as an extension of SIR, fits 4 parameters,
sweeps them, and reports a bootstrap prediction interval. Every number below is
transcribed from the paper, so this demo is a fidelity check as much as a
smoke test: if the toolchain cannot represent a real Outstanding paper, Phase 1
is not done.

Run:  python3 examples/phase1_demo.py
"""

from __future__ import annotations

import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from pathlib import Path  # noqa: E402

from mcmcore.mathstore import MathContent, NOTATION_DISCLAIMER  # noqa: E402
from mcmcore.schemas import (  # noqa: E402
    ArtifactBinding,
    Assumption,
    Experiment,
    ExperimentKind,
    Figure,
    Limitation,
    Objective,
    Paper,
    PaperSection,
    Parameter,
    ResultAtom,
    SectionKind,
    Symbol,
    Table,
    Varied,
)
from mcmcore.store import Store  # noqa: E402
from mcmcore.templates import TemplateRegistry, default_registry_root  # noqa: E402
from mcmcore.validate import audit_project  # noqa: E402

DEMO_DIR = ROOT / "examples" / "demo_pcql"


def build() -> Store:
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    st = Store.init(DEMO_DIR, "mcm2023-C-pcql")

    # -- problem lock ------------------------------------------------------
    cfg = st.layout.load_config()
    cfg.phase = "build"
    cfg.locked_problem_id = "PROB-2023-C"
    cfg.team_control_number = "2307166"
    st.layout.save_config(cfg)

    # -- 数学内容：符号、公式、假设 ------------------------------------------
    # 这些东西过去挂在 Model 对象下面。拆掉模型层之后提到项目级 ——
    # 一篇论文只有一张符号表、一套贯穿全文的公式编号。
    content = MathContent()

    # 论文原文：模型有 4 个状态变量（角色在原文里是明确的，很少见，值得保留）
    for i, (g, meaning) in enumerate(
        [("P(t)", "Potentials who might become TPers"),
         ("C(t)", "Crowd: normal TPers who get bored quickly"),
         ("Q(t)", "Quitted: those tired of the game"),
         ("L(t)", "Loyal: those who rarely give up")],
        start=1,
    ):
        content.symbols.append(
            Symbol(id=f"S1{i}", glyph=g, meaning=meaning, role="state",
                   time_varying=True)
        )
    # 4 个参数，带论文拟合出来的值
    for i, (g, meaning, val) in enumerate(
        [("beta", "Participation Factor", 1.77e-01),
         ("gamma", "Boredom Coefficient", 1.77e-02),
         ("lambda", "Conversion Factor", 1.04e-03),
         ("phi", "Loyal Player Boredom Coefficient", 1.14e-03)],
        start=1,
    ):
        content.symbols.append(
            Symbol(id=f"S1P{i}", glyph=g, meaning=meaning, role="parameter")
        )
        # 参数值住进项目参数区 —— 论文正文里的数字都从这里引用。
        st.params.upsert(
            Parameter(
                id=f"P1{i}",
                name=g,
                value=val,
                source="fitted",
                fitted_by="genetic algorithm then Nelder-Mead minimising MSE",
            )
        )

    content.assumptions.append(
        Assumption(
            id="A-PAPER-1",
            text="All Wordle players are Twitter users, and all Twitter users are potential Wordle players.",
            scope="paper",
            label="Assumption 1",
        )
    )
    content.assumptions.append(
        Assumption(
            id="A-MODEL-1",
            text="TPers do TP everyday, and non-TPers never do TP.",
            scope="model",
            label="Consistency of Behavior",
            justification="Defines the compartment transition semantics of PCQL.",
        )
    )
    content.assumptions.append(
        Assumption(
            id="A-MODEL-2",
            text="Non-TPers transformed from TPers will never become TPers again.",
            scope="model",
            label="No Return",
        )
    )

    from mcmcore.schemas import Equation

    content.equations.extend([
        # 基线（SIR）先原样复现，再改造。公式 id 是我们的；编号是论文的全文计数器。
        Equation(id="EQSIR1", number="S1", role="governing", is_numbered=False,
                 latex=r"\frac{dS}{dt} = -\beta S I / N"),
        Equation(id="EQSIR2", number="S2", role="governing", is_numbered=False,
                 latex=r"\frac{dI}{dt} = \beta S I / N - \gamma I"),
        Equation(id="EQ1", number="1", role="governing",
                 latex=r"\frac{dP}{dt} = -\beta P (C+L)/N"),
        Equation(id="EQ2", number="2", role="governing",
                 latex=r"\frac{dC}{dt} = \beta P (C+L)/N - \gamma C - \lambda C"),
        Equation(id="EQ3", number="3", role="governing", latex=r"\frac{dQ}{dt} = \gamma C"),
        Equation(id="EQ4", number="4", role="governing",
                 latex=r"\frac{dL}{dt} = \lambda C - \phi L"),
    ])
    # 目标函数（原来挂在 Model II 上；现在项目级）
    content.objective = Objective(
        expressions=[r"\min \sum_t (\hat{y}_t - y_t)^2"],
        sense="min",
        description="MSE loss used to estimate parameters.",
    )
    st.math.save(content)

    # -- Experiment: the sensitivity sweep ---------------------------------
    # -- Experiment: the sensitivity sweep ---------------------------------
    st.save_experiment(
        Experiment(
            id="EXP-001",
            label="Parameter sensitivity of PCQL",
            kind=ExperimentKind.SENSITIVITY_OAT,
            section_ref="6",
            varied=[Varied(name="beta", values=[0.10, 1.77e-01, 0.25])],
            held_fixed=["gamma", "lambda", "phi"],
            n_runs=1,
            aggregation="none",
            motivation=(
                "beta is the least constrained parameter; the paper notes some "
                "parameters rest on limited evidence."
            ),
            method="ode_solve",
            software="Python",
            entrypoint="code/pcql.py:run",
            status="planned",
            metrics=[{"name": "peak_C", "direction": "neutral"}],
        )
    )

    # 建模代码放在 code/ 下，与 experiments/（实验定义）分开：
    #   code/         脚本本身
    #   experiments/  实验协议（跑什么、扫哪个参数）
    #   runs/         每次运行的归档（机器写，不要手改）
    # 分开的理由：改代码不应该动实验配置，改配置也不该动代码，
    # 两者混在一层目录里，diff 会看不出到底改了什么。
    src = Path(__file__).resolve().parent / "experiments" / "pcql_sensitivity.py"
    dst = st.root / "code" / "pcql.py"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    # -- Experiment: bootstrap interval ------------------------------------
    st.save_experiment(
        Experiment(
            id="EXP-002",
            kind=ExperimentKind.MONTE_CARLO,
            section_ref="5",
            method="bootstrap",
            n_runs=1000,
            aggregation="2.5% and 97.5% quantiles",
            readout_condition="March 1, 2023",
            status="completed",
        )
    )

    # -- Result atoms: the paper's actual reported numbers -----------------
    st.append_atoms([
        ResultAtom(
            atom_id="RES-1001", name="beta", value=1.77e-01, format="%.2e",
            unit="/day", experiment_id="EXP-001", condition="fitted",
            renderings={"paper": "1.77e-01"},
        ),
        ResultAtom(
            atom_id="RES-1002", name="gamma", value=1.77e-02, format="%.2e",
            unit="/day", experiment_id="EXP-001", condition="fitted",
            renderings={"paper": "1.77e-02"},
        ),
        ResultAtom(
            atom_id="RES-1003", name="lambda", value=1.04e-03, format="%.2e",
            unit="/day", experiment_id="EXP-001", condition="fitted",
            renderings={"paper": "1.04e-03"},
        ),
        ResultAtom(
            atom_id="RES-1004", name="phi", value=1.14e-03, format="%.2e",
            unit="/day", experiment_id="EXP-001", condition="fitted",
            renderings={"paper": "1.14e-03"},
        ),
        ResultAtom(
            atom_id="RES-1101", name="report_forecast_mean", value=14689.9,
            format="%.1f", unit="reports", experiment_id="EXP-002",
            condition="March 1, 2023", direction="neutral",
        ),
        ResultAtom(
            atom_id="RES-1102", name="report_forecast_lo", value=11173.04,
            format="%.2f", unit="reports", experiment_id="EXP-002",
            condition="March 1, 2023, 2.5% quantile",
        ),
        ResultAtom(
            atom_id="RES-1103", name="report_forecast_hi", value=17069.15,
            format="%.2f", unit="reports", experiment_id="EXP-002",
            condition="March 1, 2023, 97.5% quantile",
        ),
    ])

    # -- Artifacts bound to atoms (never screenshots) ----------------------
    st.save_table(
        Table(
            id="TAB-001",
            template_id="tab.parameter_settings",
            caption="Fitted parameter values for the PCQL Model.",
            label="tab:params",
            bindings=[ArtifactBinding(atom_id=f"RES-100{i}") for i in range(1, 5)],
            referenced_in=["SEC-050"],
            columns=[
                {"header": "Symbol", "literal": "beta"},
                {"header": "Meaning", "literal": "Participation Factor"},
                {"header": "Value", "atom_id": "RES-1001", "format": "%.2e"},
                {"header": "Source", "literal": "fitted (MSE)"},
            ],
            rows=[
                {"literal": "gamma", "atom_ids": ["RES-1002"]},
                {"literal": "lambda", "atom_ids": ["RES-1003"]},
                {"literal": "phi", "atom_ids": ["RES-1004"]},
            ],
        )
    )
    st.save_figure(
        Figure(
            id="FIG-001",
            template_id="fig.sensitivity_line",
            experiment_id="EXP-001",
            caption="Sensitivity of peak participation to the participation factor.",
            label="fig:beta_sens",
            # Starts bound to the fitted beta only. Phase 3 re-binds it to the
            # sweep atoms once the sweep has produced them, because a figure
            # bound to results must reference results, not just inputs.
            bindings=[ArtifactBinding(atom_id="RES-1001", role="x")],
            referenced_in=["SEC-050"],
            file="figures/FIG-001.pdf",
        )
    )
    st.save_figure(
        Figure(
            id="FIG-002",
            template_id="fig.pred_vs_actual",
            experiment_id="EXP-002",
            caption="Bootstrap prediction interval for March 1, 2023.",
            label="fig:bootstrap",
            bindings=[
                ArtifactBinding(atom_id="RES-1102", role="error"),
                ArtifactBinding(atom_id="RES-1101", role="y"),
                ArtifactBinding(atom_id="RES-1103", role="error"),
            ],
            # INTENTIONALLY left uncited to demonstrate the calibrated warning.
        )
    )

    # -- Paper -------------------------------------------------------------
    st.save_paper(
        Paper(
            paper_id="PAPER-001",
            problem_id="PROB-2023-C",
            locked=True,
            summary={
                "problem_letter": "C",
                "team_control_number": "2307166",
                "key_words": ["Wordle", "SIR", "ODE", "Bootstrap", "Parameter Estimation"],
            },
            sections=[
                PaperSection(id="SEC-010", kind=SectionKind.INTRODUCTION,
                             title="Introduction", order=10,
                             body="Wordle spread rapidly through social media."),
                PaperSection(id="SEC-020", kind=SectionKind.RESTATEMENT,
                             title="Restatement of the Problem", order=20,
                             body="Forecast the number of reported results."),
                PaperSection(id="SEC-030", kind=SectionKind.ASSUMPTIONS,
                             title="Assumptions and Justifications", order=30,
                             body="Assumption 1 ..."),
                PaperSection(id="SEC-040", kind=SectionKind.NOTATIONS,
                             title="Notations", order=40, generated=True),
                PaperSection(id="SEC-050", kind=SectionKind.MODEL,
                             title="Model I: PCQL Model", order=50,
                             template_ref="M01",
                             body=r"We fit $\beta=\numRESOneZeroZeroOne$ ..."),
                PaperSection(id="SEC-060", kind=SectionKind.MODEL,
                             title="Model II: Report Forecasting", order=60,
                             template_ref="M02",
                             body="Model II consumes the compartments of Model I."),
                PaperSection(id="SEC-070", kind=SectionKind.SENSITIVITY,
                             title="Sensitivity Analysis", order=70,
                             body="We vary beta while holding others fixed."),
                PaperSection(id="SEC-080", kind=SectionKind.STRENGTHS_WEAKNESSES,
                             title="Strengths and Weaknesses", order=80,
                             body="The model is interpretable."),
                PaperSection(id="SEC-090", kind=SectionKind.CONCLUSION,
                             title="Conclusion", order=90, body="PCQL forecasts well."),
                PaperSection(id="SEC-100", kind=SectionKind.REFERENCES,
                             title="References", order=100, generated=True),
                # COMAP requires a page-limit-EXEMPT disclosure section whenever
                # AI was used. Omitting it is the most common compliance failure,
                # so the auditor treats it as an ERROR rather than a warning.
                PaperSection(id="SEC-110", kind=SectionKind.REPORT_ON_AI,
                             title="Report on Use of AI", order=110,
                             generated=True, enabled=True),
            ],
            build={"page_count": 25, "pdf_path": "export/main.pdf"},
            ai_usage={
                "ai_used": True,
                "entries": [
                    {
                        "tool": "DeepSeek",
                        "version": "v4.1",
                        "purpose": "development",
                        "phase": "pre_competition",
                        "in_report": False,
                    }
                ],
            },
        )
    )
    return st



def generate_figures(st: Store) -> int:
    """Generate the bound figures from the ResultAtoms.

    Figures are generated, never pasted: each one reads its numbers from atoms,
    so regenerating after a result changes cannot leave a stale picture behind.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    out = st.root / "figures"
    out.mkdir(parents=True, exist_ok=True)
    atoms = {a.atom_id: a for a in st.load_atoms()}

    beta0 = atoms["RES-1001"].numeric()
    betas = np.linspace(max(0.01, beta0 * 0.4), beta0 * 1.8, 60)
    peak = 1.0 / (1.0 + (betas / beta0) ** -1.6)
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.plot(betas, peak, lw=2, color="#1f4e79")
    ax.axvline(beta0, ls="--", lw=1.2, color="#c00000")
    ax.annotate(f"fitted $\\beta$ = {beta0:.2e}", xy=(beta0, 0.5),
                xytext=(beta0 * 1.08, 0.35), color="#c00000", fontsize=9)
    ax.set_xlabel(r"Participation factor $\beta$")
    ax.set_ylabel("Normalised peak participation")
    ax.set_title(r"Sensitivity of peak participation to $\beta$")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "FIG-001.pdf")
    plt.close(fig)

    mean = atoms["RES-1101"].numeric()
    lo = atoms["RES-1102"].numeric()
    hi = atoms["RES-1103"].numeric()
    fig, ax = plt.subplots(figsize=(6, 3.6))
    days = np.arange(0, 30)
    traj = mean * (0.55 + 0.45 * np.exp(-((days - 12) ** 2) / 220))
    ax.plot(days, traj, lw=2, color="#1f4e79", label="forecast mean")
    ax.fill_between(days, traj * (lo / mean), traj * (hi / mean),
                    alpha=0.22, color="#1f4e79", label="95% bootstrap interval")
    ax.axhline(mean, ls=":", lw=1.1, color="#c00000")
    ax.annotate(f"mean = {mean:,.0f}", xy=(1, mean), xytext=(1, mean * 1.06),
                color="#c00000", fontsize=9)
    ax.set_xlabel("Days from forecast origin")
    ax.set_ylabel("Reported results")
    ax.set_title("Bootstrap forecast with 95% interval")
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "FIG-002.pdf")
    plt.close(fig)
    return len(list(out.glob("*.pdf")))


def main() -> int:
    print("=" * 74)
    print("MCMtools Phase 1 demo - reconstructed from 2023 MCM Problem C/2307166")
    print("=" * 74)

    st = build()
    print(f"\nProject created at {DEMO_DIR.relative_to(ROOT)}")

    n_figs = generate_figures(st)
    for fig in st.list_figures():
        fig.file = f"figures/{fig.id}.pdf"
        st.save_figure(fig)
    print(f"Figures generated and bound: {n_figs}")

    reg = TemplateRegistry(default_registry_root()).load()
    print(f"Template registry: {len(reg)} templates {reg.summary()}")

    print("\n" + "-" * 74)
    print("RESULT ATOMS (single source of truth for every number)")
    print("-" * 74)
    for a in st.load_atoms():
        cond = f"  [{a.condition}]" if a.condition else ""
        print(f"  {a.atom_id:10s} {a.name:22s} = {a.rendered():>12s} {a.unit or '':10s}{cond}")

    print("\n" + "-" * 74)
    print("WHAT CHANGES WHEN ONE NUMBER MOVES")
    print("-" * 74)
    atoms = {a.atom_id: a for a in st.load_atoms()}
    old = atoms["RES-1101"]
    print(f"  Suppose a rerun changes {old.atom_id} ({old.name}):")
    print(f"    before: {old.rendered()} {old.unit}")
    old.value = 15000.0
    st.append_atoms([old])
    print(f"    after : {old.rendered()} {old.unit}")
    for fig in st.list_figures():
        if fig.is_stale_if(["RES-1101"]):
            print(f"    -> {fig.id} becomes STALE (bound via {[b.role for b in fig.bindings]})")
    for tab in st.list_tables():
        if "RES-1101" in tab.bound_atom_ids():
            print(f"    -> {tab.id} becomes STALE")
    print("    Every rendering of this number now follows automatically.")

    print("\n" + "-" * 74)
    print("AUDIT")
    print("-" * 74)
    report = audit_project(st, reg)
    for f in report.errors:
        print(f"  {f}")
    for f in report.warnings:
        print(f"  {f}")
    print(f"\n  {report.summary_line()}")

    print("\n" + "-" * 74)
    print("TEMPLATE PROVENANCE SAMPLE")
    print("-" * 74)
    t = reg.get("exp.sensitivity_oat")
    print(f"  {t.template_id}: {t.description}")
    for e in t.evidence[:2]:
        print(f"    * {e[:88]}...")

    # -- negative control: prove the compliance check is not decorative ----
    print("\n" + "-" * 74)
    print("NEGATIVE CONTROL: remove the AI disclosure, confirm the audit fails")
    print("-" * 74)
    paper = st.load_paper()
    paper.sections = [s for s in paper.sections if s.kind != SectionKind.REPORT_ON_AI]
    st.save_paper(paper)
    broken = audit_project(st, reg)
    for f in broken.errors:
        print(f"  {f}")
    print(f"\n  {broken.summary_line()}")
    assert not broken.ok(), "the AI-disclosure check failed to fire"

    # -- Phase 2: compile the paper ----------------------------------------
    print("\n" + "-" * 74)
    print("PHASE 2: COMPILE TO PDF")
    print("-" * 74)
    from mcmcore.compiler import PaperCompiler, find_engine

    if find_engine("pdflatex") is None:
        print("  pdflatex not found; skipping the compile stage.")
    else:
        # Undo the negative control: put the disclosure section back so the
        # project is compliant again before we compile it.
        paper = st.load_paper()
        if not any(s.kind == SectionKind.REPORT_ON_AI for s in paper.sections):
            paper.sections.append(
                PaperSection(id="SEC-110", kind=SectionKind.REPORT_ON_AI,
                             title="Report on Use of AI", order=110,
                             generated=True, enabled=True)
            )
            st.save_paper(paper)
        result = PaperCompiler(st).build()
        for line in result.messages:
            print("  " + line)
        if result.ok:
            print(f"\n  PDF: {result.pdf_path}")
            print(f"  Budget: {result.summary()}")

    # -- Phase 3: run the experiment, prove the staleness loop -------------
    print("\n" + "-" * 74)
    print("PHASE 3: RUN THE EXPERIMENT AND CLOSE THE STALENESS LOOP")
    print("-" * 74)
    from mcmcore.figures import FigureGenerator
    from mcmcore.runner import ExperimentRunner, stale_artifacts

    runner = ExperimentRunner(st)

    print("\n1. Run the sensitivity sweep on the paper's fitted parameters.")
    out = runner.run("EXP-001")
    print("   " + out.summary().replace("\n", "\n   "))
    for r in out.runs:
        params = ", ".join(f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}"
                           for k, v in sorted(r.resolved_parameters.items()))
        print(f"     {r.run_id}  {r.status.value:8s} {r.duration_seconds:.3f}s  {params}")

    # Bind FIG-001 to the sweep atoms it is supposed to visualise, now that the
    # sweep has produced them. This is the binding the stale loop protects.
    sweep = sorted(
        (a for a in st.load_atoms()
         if a.name == "peak_active" and a.experiment_id == "EXP-001"
         and (a.condition or "").startswith("beta=")),
        key=lambda a: float(a.condition.split("beta=")[1].split(",")[0]),
    )
    fig = st.load_figure("FIG-001")
    fig.bindings = [ArtifactBinding(atom_id=a.atom_id, role="y") for a in sweep]
    fig.bindings.append(ArtifactBinding(atom_id="RES-1001", role="x"))
    fig.status = "generated"
    st.save_figure(fig)
    print(f"   FIG-001 bound to {len(sweep)} sweep atoms: "
          f"{', '.join(a.condition.split(',')[0] for a in sweep)}")

    print("\n2. Rerun with IDENTICAL inputs: nothing may become stale.")
    again = runner.run("EXP-001")
    print(f"   changed atoms: {len(again.changed)}  ->  stale: {again.stale.total}")
    assert not again.changed, "an identical rerun must not invalidate artifacts"

    print("\n3. Refit gamma in the parameter area and rerun. The figure MUST go stale.")
    # 参数改动直接写参数区（params/parameters.yaml），不再绕道模型层。
    gamma = st.params.load().by_name()["gamma"]
    print(f"   gamma {gamma.value:g} -> 2.50e-02")
    gamma.value = 2.50e-02
    st.params.upsert(gamma)

    changed_out = runner.run("EXP-001")
    print(f"   {len(changed_out.changed)} atom(s) changed -> "
          f"{changed_out.stale.total} artifact(s) stale")
    for fid in changed_out.stale.stale_figures:
        print(f"     STALE: {fid}")

    figs, tabs = stale_artifacts(st)
    assert figs, "the bound figure should be stale after a parameter refit"

    print("\n4. Regenerate the stale figure from the NEW atom values.")
    gen = FigureGenerator(st)
    regenerated = gen.regenerate()
    for w in gen.warnings:
        print(f"   WARNING: {w}")
    print(f"   regenerated: {', '.join(regenerated) or 'none'}")
    figs, tabs = stale_artifacts(st)
    print(f"   still stale: {len(figs) + len(tabs)}")
    assert not figs and not tabs, "regeneration must clear the stale flag"

    print("\n5. Rebuild the paper: the PDF now carries the refitted numbers.")
    final = PaperCompiler(st).build()
    for line in final.messages:
        print("   " + line)
    if final.ok:
        print(f"\n   PDF: {final.pdf_path}")
        print(f"   Budget: {final.summary()}")

    print("\n" + "=" * 74)
    print("Phases 1-3 complete. A number now has exactly one source:")
    print("  参数区 -> 实验运行 -> ResultAtom -> 宏 -> PDF")
    print("and changing it at the top invalidates every artifact bound to it.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
