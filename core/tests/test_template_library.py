"""模板库自身的约束。

模板库的价值全在"能直接用"：一个坏的 template.yaml 会让面板下拉框
里多一个选了就报错的选项，而用户不知道是模板坏了还是自己填错了。
这些测试把"坏模板进不来"钉死。
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

from mcmcore.paperkit import (SPINE_TEMPLATES, available_spines,
                              build_sections, load_spine)
from mcmcore.schemas import SectionKind
from mcmcore.templates import (TEMPLATE_KINDS, TemplateRegistry,
                               default_registry_root)

ROOT = default_registry_root()
FIGDIR = ROOT / "figures"


@pytest.fixture(scope="module")
def registry() -> TemplateRegistry:
    return TemplateRegistry(ROOT).load()


# -- 注册表健康 ------------------------------------------------------------


class TestRegistryHealth:
    def test_every_template_loads(self, registry) -> None:
        assert registry.errors == [], f"有模板加载失败：{registry.errors}"

    def test_validate_is_clean(self, registry) -> None:
        assert registry.validate() == []

    def test_kinds_are_known(self, registry) -> None:
        for t in registry.all():
            assert t.kind in TEMPLATE_KINDS, f"{t.template_id} 的 kind 非法"

    def test_ids_are_unique_and_namespaced(self, registry) -> None:
        seen = set()
        for t in registry.all():
            assert t.template_id not in seen
            seen.add(t.template_id)
            # id 必须带命名空间前缀，面板按它分组显示。
            # experiment 用 exp. 而不是 experiment.（历史约定，短且够用），
            # 所以这里只要求"有点号前缀"，不要求与 kind 字面相等。
            assert "." in t.template_id, t.template_id

    def test_every_template_has_a_headline(self, registry) -> None:
        """没有用途说明的模板在面板里就是一串 id，用户没法选。"""
        for t in registry.all():
            assert registry.headline(t), f"{t.template_id} 缺用途说明"

    def test_every_template_is_corpus_grounded(self, registry) -> None:
        """每个模板都要说清为什么存在。凭想象加的模板会污染整个库。"""
        for t in registry.all():
            assert t.observed_in, f"{t.template_id} 缺 observed_in"
            assert t.evidence, f"{t.template_id} 缺 evidence"

    def test_required_inputs_are_all_declared(self, registry) -> None:
        """required_inputs 里的名字必须都在 inputs 里声明过。

        注意 required_inputs 的语义是"这张图要用到哪些输入"，
        **不是**"哪些必填"（必填由 inputs[].optional 表示）。
        真正的错误是列了一个从没声明的名字 —— 那样绑定界面会提示
        用户去填一个不存在的字段。convergence_study 就真犯过这个错，
        它 required_inputs 写了 max_iterations，而输入的其实是
        varied / held_fixed。

        只查 figure/table：experiment 模板的 required_inputs 指的是
        "运行参数"（如 n_folds），那些参数放在 defaults 里，本来就不该
        出现在 inputs 中 —— 两类模板形状不同。
        """
        for t in registry.all():
            if t.kind not in ("figure", "table"):
                continue
            declared = {i.name for i in t.inputs}
            stated = set((t.requires.required_inputs if t.requires else []) or [])
            unknown = stated - declared
            assert not unknown, (
                f"{t.template_id}: required_inputs 里的 {sorted(unknown)} "
                f"没有在 inputs 里声明（已声明：{sorted(declared)}）"
            )

    def test_mandatory_inputs_are_listed_as_required(self, registry) -> None:
        """反过来也要成立：标了 optional=false 的输入必须出现在
        required_inputs 里，否则绑定界面不会提示它，用户漏填后
        渲染才报错。"""
        for t in registry.all():
            if t.kind not in ("figure", "table"):
                continue
            mandatory = {i.name for i in t.inputs if not i.optional}
            stated = set((t.requires.required_inputs if t.requires else []) or [])
            missing = mandatory - stated
            assert not missing, (
                f"{t.template_id}: {sorted(missing)} 是必填却不在 "
                f"required_inputs 里"
            )


# -- 图模板的代码质量 ------------------------------------------------------


class TestFigureTemplates:
    def test_every_figure_has_render_code(self) -> None:
        for d in sorted(FIGDIR.iterdir()):
            if not d.is_dir() or not (d / "template.yaml").is_file():
                continue
            assert (d / "render.py").is_file(), f"{d.name} 缺 render.py"

    def test_render_entrypoint_exists(self) -> None:
        """每个模板都要有可调用的入口。

        数据图走 `render(data, meta) -> Figure`。
        结构图（流程图、模型结构图）走 drawio，入口是
        `build(...)` + `render_to_file(...)` —— 它们产出的是可编辑的
        .drawio 源文件而不是 matplotlib 图，所以签名不同。这是设计，
        不是缺陷，但两者必须至少有一个，否则这个模板没人调得动。
        """
        for d in sorted(FIGDIR.iterdir()):
            f = d / "render.py"
            if not f.is_file():
                continue
            text = f.read_text(encoding="utf-8")
            has_render = re.search(r"^def render\(", text, re.M)
            has_build = re.search(r"^def build\(", text, re.M)
            assert has_render or has_build, (
                f"{d.name}/render.py 既没有 render() 也没有 build()"
            )

    def test_no_template_writes_files_itself(self) -> None:
        """模板不许自己 savefig。

        落盘由上层负责：上层知道该写到哪个目录、要不要记进图记录。
        模板自己写文件会绕过归档，产出"论文里没有的图"。
        """
        for d in sorted(FIGDIR.iterdir()):
            f = d / "render.py"
            if not f.is_file():
                continue
            text = f.read_text(encoding="utf-8")
            assert "savefig" not in text, f"{d.name}/render.py 自己调了 savefig"

    def test_inputs_declared_in_yaml_are_read_in_code(self) -> None:
        """YAML 里声明的必填输入，代码里必须真的读它。

        声明了不读 = 绑定界面让用户填一个没人用的值。
        """
        for d in sorted(FIGDIR.iterdir()):
            ty = d / "template.yaml"
            ry = d / "render.py"
            if not (ty.is_file() and ry.is_file()):
                continue
            tmpl = yaml.safe_load(ty.read_text(encoding="utf-8")) or {}
            required = ((tmpl.get("requires") or {}).get("required_inputs") or [])
            code = ry.read_text(encoding="utf-8")
            for name in required:
                assert f'"{name}"' in code or f"'{name}'" in code, (
                    f"{d.name}: 声明了必填输入 {name!r} 但 render.py 里没读它"
                )

    def test_missing_data_raises_chinese_valueerror(self) -> None:
        """缺数据必须抛中文 ValueError，不能画空图。

        空图看起来像"跑成功了但没结果"，比报错难查得多。
        """
        cases = sorted(
            d for d in FIGDIR.iterdir()
            if (d / "render.py").is_file() and (d / "template.yaml").is_file()
        )
        assert cases, "一个图模板都没找到"
        failed = []
        for d in cases:
            mod = _load_render(d)
            if mod is None:
                failed.append(f"{d.name}: 无法导入")
                continue
            # 结构类模板（drawio）没有 render()，跳过
            if not hasattr(mod, "render"):
                continue
            try:
                mod.render({}, {})
            except ValueError as exc:
                if not any("\u4e00" <= c <= "\u9fff" for c in str(exc)):
                    failed.append(f"{d.name}: 报错信息不是中文")
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{d.name}: 抛了 {type(exc).__name__}")
            else:
                # 结构类模板（流程图）按设计不需要数据，分开处理
                tmpl = yaml.safe_load((d / "template.yaml").read_text(encoding="utf-8"))
                req = ((tmpl.get("requires") or {}).get("required_inputs") or [])
                if req:
                    failed.append(f"{d.name}: 空数据既没报错也没画图")
        assert not failed, "图模板的错误处理有问题：\n  " + "\n  ".join(failed)


def _load_render(directory: Path):
    """导入模板的 render，共用 mcmplot。"""
    if str(FIGDIR) not in sys.path:
        sys.path.insert(0, str(FIGDIR))
    spec = importlib.util.spec_from_file_location(
        f"_tpl_{directory.name}", directory / "render.py")
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:  # noqa: BLE001
        return None
    return mod


# -- 检索 ------------------------------------------------------------------


class TestSearch:
    def test_english_search_finds_by_id(self, registry) -> None:
        hits = [t.template_id for t in registry.search("heatmap", limit=3)]
        assert "fig.heatmap_matrix" in hits

    def test_kind_filter_is_respected(self, registry) -> None:
        for t in registry.search("sensitivity", kind="experiment"):
            assert t.kind == "experiment"

    def test_chinese_need_maps_to_template(self, registry) -> None:
        """用户写中文，模板是英文。映射表断了中文用户就搜不到东西。"""
        for need, want in [
            ("画个热力图", "fig.heatmap_matrix"),
            ("我要做敏感性分析", None),      # 只要求有结果
            ("展示时间趋势", "fig.timeseries"),
        ]:
            hits = [t.template_id for t in registry.suggest(need, limit=5)]
            assert hits, f"{need!r} 一条都没搜到"
            if want:
                assert want in hits, f"{need!r} 没命中 {want}，得到 {hits}"

    def test_search_is_stable(self, registry) -> None:
        """同样的查询必须给同样的顺序，否则面板每次刷新都在跳。"""
        a = [t.template_id for t in registry.search("distribution", limit=5)]
        b = [t.template_id for t in registry.search("distribution", limit=5)]
        assert a == b

    def test_empty_query_returns_nothing(self, registry) -> None:
        assert registry.search("") == []
        assert registry.search("   ") == []


# -- 题型骨架 --------------------------------------------------------------


class TestSpines:
    def test_all_five_spines_available(self) -> None:
        got = available_spines()
        for name in ["general", "data_driven", "physical", "policy", "evaluation"]:
            assert name in got, f"缺少骨架 {name}"

    def test_unknown_spine_falls_back_instead_of_crashing(self) -> None:
        assert load_spine("nonexistent") == load_spine("general")

    def test_every_spine_uses_valid_section_kinds(self) -> None:
        """骨架里的 kind 必须是合法 SectionKind。

        写错的后果：那一节静默降级成 OTHER，标题照常显示、
        正文骨架匹配不上，用户看到一节空的却不知道为什么。
        """
        valid = {k.value for k in SectionKind}
        for name in available_spines():
            for item in load_spine(name):
                assert item.get("kind") in valid, (
                    f"骨架 {name} 的 kind={item.get('kind')!r} 不是合法 SectionKind"
                )

    def test_every_spine_starts_with_introduction(self) -> None:
        """语料里 Introduction 在 71.1% 的论文中排第一，且是 100% 前置关系。"""
        for name in available_spines():
            first = load_spine(name)[0]
            assert first["kind"] == "introduction", f"{name} 没从引言开始"

    def test_conclusion_precedes_references(self) -> None:
        """CONC->REF 是语料里 100% 成立的前置关系。"""
        for name in available_spines():
            kinds = [s["kind"] for s in load_spine(name)]
            assert kinds.index("conclusion") < kinds.index("references")

    def test_no_literature_review_section(self) -> None:
        """Literature Review 在 415 篇语料里出现 0 次，不该进模板。"""
        for name in available_spines():
            for item in load_spine(name):
                title = (item.get("title") or "").lower()
                assert "literature" not in title

    def test_orders_are_unique(self) -> None:
        for name in available_spines():
            orders = [s["order"] for s in load_spine(name)]
            assert len(orders) == len(set(orders)), f"{name} 有重复的 order"


class TestScaffoldCompiles:
    """骨架必须能直接编译。

    这条测试是四个真实编译失败的产物：占位符花括号被吃掉、
    \\includegraphics 指向不存在的文件、骨架里写死不存在的宏、
    中文进 pdflatex。任何一个都让"新建论文"这一步直接卡住。
    """

    def test_body_has_no_bare_chinese(self) -> None:
        """能排版出去的正文里不能有中文。

        pdflatex 遇到中文直接崩。中文只允许出现在 % 注释里。
        """
        for name in available_spines():
            for sec in build_sections(name):
                if not sec.body:
                    continue
                for line in sec.body.split("\n"):
                    if line.strip().startswith("%"):
                        continue
                    assert not re.search(r"[\u4e00-\u9fff]", line), (
                        f"骨架 {name} 的 {sec.kind.value} 节正文里有裸中文："
                        f"{line.strip()[:50]}"
                    )

    def test_body_has_no_includegraphics(self) -> None:
        """骨架不能引用还不存在的图。

        新项目里没有图，\\includegraphics 必然报 File not found。
        图的放置由编译器根据 Figure 记录的引用自动完成。
        """
        for name in available_spines():
            for sec in build_sections(name):
                for line in (sec.body or "").split("\n"):
                    # % 注释会被 LaTeX 忽略，注释里提到 includegraphics
                    # 是在告诉用户"别这么写"，那是好事
                    if line.strip().startswith("%"):
                        continue
                    assert "includegraphics" not in line, (
                        f"骨架 {name} 的 {sec.kind.value} 节正文里有 "
                        f"\\includegraphics：{line.strip()[:50]}"
                    )

    def test_body_has_no_hardcoded_number_macros(self) -> None:
        """骨架不能写死 \\numXxx{}。

        宏由实验结果生成，新项目里一个都没有，编译就是
        Undefined control sequence。
        """
        for name in available_spines():
            for sec in build_sections(name):
                found = re.findall(r"\\num[A-Za-z]+\{\}", sec.body or "")
                assert not found, (
                    f"骨架 {name} 的 {sec.kind.value} 节写死了宏 {found}"
                )

    def test_unfilled_placeholders_become_visible_markers(self) -> None:
        """没填的占位符要变成能编译、看得见的标记。

        {{...}} 落进 LaTeX 会让 TeX 报完全指不到病灶的错。
        """
        from mcmcore.compiler.renderer import neutralise_placeholders

        out = neutralise_placeholders(r"text {{background}} and")
        assert "{{" not in out and "}}" not in out
        assert "background" in out, "标记里要保留占位符名，否则没法填"

    def test_placeholder_marker_preserves_command_braces(self) -> None:
        r"""占位符常常就是花括号本身。

        \includegraphics{{figure_file}} 里 {{figure_file}} 就是那个参数；
        替换成不带括号的文本会让参数消失。
        """
        from mcmcore.compiler.renderer import neutralise_placeholders

        out = neutralise_placeholders(r"\caption{{caption}}")
        assert out.startswith(r"\caption{") and out.endswith("}")

    def test_placeholder_underscore_is_escaped(self) -> None:
        """下划线在 LaTeX 里是数学专用字符，裸写会报 Missing $。"""
        from mcmcore.compiler.renderer import neutralise_placeholders

        out = neutralise_placeholders("{{prior_work_and_gap}}")
        assert r"\_" in out


# -- CLI（文档里的命令必须真的能跑）----------------------------------------


class TestTemplateCLI:
    """文档里写的命令，必须真的存在且能用。

    这不是形式检查：我在指南里写过 `mcm audit`，那个命令根本不存在 ——
    用户照着敲只会得到一句 "invalid choice"。文档即承诺。
    """

    @staticmethod
    def _run(argv):
        import subprocess
        import sys as _sys
        from pathlib import Path as _Path
        mcm = _Path(__file__).resolve().parents[1] / "mcm"
        return subprocess.run([_sys.executable, str(mcm), *argv],
                              capture_output=True, text=True)

    def test_template_list_works(self, tmp_path) -> None:
        r = self._run(["--dir", str(tmp_path), "template", "list"])
        assert r.returncode == 0, r.stderr
        assert "FIGURE" in r.stdout

    def test_kind_filter_works(self, tmp_path) -> None:
        r = self._run(["--dir", str(tmp_path), "template", "list", "--kind", "figure"])
        assert r.returncode == 0, r.stderr
        assert "MODEL" not in r.stdout

    def test_chinese_query_finds_template(self, tmp_path) -> None:
        r = self._run(["--dir", str(tmp_path), "template", "list", "-q", "分布"])
        assert r.returncode == 0, r.stderr
        assert "fig.histogram_distribution" in r.stdout

    def test_query_with_no_hits_exits_nonzero(self, tmp_path) -> None:
        """搜不到要明确失败，不能静默返回空表 —— 脚本里靠退出码判断。"""
        r = self._run(["--dir", str(tmp_path), "template", "list",
                       "-q", "zzzznotatemplate"])
        assert r.returncode != 0

    def test_template_show_works(self, tmp_path) -> None:
        r = self._run(["--dir", str(tmp_path), "template", "show", "fig.timeseries"])
        assert r.returncode == 0, r.stderr
        assert "fig.timeseries" in r.stdout

    def test_unknown_template_suggests_alternatives(self, tmp_path) -> None:
        """敲错模板名时要给候选，不能只说"没有"。"""
        r = self._run(["--dir", str(tmp_path), "template", "show", "timeseries"])
        assert r.returncode != 0
        assert "fig.timeseries" in (r.stdout + r.stderr)


# -- 每个图模板都能真的画出来 ----------------------------------------------

# 一份手工配对的最小数据。手工是有意的：自动按类型编数据会喂错形状，
# 然后 18 个模板"失败"其实全是测试自己的问题，白白浪费一轮排查。
SAMPLE_DATA = {
 'bar_comparison':      {'categories': ['A', 'B', 'C'], 'values': [1.2, 2.3, 1.8],
                         'errors': [.1, .2, .15]},
 'box_violin':          {'groups': ['A', 'A', 'A', 'B', 'B', 'B'],
                         'values': [1, 2, 3, 5, 6, 7]},
 'boxplot_grouped':     {'groups': ['A', 'A', 'B', 'B'], 'values': [1, 2, 5, 6]},
 'convergence':         {'iterations': [0, 10, 20, 30], 'objective': [10, 5, 3, 2],
                         'converged_at': 20},
 'correlation_heatmap': {'labels': ['a', 'b', 'c'],
                         'matrix': [[1, .5, -.2], [.5, 1, .1], [-.2, .1, 1]]},
 'cumulative_curve':    {'x': [1, 2, 3, 4], 'y': [1, 3, 6, 10]},
 'errorbar_series':     {'x': [1, 2, 3], 'mean': [1, 2, 3], 'std': [.1, .2, .1]},
 'gantt_schedule':      {'tasks': ['t1', 't2', 't3'], 'starts': [0, 2, 4],
                         'durations': [2, 2, 1]},
 'heatmap_matrix':      {'matrix': [[1, 2], [3, 4]], 'row_labels': ['r1', 'r2'],
                         'col_labels': ['c1', 'c2']},
 'histogram_distribution': {'values': [1, 2, 2, 3, 3, 3, 4, 4, 5]},
 'map_choropleth':      {'regions': ['A', 'B', 'C'], 'values': [1, 2, 3]},
 'network_graph':       {'nodes': ['A', 'B', 'C'], 'edges': [['A', 'B'], ['B', 'C']]},
 'pareto_frontier':     {'x': [1, 2, 3, 4, 5], 'y': [9, 7, 5, 4, 2]},
 'phase_portrait':      {'x': [1, 2, 3, 2, 1], 'y': [1, 3, 2, 1, .5],
                         't': [0, 1, 2, 3, 4]},
 'pred_vs_actual':      {'actual': [1, 2, 3, 4], 'predicted': [1.1, 1.9, 3.2, 3.8]},
 'qq_plot':             {'values': [.1, -.3, .5, -.2, .8, -.6, .3, 0, -.1, .4]},
 'radar_compare':       {'categories': ['a', 'b', 'c'], 'series': [[1, 2, 3], [3, 2, 1]],
                         'labels': ['P', 'Q']},
 'residual':            {'predicted': [1, 2, 3, 4], 'residual': [.1, -.2, .05, .3]},
 'roc_curve':           {'fpr': [0, .1, .3, 1], 'tpr': [0, .6, .85, 1]},
 'sankey_flow':         {'stages': [['A', 'B'], ['C', 'D']],
                         'flows': [[0, 0, 1, 0, 5], [0, 1, 1, 1, 3]]},
 'scatter_matrix':      {'frame': {'a': [1, 2, 3, 4], 'b': [2, 4, 5, 4]}},
 'sensitivity_line':    {'x': [.1, .2, .3], 'y': [1, 2, 3]},
 'stacked_area':        {'t': [1, 2, 3], 'values': [[1, 2, 3], [2, 2, 2]],
                         'labels': ['x', 'y']},
 'surface_3d':          {'x': [0, 1, 2], 'y': [0, 1, 2],
                         'z': [[1, 2, 3], [2, 3, 4], [3, 4, 5]]},
 'timeseries':          {'t': [1, 2, 3, 4], 'y': [1, 3, 2, 4],
                         'observed': [1.1, 2.9, 2.2, 3.8]},
 'waterfall_contribution': {'labels': ['A', 'B'], 'values': [5, -3], 'base': 100},
 # -- 新增的 10 个模板 -------------------------------------------------
 # 手工配对是有意的（见本字典开头）：自动按类型编数据会喂错形状。
 # 这里每一份都满足模板声明的长度约束：categories 与 values 等长、
 # labels 等于 series 的行数、param_x/param_y 等于 scores 的列数/行数。
 'violin_split':        {'groups': ['A', 'A', 'A', 'B', 'B', 'B'],
                         'values': [1.0, 2.0, 1.5, 3.0, 4.5, 3.8]},
 'bump_chart':          {'entities': ['甲', '乙', '丙'],
                         'periods': ['2021', '2022', '2023'],
                         'ranks': [[1, 2, 3], [3, 1, 2], [2, 3, 1]]},
 'dumbbell':            {'categories': ['北京', '上海', '广东'],
                         'before': [72.0, 65.0, 58.0],
                         'after': [78.0, 61.0, 70.0]},
 'lollipop':            {'categories': ['因素A', '因素B', '因素C'],
                         'values': [8.4, 3.1, 5.6]},
 'heatmap_annotated':   {'matrix': [[50, 5, 2], [3, 42, 6], [1, 4, 38]],
                         'row_labels': ['猫', '狗', '鸟'],
                         'col_labels': ['猫', '狗', '鸟']},
 'residual_hist_qq':    {'residual': [.1, -.3, .5, -.2, .8, -.6, .3, 0,
                                      -.1, .4, -.25, .15]},
 'model_metric_radar':  {'metrics': ['准确率', '召回率', 'F1'],
                         'models': ['随机森林', '逻辑回归'],
                         'scores': [[.92, .88, .90], [.85, .81, .83]]},
 'dual_axis':           {'x': [1, 2, 3, 4], 'y_left': [10, 12, 11, 14],
                         'y_right': [0.30, 0.45, 0.40, 0.62]},
 'confidence_band':     {'x': [1, 2, 3, 4], 'mean': [5, 6, 7, 8],
                         'lower': [4, 5, 6, 7], 'upper': [6, 7, 8, 9]},
 'grid_search_surface': {'param_x': [1, 2, 4, 8, 16],
                         'param_y': [0.1, 0.2, 0.3],
                         'scores': [[3.0, 2.0, 2.5, 4.0, 5.0],
                                    [2.0, 1.5, 1.2, 3.0, 4.0],
                                    [4.0, 3.0, 2.8, 5.0, 6.0]]},
}


class TestEveryFigureRenders:
    """每个数据图模板都要能用真实数据画出一张非空 PDF。

    这是唯一能证明"模板可用"的测试。光检查文件存在、函数签名对，
    都不足以说明它画得出来 —— matplotlib 的错五花八门，
    只有真跑一遍才知道。
    """

    def test_all_data_templates_have_sample_data(self) -> None:
        """新增模板必须同时补一份测试数据，否则这里会失败。"""
        missing = []
        for d in sorted(FIGDIR.iterdir()):
            ry = d / "render.py"
            if not ry.is_file():
                continue
            if "def render(" not in ry.read_text(encoding="utf-8"):
                continue          # 结构类走 drawio
            if d.name not in SAMPLE_DATA:
                missing.append(d.name)
        assert not missing, (
            f"这些模板没有测试数据，请补进 SAMPLE_DATA：{missing}"
        )

    def test_every_template_produces_a_pdf(self, tmp_path) -> None:
        import matplotlib
        matplotlib.use("Agg")

        failures = []
        for name, data in sorted(SAMPLE_DATA.items()):
            d = FIGDIR / name
            mod = _load_render(d)
            if mod is None or not hasattr(mod, "render"):
                failures.append(f"{name}: 加载不了")
                continue
            try:
                fig = mod.render(data, {"caption": "Smoke test"})
                out = tmp_path / f"{name}.pdf"
                fig.savefig(out)
                if out.stat().st_size < 3000:
                    failures.append(f"{name}: PDF 只有 {out.stat().st_size} 字节")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: {type(exc).__name__}: {str(exc)[:60]}")
            finally:
                try:
                    import matplotlib.pyplot as plt
                    plt.close("all")
                except Exception:  # noqa: BLE001
                    pass
        assert not failures, "图模板渲染失败：\n  " + "\n  ".join(failures)
