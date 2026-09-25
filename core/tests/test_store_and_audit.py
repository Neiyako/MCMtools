"""Store, template-registry, and audit tests."""

import pytest

from mcmcore.schemas import (
    ArtifactBinding,
    Assumption,
    Equation,
    Experiment,
    ExperimentKind,
    Figure,
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
from mcmcore.mathstore import MathContent
from mcmcore.store import Store
from mcmcore.templates import TemplateRegistry, default_registry_root
from mcmcore.validate import audit_project


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------


class TestStoreRoundTrip:
    def test_math_round_trip_is_identity(self, tmp_path):
        """符号、公式、假设往返读写必须完全一致。

        这些东西现在是项目级的（math/），不再挂在模型下面。
        """
        st = Store.init(tmp_path, "t")
        content = MathContent(
            symbols=[Symbol(id="S1", glyph="beta", meaning="participation",
                            role="parameter")],
            assumptions=[Assumption(id="A1", text="Behaviour is consistent.",
                                    scope="paper", label="Assumption 4")],
            equations=[Equation(id="E1", number="5", latex="x = y")],
        )
        st.math.save(content)
        assert st.math.load() == content

    def test_params_round_trip_is_identity(self, tmp_path):
        st = Store.init(tmp_path, "t")
        param = Parameter(id="P1", name="gamma", value=0.0177, source="fitted")
        st.params.upsert(param)
        assert st.params.load().by_name()["gamma"] == param

    def test_experiment_round_trip(self, tmp_path):
        st = Store.init(tmp_path, "t")
        e = Experiment(
            id="EXP-01",
            kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[Varied(name="k", values=[4.5, 5, 5.5])],
            held_fixed=["b0"],
            n_runs=3,
            aggregation="mean and std",
        )
        st.save_experiment(e)
        assert st.load_experiment("EXP-01") == e

    def test_atom_append_merges_by_id(self, tmp_path):
        st = Store.init(tmp_path, "t")
        st.append_atoms([ResultAtom(atom_id="R1", name="a", value=1)])
        st.append_atoms([ResultAtom(atom_id="R1", name="a", value=2)])
        atoms = st.load_atoms()
        assert len(atoms) == 1
        assert atoms[0].value == 2

    def test_open_requires_init(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Store.open(tmp_path / "nope")

    def test_layout_directories_created(self, tmp_path):
        Store.init(tmp_path, "t")
        for sub in ("math", "params", "experiments", "results", "paper", "export"):
            assert (tmp_path / sub).is_dir()

    def test_dataset_round_trip_preserves_schema_key(self, tmp_path):
        from mcmcore.schemas import Dataset

        st = Store.init(tmp_path, "t")
        d = Dataset(
            dataset_id="DS-001",
            name="raw",
            schema=[{"name": "temp", "dtype": "float64", "unit": "C"}],
        )
        st.save_dataset(d)
        loaded = st.load_dataset("DS-001")
        assert loaded.schema_[0].name == "temp"


# --------------------------------------------------------------------------
# Template registry
# --------------------------------------------------------------------------


class TestTemplateRegistry:
    @pytest.fixture(scope="class")
    def registry(self):
        return TemplateRegistry(default_registry_root()).load()

    def test_registry_loads(self, registry):
        assert len(registry) > 0

    def test_registry_has_no_errors(self, registry):
        assert registry.validate() == []

    def test_all_five_kinds_present(self, registry):
        for kind in ("model", "experiment", "figure", "table", "paper"):
            assert registry.by_kind(kind), f"no templates of kind {kind}"

    def test_every_template_carries_evidence(self, registry):
        """Templates exist because the corpus justified them, not on a hunch."""
        for t in registry.all():
            assert t.evidence, f"{t.template_id} has no corpus evidence"

    def test_known_ids_resolve(self, registry):
        for tid in (
            "exp.sensitivity_oat",
            "tab.parameter_settings",
            "fig.sensitivity_line",
            "paper.comap_latex",
            "paper.section_spine",
        ):
            assert tid in registry

    def test_oat_template_declares_invariant_requirement(self, registry):
        t = registry.get("exp.sensitivity_oat")
        assert "held_fixed" in t.requires.required_inputs

    def test_section_spine_never_templates_literature_review(self, registry):
        """'Literature Review' appears in 0 of 415 papers."""
        t = registry.get("paper.section_spine")
        assert "literature_review" in t.defaults["never_template"]
        kinds = [s["kind"] for s in t.defaults["spine"]]
        assert "literature_review" not in kinds

    def test_section_spine_order_matches_100pct_precedence(self, registry):
        """Introduction must precede References (holds 100% in the corpus)."""
        t = registry.get("paper.section_spine")
        spine = {s["kind"]: s["order"] for s in t.defaults["spine"]}
        assert spine["introduction"] < spine["references"]
        assert spine["assumptions"] < spine["notations"]

    def test_comap_template_bundles_official_reference_file(self, registry):
        t = registry.get("paper.comap_latex")
        assert t.reference_file
        assert (default_registry_root() / "paper" / "comap_latex" / t.reference_file).exists()

    def test_missing_entrypoint_is_reported(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "template.yaml").write_text(
            "template_id: x.bad\nkind: experiment\nentrypoint: nope.py\n", encoding="utf-8"
        )
        reg = TemplateRegistry(tmp_path).load()
        assert any("entrypoint not found" in e for e in reg.validate())


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


def _project(tmp_path):
    return Store.init(tmp_path, "audit-test")


class TestAuditModel:
    def test_oat_without_invariant_is_an_error(self, tmp_path):
        st = _project(tmp_path)
        st.save_experiment(
            Experiment(
                id="EXP-01",
                kind=ExperimentKind.SENSITIVITY_OAT,
                varied=[Varied(name="a", values=[1, 2])],
            )
        )
        rep = audit_project(st)
        assert any(f.code == "OAT_NO_INVARIANT" for f in rep.errors)

    def test_symbol_two_meanings_is_an_error(self, tmp_path):
        """同一个符号两种含义 = 读者会被误导，是硬伤。

        原来这是"跨模型符号冲突"（跨模型所以只算警告）。模型层拆掉后
        变成项目级的"符号重定义" —— 一篇论文只有一张符号表，
        所以升级为 error。
        """
        st = _project(tmp_path)
        content = MathContent(symbols=[
            Symbol(id="S1", glyph="gamma", meaning="boredom"),
            Symbol(id="S2", glyph="gamma", meaning="risk aversion"),
        ])
        st.math.save(content)
        rep = audit_project(st)
        assert any(f.code == "SYMBOL_REDEFINED" for f in rep.errors)

    def test_same_glyph_same_meaning_is_a_merge_warning(self, tmp_path):
        """含义相同的重复符号只提醒合并，不算错误。"""
        st = _project(tmp_path)
        st.math.save(MathContent(symbols=[
            Symbol(id="S1", glyph="t", meaning="time"),
            Symbol(id="S2", glyph="t", meaning="time"),
        ]))
        rep = audit_project(st)
        assert any(f.code == "SYMBOL_DUPLICATE" for f in rep.warnings)
        assert not any(f.code == "SYMBOL_REDEFINED" for f in rep.findings)

    def test_distinct_symbols_are_not_flagged(self, tmp_path):
        st = _project(tmp_path)
        st.math.save(MathContent(symbols=[
            Symbol(id="S1", glyph="t", meaning="time"),
            Symbol(id="S2", glyph="v", meaning="velocity"),
        ]))
        rep = audit_project(st)
        # SYMBOL_ROLES_UNSET 是 info 级提示（role 未标注很常见），
        # 不算"这个符号有问题"。
        flagged = {f.code for f in rep.findings}
        assert "SYMBOL_REDEFINED" not in flagged
        assert "SYMBOL_DUPLICATE" not in flagged

    def test_duplicate_equation_number_is_an_error(self, tmp_path):
        st = _project(tmp_path)
        st.math.save(MathContent(equations=[
            Equation(id="E1", number="5", latex="a=b"),
            Equation(id="E2", number="5", latex="c=d"),
        ]))
        rep = audit_project(st)
        assert any(f.code == "EQUATION_NUMBER_DUPLICATE" for f in rep.errors)

    def test_optimization_without_constraints_warns(self, tmp_path):
        st = _project(tmp_path)
        st.math.save(MathContent(
            objective=Objective(expressions=["max x"]),
            constraints=[],
        ))
        rep = audit_project(st)
        assert any(f.code == "OPTIMIZATION_NO_CONSTRAINTS" for f in rep.warnings)

    def test_notation_disclaimer_is_injected(self, tmp_path):
        st = _project(tmp_path)
        st.math.save(MathContent(symbols=[
            Symbol(id="S1", glyph="x", meaning="a quantity"),
        ]))
        rep = audit_project(st)
        assert any(f.code == "NOTATION_DISCLAIMER_ADDED" for f in rep.infos)

    def test_parameter_without_provenance_warns(self, tmp_path):
        """105/237 篇现代论文会标注参数来源，所以缺来源值得提醒。

        这条检查是当初保留 Parameter 的理由。
        """
        st = _project(tmp_path)
        st.params.upsert(Parameter(id="P1", name="gamma", value=0.02))
        rep = audit_project(st)
        assert any(f.code == "PARAMETER_NO_PROVENANCE" for f in rep.warnings)

    def test_parameter_with_provenance_is_clean(self, tmp_path):
        st = _project(tmp_path)
        st.params.upsert(Parameter(id="P1", name="gamma", value=0.02, source="fitted"))
        rep = audit_project(st)
        assert not any(f.code == "PARAMETER_NO_PROVENANCE" for f in rep.findings)


class TestAuditArtifacts:
    def test_binding_to_unknown_atom_is_an_error(self, tmp_path):
        st = _project(tmp_path)
        st.save_figure(Figure(id="FIG-01", bindings=[ArtifactBinding(atom_id="R99")]))
        rep = audit_project(st)
        assert any(f.code == "DANGLING_ARTIFACT_BINDING" for f in rep.errors)

    def test_uncited_figure_is_only_a_warning(self, tmp_path):
        """63% of Outstanding figures are uncited, so this must not be fatal."""
        st = _project(tmp_path)
        st.append_atoms([ResultAtom(atom_id="R1", name="x", value=1, unit="-")])
        st.save_figure(Figure(id="FIG-01", bindings=[ArtifactBinding(atom_id="R1")]))
        rep = audit_project(st)
        assert any(f.code == "ARTIFACT_NOT_CITED" for f in rep.warnings)
        assert not any(f.code == "ARTIFACT_NOT_CITED" for f in rep.errors)

    def test_unbound_artifact_warns(self, tmp_path):
        st = _project(tmp_path)
        st.save_table(Table(id="TAB-01"))
        rep = audit_project(st)
        assert any(f.code == "ARTIFACT_UNBOUND" for f in rep.warnings)

    def test_table_bound_atoms_collected(self):
        t = Table(
            id="TAB-01",
            columns=[{"header": "RMSE", "atom_id": "R1"}],
            rows=[{"literal": "Lasso", "atom_ids": ["R2", "R3"]}],
            bindings=[ArtifactBinding(atom_id="R4")],
        )
        assert set(t.bound_atom_ids()) == {"R1", "R2", "R3", "R4"}

    def test_atom_without_condition_or_unit_warns(self, tmp_path):
        st = _project(tmp_path)
        st.append_atoms([ResultAtom(atom_id="R1", name="x", value=1)])
        rep = audit_project(st)
        assert any(f.code == "ATOM_NO_CONDITION_OR_UNIT" for f in rep.warnings)


class TestAuditPaper:
    def _paper(self, **kw):
        base = dict(
            paper_id="P1",
            summary={"problem_letter": "C", "team_control_number": "2400001"},
        )
        base.update(kw)
        return Paper(**base)

    def test_placeholder_summary_is_an_error(self, tmp_path):
        st = _project(tmp_path)
        st.save_paper(Paper())
        rep = audit_project(st)
        assert any(f.code == "SUMMARY_PLACEHOLDER" for f in rep.errors)

    def test_missing_introduction_is_an_error(self, tmp_path):
        st = _project(tmp_path)
        st.save_paper(self._paper())
        rep = audit_project(st)
        assert any(f.code == "MISSING_INTRODUCTION" for f in rep.errors)

    def test_full_spine_passes_structure_checks(self, tmp_path):
        st = _project(tmp_path)
        st.save_paper(
            self._paper(
                sections=[
                    PaperSection(id="S1", kind=SectionKind.INTRODUCTION, title="Introduction", order=10, body="x"),
                    PaperSection(id="S2", kind=SectionKind.REFERENCES, title="References", order=90, generated=True),
                ]
            )
        )
        rep = audit_project(st)
        assert not any(f.code == "MISSING_INTRODUCTION" for f in rep.errors)
        assert not any(f.code == "MISSING_REFERENCES" for f in rep.errors)
        assert not any(f.code == "SECTION_ORDER_VIOLATION" for f in rep.errors)

    def test_reversed_order_is_an_error(self, tmp_path):
        st = _project(tmp_path)
        st.save_paper(
            self._paper(
                sections=[
                    PaperSection(id="S1", kind=SectionKind.INTRODUCTION, title="Introduction", order=90, body="x"),
                    PaperSection(id="S2", kind=SectionKind.REFERENCES, title="References", order=10, generated=True),
                ]
            )
        )
        rep = audit_project(st)
        assert any(f.code == "SECTION_ORDER_VIOLATION" for f in rep.errors)

    def test_page_overrun_is_an_error(self, tmp_path):
        st = _project(tmp_path)
        st.save_paper(self._paper(build={"page_count": 27}))
        rep = audit_project(st)
        assert any(f.code == "PAGE_LIMIT_EXCEEDED" for f in rep.errors)

    def test_exactly_25_pages_is_celebrated_not_flagged(self, tmp_path):
        st = _project(tmp_path)
        st.save_paper(self._paper(build={"page_count": 25}))
        rep = audit_project(st)
        assert any(f.code == "PAGE_LIMIT_EXACT" for f in rep.infos)
        assert not any(f.code == "PAGE_LIMIT_EXCEEDED" for f in rep.errors)

    def test_ai_use_without_disclosure_is_an_error(self, tmp_path):
        st = _project(tmp_path)
        st.save_paper(self._paper(ai_usage={"ai_used": True}))
        rep = audit_project(st)
        assert any(f.code == "AI_USE_UNDISCLOSED" for f in rep.errors)

    def test_ai_use_with_disclosure_section_passes(self, tmp_path):
        st = _project(tmp_path)
        st.save_paper(
            self._paper(
                ai_usage={"ai_used": True},
                sections=[
                    PaperSection(id="S1", kind=SectionKind.INTRODUCTION, title="Introduction", order=10, body="x"),
                    PaperSection(id="S2", kind=SectionKind.REFERENCES, title="References", order=90, generated=True),
                    PaperSection(id="S3", kind=SectionKind.REPORT_ON_AI, title="Report on Use of AI", order=110, generated=True, enabled=True),
                ],
            )
        )
        rep = audit_project(st)
        assert not any(f.code == "AI_USE_UNDISCLOSED" for f in rep.errors)

    def test_literature_review_section_warns(self, tmp_path):
        st = _project(tmp_path)
        st.save_paper(
            self._paper(
                sections=[
                    PaperSection(id="S1", kind=SectionKind.OTHER, title="Literature Review", order=10, body="x"),
                ]
            )
        )
        rep = audit_project(st)
        assert any(f.code == "LITERATURE_REVIEW_SECTION" for f in rep.warnings)


class TestAuditEndToEnd:
    def test_a_well_formed_project_passes(self, tmp_path):
        """The acid test: a correct project must produce zero errors."""
        st = Store.init(tmp_path, "good")

        st.math.save(MathContent(symbols=[
            Symbol(id="S1", glyph="beta", meaning="participation",
                   role="parameter", unit="/"),
        ]))
        st.params.upsert(
            Parameter(id="P1", name="beta", value=0.177, source="fitted")
        )

        st.save_experiment(
            Experiment(
                id="EXP-01",
                kind=ExperimentKind.SENSITIVITY_OAT,
                varied=[Varied(name="beta", values=[0.1, 0.2])],
                held_fixed=["gamma", "lambda"],
                n_runs=1,
                aggregation="none",
            )
        )
        st.append_atoms([
            ResultAtom(atom_id="R1", name="rmse", value=0.0791, unit="/",
                       format="%.4f", condition="beta=0.1"),
        ])
        st.save_figure(
            Figure(id="FIG-01", bindings=[ArtifactBinding(atom_id="R1")],
                   referenced_in=["SEC-050"])
        )
        st.save_paper(
            Paper(
                paper_id="P1",
                summary={"problem_letter": "C", "team_control_number": "2400001"},
                sections=[
                    PaperSection(id="SEC-010", kind=SectionKind.INTRODUCTION,
                                 title="Introduction", order=10, body="Text."),
                    PaperSection(id="SEC-050", kind=SectionKind.MODEL,
                                 title="Model I", order=50, body="Text.",
                                 template_ref="M01"),
                    PaperSection(id="SEC-090", kind=SectionKind.REFERENCES,
                                 title="References", order=90, generated=True),
                ],
            )
        )
        rep = audit_project(st)
        assert rep.ok(), f"unexpected errors: {[str(f) for f in rep.errors]}"


# --------------------------------------------------------------------------
# In-place list mutation must not bypass validation
# --------------------------------------------------------------------------


class TestInPlaceMutation:
    """Regression: validate_assignment does NOT catch list.append(dict)."""

    def test_appending_a_dict_then_saving_coerces_it(self, tmp_path):
        """往列表里塞 dict，保存后读回来应当是真正的模型对象。

        这条测的是存储层的强制转换能力，与实体类型无关 ——
        模型层删掉后改用 Experiment 的 varied 来测。
        """
        st = Store.init(tmp_path, "t")
        exp = Experiment(id="EXP-01", kind=ExperimentKind.SENSITIVITY_OAT)
        exp.varied.append({"name": "beta", "values": [0.1, 0.2]})
        st.save_experiment(exp)

        back = st.load_experiment("EXP-01")
        assert isinstance(back.varied[0], Varied)
        assert back.varied[0].name == "beta"
        assert back.varied[0].values == [0.1, 0.2]

    def test_revalidate_coerces_in_place(self):
        exp = Experiment(id="EXP-01", kind=ExperimentKind.SENSITIVITY_OAT)
        exp.varied.append({"name": "gamma", "values": [1.0]})
        exp.revalidate()
        assert isinstance(exp.varied[0], Varied)
        assert exp.varied[0].name == "gamma"

    def test_saving_does_not_emit_serializer_warnings(self, tmp_path):
        import warnings

        st = Store.init(tmp_path, "t")
        exp = Experiment(id="EXP-01", kind=ExperimentKind.SENSITIVITY_OAT)
        exp.varied.append({"name": "beta", "values": [0.1]})
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            st.save_experiment(exp)

    def test_invalid_dict_in_list_still_raises_on_save(self, tmp_path):
        """强制转换不能变成夹带坏数据的后门。"""
        from pydantic import ValidationError

        st = Store.init(tmp_path, "t")
        exp = Experiment(id="EXP-01", kind=ExperimentKind.SENSITIVITY_OAT)
        exp.varied.append({"name": "beta", "values": "不是列表"})
        with pytest.raises(ValidationError):
            st.save_experiment(exp)
