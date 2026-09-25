"""实测一遍完整流程时踩出来的坑，逐个钉住。

这些都不是理论问题：每一条都真实地让一次论文编译失败，
而且报错信息指向的地方往往不是真正的原因。
"""

from __future__ import annotations

import pytest

from mcmcore.schemas import (ArtifactBinding, Figure, Paper, PaperSection,
                             ResultAtom, SectionKind)
from mcmcore.store import Store


# -- numpy 标量必须能进运行归档 --------------------------------------------


class TestNumpySerialisation:
    """科研代码里 np.mean 这类调用遍地都是，返回值是 np.float64 而不是
    float。yaml.safe_dump 不认它，而且是在**写归档时**才炸 —— 代码本身
    已经跑完了，用户会以为是归档坏了，其实是数据类型。
    """

    def test_numpy_scalar_survives_yaml_round_trip(self, tmp_path) -> None:
        import numpy as np

        from mcmcore.store import _to_plain

        assert _to_plain(np.float64(0.5)) == 0.5
        assert isinstance(_to_plain(np.float64(0.5)), float)
        assert _to_plain(np.int64(7)) == 7
        assert isinstance(_to_plain(np.int64(7)), int)

    def test_numpy_inside_nested_structures(self, tmp_path) -> None:
        import numpy as np

        from mcmcore.store import _to_plain

        got = _to_plain({"a": [np.float32(1.5), {"b": np.int32(2)}]})
        assert got == {"a": [1.5, {"b": 2}]}
        assert isinstance(got["a"][0], float)

    def test_numpy_array_of_scalars_converts(self) -> None:
        import numpy as np

        from mcmcore.store import _to_plain

        # numpy 数组本身的 .item() 会抛错（元素多于一个），
        # 列表化之后再逐个转换即可。
        got = _to_plain(list(np.array([1.0, 2.0])))
        assert got == [1.0, 2.0]

    def test_plain_python_is_untouched(self) -> None:
        from mcmcore.store import _to_plain

        assert _to_plain("abc") == "abc"          # str 也有 .item 吗？
        assert _to_plain(3) == 3
        assert _to_plain({"x": (1, 2)}) == {"x": [1, 2]}


# -- \lit{} 必须能从正文里展开 --------------------------------------------


class TestLiteralUnwrapping:
    """`\\lit{}` 是审计器的逃生口，标记"这个数字不是结果"。
    它不是 LaTeX 命令：留在正文里会导致 Undefined control sequence，
    而且**编译不出 PDF**。
    """

    def test_lit_is_unwrapped(self) -> None:
        from mcmcore.compiler.renderer import unwrap_literals

        assert unwrap_literals(r"day \lit{40} and \lit{2022}") == "day 40 and 2022"

    def test_double_escaped_lit_still_unwraps(self) -> None:
        """历史数据里出现过 \\\\lit{} 的写法，也要认。"""
        from mcmcore.compiler.renderer import unwrap_literals

        assert unwrap_literals(r"day \\lit{40}") == "day 40"

    def test_macro_names_survive_unwrapping(self) -> None:
        r"""最要紧的一条：\lit 展开不能伤到 \num...

        早先的实现用 r'\1' 当替换串，配合匹配双反斜杠的模式，
        结果把 \numRSquared 里的 \n 当成换行符吃掉，宏名变成
        "换行 + umRSquared"，正文里那一格的数字就空了。
        """
        from mcmcore.compiler.renderer import unwrap_literals

        src = r"The fit achieves $R^2 = \numRSquared{}$ at day \lit{40}."
        out = unwrap_literals(src)
        assert r"\numRSquared{}" in out
        assert "\num" not in out
        assert "\\um" not in out


# -- 绑定语义 --------------------------------------------------------------


class TestBindingKinds:
    def test_series_and_literal_are_not_dangling(self, tmp_path) -> None:
        """序列/字面绑定没有对应原子，不该被报成悬空绑定。"""
        from mcmcore.validate import audit_project

        st = Store.init(tmp_path / "proj", project_id="P1")
        st.save_figure(Figure(
            id="FIG-001", template_id="fig.pred_vs_actual",
            bindings=[
                ArtifactBinding(atom_id="SER-a", role="actual",
                                source="artifact", artifact_path="t.csv",
                                column="x"),
                ArtifactBinding(atom_id="LIT-n", role="nodes",
                                source="literal", value=[{"id": "n1"}]),
            ],
        ))
        rep = audit_project(st)
        codes = [f.code for f in rep.findings]
        assert "DANGLING_ARTIFACT_BINDING" not in codes


# -- scaffold 不能覆盖自动生成的章节 --------------------------------------


class TestScaffoldRespectsGenerated:
    """自动生成的章节（符号表、AI 报告）正文由编译器产出。
    塞模板骨架会怎样：符号表章节拿到一句 \\input{generated/notations}，
    而那个文件根本不会被生成，编译报 Undefined control sequence。
    """

    def test_generated_sections_get_no_template_body(self) -> None:
        from mcmcore.paperkit import build_sections

        by_kind = {s.kind: s for s in build_sections()}
        assert by_kind[SectionKind.NOTATIONS].generated is True
        assert by_kind[SectionKind.REPORT_ON_AI].generated is True

    def test_scaffold_does_not_write_into_generated_section(self) -> None:
        from mcmcore.paperkit import scaffold

        paper = Paper(paper_id="PAPER-001", problem_id="PROB-001")
        paper, _ = scaffold(paper)
        for s in paper.sections:
            if s.generated:
                assert not (s.body or "").strip(), (
                    f"{s.kind.value} 是自动生成的章节，不该被塞入正文"
                )

    def test_scaffold_keeps_generated_flag(self) -> None:
        from mcmcore.paperkit import scaffold

        paper, _ = scaffold(Paper(paper_id="PAPER-001", problem_id="PROB-001"))
        kinds = {s.kind for s in paper.sections if s.generated}
        assert SectionKind.NOTATIONS in kinds


# -- 宏别名 ---------------------------------------------------------------


class TestMacroAliases:
    """\\numRESEXPZeroZeroOneRTwoZeroZeroOne{} 这种名字没法写进正文。"""

    def test_alias_produces_readable_macro(self) -> None:
        from mcmcore.compiler.numbers import NumberMacros

        m = NumberMacros()
        names = m.add_atom(ResultAtom(atom_id="RES-EXP001-R2-001", name="r2",
                                      value=0.8202, macro_alias="r_squared"))
        assert names == ["numRSquared"]

    def test_alias_strips_digits_because_latex_forbids_them(self) -> None:
        """LaTeX 控制序列不能含数字：Beta020 会被削成 Beta。"""
        from mcmcore.compiler.numbers import NumberMacros

        m = NumberMacros()
        names = m.add_atom(ResultAtom(atom_id="RES-1", name="p", value=1,
                                      macro_alias="peak_day_beta020"))
        assert names[0] == "numPeakDayBeta"      # 数字被丢掉，不是崩溃

    def test_alias_collision_falls_back_to_long_name(self) -> None:
        """两个原子抢同一个别名时，第二个必须回退成长名。

        静默覆盖会让论文里某个数字悄悄变成另一个数的值 ——
        这种错误没有任何迹象。
        """
        from mcmcore.compiler.numbers import NumberMacros

        m = NumberMacros()
        first = m.add_atom(ResultAtom(atom_id="RES-AAA-001", name="a", value=1,
                                      macro_alias="rmse"))
        second = m.add_atom(ResultAtom(atom_id="RES-BBB-001", name="b", value=2,
                                       macro_alias="rmse"))
        assert first == ["numRmse"]
        assert second != ["numRmse"]
        assert m.macros["numRmse"] == "1"        # 第一个的值没被顶掉

    def test_runner_passes_alias_through(self) -> None:
        """脚本里写了 macro_alias，运行器必须传到原子上。"""
        from mcmcore.runner import _make_atom

        atom = _make_atom({"name": "r2", "value": 0.82,
                           "macro_alias": "r_squared"},
                          "RUN-001", "EXP-001", "")
        assert atom.macro_alias == "r_squared"


# -- 被换行劈开的宏引用 ------------------------------------------------------
# 这一组修的是一个真实事故：早先某次批量编辑把 `\numBeta{}` 的反斜杠
# 吃掉了，剩下的 n 和字面 \n 拼在一起，存档里变成 "\n\numBeta{}"。
# LaTeX 报一句完全不指向病灶的 "Undefined control sequence"，
# PDF 直接产不出来。修在渲染入口，这样已经写坏的存档也能自愈。


class TestSplitMacroRepair:
    def test_joined_when_split_by_newline(self) -> None:
        from mcmcore.compiler.renderer import normalise
        out = normalise("is $\\beta = \n\numBeta{}$ per day")
        assert "\\numBeta{}" in out
        # 修好之后不该再有"缺反斜杠的 umXxx"
        assert "\\numBeta{}" == out[out.index("numBeta") - 1:
                                     out.index("numBeta") + len("numBeta{}")]

    def test_bare_um_prefix_is_repaired(self) -> None:
        """收换行时反斜杠被一起吞掉，只剩 umXxx。"""
        from mcmcore.compiler.renderer import normalise
        assert "\\numRZero{}" in normalise("a umRZero{} b")

    def test_backslash_um_prefix_is_repaired(self) -> None:
        from mcmcore.compiler.renderer import normalise
        assert "\\numRZero{}" in normalise("a \\umRZero{} b")

    def test_valid_macros_are_left_alone(self) -> None:
        """不能误伤 —— 正常的宏必须原样保留。"""
        from mcmcore.compiler.renderer import normalise
        for good in ["\\numBetaFit{}", "\\numBetaBetaZeroFourFive{}",
                     "\\numRSquaredFit{}", "\\numPeakDay"]:
            assert good in normalise(good), good

    def test_plain_text_untouched(self) -> None:
        from mcmcore.compiler.renderer import normalise
        assert normalise("just some words") == "just some words"

    def test_newline_inside_inline_math_is_folded(self) -> None:
        r"""行内数学不能跨空行，TeX 会报一句误导的话。"""
        from mcmcore.compiler.renderer import normalise
        out = normalise("value $\\beta = \n\numBetaFit{}$ end")
        assert "\n" not in out
        assert "\\numBetaFit{}" in out

    def test_math_outside_newlines_are_kept(self) -> None:
        """数学之外的换行是段落结构，必须保留。"""
        from mcmcore.compiler.renderer import normalise
        out = normalise("first line\n\nsecond line")
        assert "\n\n" in out
