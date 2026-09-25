"""FastAPI service layer.

Thin by design: every endpoint delegates to a Core function. If an endpoint
contains logic, that logic belongs in Core where the CLI can reach it too.

Three constraints from the architecture doc are enforced here:

1. **No endpoint mutates a `ResultAtom`.** Results are written only by the run
   pipeline. This is what makes the single source of truth trustworthy -- if an
   HTTP client could edit a result, the number in the paper would no longer be
   the number the experiment produced.
2. **No endpoint does long work synchronously**, except `paper/build` (bounded,
   seconds). An experiment run returns 202 + a run id.
3. **Every mutating endpoint returns the affected audit findings**, so the UI can
   show consequences immediately rather than after a refresh.

Run with:  mcm serve [--port 8420]
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .figures import FigureGenerator
from . import paperkit
from .runstore import RunStore
from .runner import ExperimentRunner, stale_artifacts
from . import version_string
from .schemas import Experiment, Figure, Table
from .state import build_overview
from .store import Store
from .validate import audit_project

# --------------------------------------------------------------------------
# Request bodies
# --------------------------------------------------------------------------


class LockRequest(BaseModel):
    problem_id: str
    team_number: Optional[str] = None


class ScaffoldRequest(BaseModel):
    """按模板补章节时，是否连已有正文也一起重置。默认不动。"""
    fill_existing: bool = False


class RunRequest(BaseModel):
    dry_run: bool = False
    seed: Optional[int] = None


class RegenerateRequest(BaseModel):
    only_stale: bool = True


class SuppressRequest(BaseModel):
    reason: str


class SectionUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None


class AIUsageRequest(BaseModel):
    """Mirrors AIUsage. The field is `ai_used`, not `used`."""

    ai_used: bool
    entries: List[Dict[str, Any]] = []


# --------------------------------------------------------------------------
# App factory
# --------------------------------------------------------------------------


def _registry():
    """加载模板注册表。每次调用都读盘 —— 模板是用户会自己加的，
    不能缓存住让新模板不出现。"""
    from .templates import TemplateRegistry, default_registry_root

    return TemplateRegistry(default_registry_root()).load_strict()


def _template_has_code(template_id: str) -> bool:
    """模板是否自带绘制代码。

    只有元数据、没有 render.py 的模板在工作台里画不出东西，
    面板要如实标出来，而不是让用户点了才发现。
    """
    from .templates import default_registry_root

    name = template_id.split(".")[-1]
    return (default_registry_root() / "figures" / name / "render.py").is_file()


def _ref_from_dict(d: Dict[str, Any]):
    """把一份字典转成 Reference，容忍多余字段。

    面板传来的东西可能带着界面用的字段（比如临时 id），
    而 schema 是 extra=forbid —— 这里先筛一遍，免得用户
    看到一句 pydantic 的英文报错。
    """
    from .schemas.paper import Reference

    allowed = set(Reference.model_fields.keys())
    return Reference(**{k: v for k, v in (d or {}).items() if k in allowed})


def _close_fig(fig) -> None:
    try:
        import matplotlib.pyplot as plt

        plt.close(fig)
    except Exception:
        pass


def _count_by_source(ps) -> Dict[str, int]:
    """按来源统计参数数量，面板上用来一眼看出哪些还是"来源未知"。"""
    out: Dict[str, int] = {}
    for param in ps.parameters:
        key = param.source.value if hasattr(param.source, "value") else str(param.source)
        out[key] = out.get(key, 0) + 1
    return out


def create_app(project_root: Path) -> FastAPI:
    """Build the app bound to one project directory.

    Binding at construction (rather than per-request) means the server cannot
    be pointed at a different project by a client, which would make the audit
    findings it reports unattributable.
    """
    root = Path(project_root).resolve()

    app = FastAPI(
        title="MCMtools",
        version=version_string(),
        description="A local, reproducible, auditable mathematical-modelling toolchain.",
    )

    def store() -> Store:
        if not (root / "project.yaml").exists():
            raise HTTPException(404, f"not an MCMtools project: {root}")
        return Store.open(root)

    def findings_payload(st: Store) -> Dict[str, Any]:
        """The affected findings, returned by every mutating endpoint."""
        report = audit_project(st)
        return {
            "verdict": report.verdict().value,
            "errors": [f.as_dict() for f in report.errors],
            "warnings": [f.as_dict() for f in report.warnings],
        }

    # ---------------------------------------------------------------- state
    @app.get("/api/state")
    def get_state() -> Dict[str, Any]:
        """The Overview payload: phase, counts, steps, blockers."""
        st = store()
        return build_overview(st, audit_project(st)).to_dict()

    @app.get("/api/project")
    def get_project() -> Dict[str, Any]:
        cfg = store().layout.load_config()
        return cfg.model_dump(by_alias=True)

    @app.post("/api/project/lock")
    def lock_problem(req: LockRequest) -> Dict[str, Any]:
        st = store()
        cfg = st.layout.load_config()
        cfg.locked_problem_id = req.problem_id
        if req.team_number:
            cfg.team_control_number = req.team_number
        from .schemas import ProjectPhase

        cfg.phase = ProjectPhase.BUILD
        st.layout.save_config(cfg)
        return {"project": cfg.model_dump(by_alias=True),
                "findings": findings_payload(st)}

    # ------------------------------------------------------------- datasets
    @app.get("/api/datasets")
    def list_datasets() -> List[Dict[str, Any]]:
        st = store()
        return [d.model_dump(by_alias=True) for d in st.list_datasets()]

    @app.get("/api/datasets/{dataset_id}")
    def get_dataset(dataset_id: str) -> Dict[str, Any]:
        st = store()
        try:
            return st.load_dataset(dataset_id).model_dump(by_alias=True)
        except FileNotFoundError:
            raise HTTPException(404, f"no dataset {dataset_id}")

    # ----------------------------------------------------- figure workbench
    @app.get("/api/templates")
    def list_templates(kind: Optional[str] = None, q: Optional[str] = None
                       ) -> List[Dict[str, Any]]:
        """可用模板清单。生图工作台靠它列出"能画哪些图"。

        q 是关键词。模板到 74 个之后，下拉框滚到眼花 ——
        用户记得"有个画分布的图"但想不起叫什么，搜索比滚动有用得多。
        """
        reg = _registry()
        if not q:
            picked = [t for t in reg.all() if not kind or t.kind == kind]
        else:
            # 先按字面搜（英文模板名、用途），再走 suggest 的中文映射。
            # 只做前者的话，用户在中文界面里搜"分布"会得到 0 条 ——
            # 模板里一个中文字都没有。两段结果去重后合并，
            # 字面命中的排在前面（精确 > 联想）。
            picked = reg.search(q, kind=kind)
            seen = {t.template_id for t in picked}
            for t in reg.suggest(q, kind=kind, limit=40):
                if t.template_id not in seen:
                    picked.append(t)
                    seen.add(t.template_id)
        out = []
        for t in picked:
            out.append({
                "template_id": t.template_id,
                "kind": t.kind,
                "purpose": reg.headline(t),
                "description": t.description,
                "observed_in": t.observed_in,
                "inputs": [{"name": i.name, "role": i.role, "type": i.type,
                            "optional": i.optional} for i in t.inputs],
                "caption_template": t.caption_template,
                "backend": getattr(t, "backend", None),
                "has_code": _template_has_code(t.template_id),
            })
        return sorted(out, key=lambda x: x["template_id"])

    @app.get("/api/templates/{template_id}")
    def get_template(template_id: str) -> Dict[str, Any]:
        from .sampledata import sample_for, snippet_for

        reg = _registry()
        t = reg.get(template_id)
        if t is None:
            raise HTTPException(404, f"没有这个模板：{template_id}")
        return {
            "template_id": t.template_id,
            "kind": t.kind,
            "purpose": t.purpose,
            # 示例数据和填写说明都由模板声明推导，不手写 ——
            # 手写的示例会在加模板时过期，用户就又面对一个空文本框。
            "sample": sample_for(t),
            "snippet": snippet_for(t),
            "evidence": t.evidence,
            "inputs": [{"name": i.name, "role": i.role, "type": i.type,
                        "optional": i.optional} for i in t.inputs],
            "defaults": t.defaults,
            "caption_template": t.caption_template,
            "has_code": _template_has_code(t.template_id),
        }

    @app.post("/api/templates/{template_id}/preview")
    def preview_template(template_id: str,
                         payload: Dict[str, Any] = Body(default={})) -> Any:
        """用给定数据即时渲染一张图，返回 PDF。

        这是生图工作台的核心动作：**先看效果再决定要不要用**。
        数据对了才绑进论文，而不是绑完才发现画出来不对。
        """
        from fastapi.responses import Response

        backend = payload.get("backend", "matplotlib")
        data = payload.get("data") or {}

        if backend == "drawio":
            # drawio 图返回可编辑源文件，不是位图。
            import tempfile

            from .figures import FigureGenerator

            st = store()
            gen = FigureGenerator(st)
            mod = gen._load_template(template_id)
            if mod is None or not hasattr(mod, "build"):
                raise HTTPException(404, f"模板 {template_id} 没有绘制代码")
            try:
                xml = mod.build(data, payload.get("meta") or {})
            except Exception as exc:
                raise HTTPException(422, f"{type(exc).__name__}: {exc}")
            return Response(
                content=xml, media_type="application/xml",
                headers={"Content-Disposition":
                         f'inline; filename="{template_id.split(".")[-1]}.drawio"'},
            )

        import io
        import tempfile

        from .figures import FigureGenerator

        st = store()
        gen = FigureGenerator(st)
        mod = gen._load_template(template_id)
        if mod is None or not hasattr(mod, "render"):
            raise HTTPException(404, f"模板 {template_id} 没有绘制代码")
        try:
            fig = mod.render(dict(data), payload.get("meta") or {})
        except Exception as exc:
            # 渲染失败是 422 加原因，让工作台把问题显示给用户。
            raise HTTPException(422, f"{type(exc).__name__}: {exc}")

        buf = io.BytesIO()
        fig.savefig(buf, format="pdf", bbox_inches="tight")
        _close_fig(fig)
        buf.seek(0)
        return Response(content=buf.read(), media_type="application/pdf")

    # ------------------------------------------------------- math & params
    # -- DIY 生图 ---------------------------------------------------------
    @app.get("/api/diy/options")
    def diy_options() -> Dict[str, Any]:
        """DIY 能选的图形类型和配色。

        前端不硬编码这些清单 —— 加一种图要同时改两处，早晚不一致。
        """
        from .diyfig import catalog
        from . import mcmplot
        return {**catalog(), "has_cjk_font": mcmplot.has_cjk()}

    @app.post("/api/diy/render")
    def diy_render(payload: Dict[str, Any] = Body(default={})) -> Any:
        """按规格即时画一张图，返回 PDF。

        和模板预览走同一条路（返回 PDF 让前端嵌进 iframe），
        用户看到的就是最终能进论文的东西。
        """
        from fastapi.responses import Response

        from .diyfig import DIYError, render

        spec = payload.get("spec") or {}
        meta = payload.get("meta") or {}
        try:
            fig = render(spec, meta)
        except DIYError as exc:
            # 规格错误是用户能改的，用 422 把中文原因原样带回去
            raise HTTPException(422, str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                422, f"画图失败：{type(exc).__name__}: {exc}")

        import io
        import matplotlib.pyplot as plt

        buf = io.BytesIO()
        try:
            fig.savefig(buf, format="pdf")
        finally:
            plt.close(fig)
        return Response(content=buf.getvalue(), media_type="application/pdf",
                        headers={"Content-Disposition":
                                 'inline; filename="diy.pdf"'})

    @app.post("/api/diy/save")
    def diy_save(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
        """把 DIY 规格存成项目里的一个图模板，之后可反复用。

        存成**模板**而不是只存一张 PDF：同一个 DIY 图往往要在多个
        实验上重复用，存规格才能改数据重用。落盘位置在
        templates/figures/ 下，和其他模板平级。
        """
        import re as _re

        import yaml as _yaml

        from .diyfig import CATEGORICAL, CHART_TYPES, MATRIX_TYPES, render
        from .templates import default_registry_root

        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(422, "要给这张图起个名字。")
        # 目录名只允许字母数字下划线，避免路径穿越
        slug = _re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
        if not slug:
            raise HTTPException(422, "名字里要有字母或数字，例如 peak_curve。")

        spec = payload.get("spec") or {}
        try:
            fig = render(spec, payload.get("meta") or {})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, f"这张图画不出来，先修好再保存：{exc}")

        import matplotlib.pyplot as plt
        plt.close(fig)

        kinds = {k for k, _ in CHART_TYPES}
        chart = spec.get("chart") or "line"
        out_dir = (default_registry_root() / "figures" / f"diy_{slug}")
        out_dir.mkdir(parents=True, exist_ok=True)

        inputs = [{"name": "y", "role": "metric", "type": "array",
                   "optional": False, "description": "主数据序列"}]
        if chart in MATRIX_TYPES:
            inputs = [{"name": "matrix", "role": "matrix", "type": "matrix",
                       "optional": False, "description": "二维数值矩阵"}]
        elif chart in CATEGORICAL:
            inputs = [{"name": "y", "role": "metric", "type": "array",
                       "optional": False, "description": "各分类的数值"},
                      {"name": "labels", "role": "labels", "type": "array",
                       "optional": True, "description": "各分类的名称"}]

        doc = {
            "template_id": f"fig.diy_{slug}",
            "kind": "figure",
            "version": "1.0.0",
            "purpose": spec.get("title") or f"Custom figure: {name}",
            "purpose_cn": f"自定图：{spec.get('title') or name}",
            "observed_in": "panel: created from the DIY builder",
            "inputs": inputs,
            # 渲染入口靠 render.py 文件本身存在来识别（_template_has_code），
            # 不需要也不能在 YAML 里声明 —— schema 是 extra=forbid，
            # 写一个不存在的键会让整个模板加载失败。
            "backend": "matplotlib",
            "defaults": {"spec": spec},
        }
        (out_dir / "template.yaml").write_text(
            _yaml.safe_dump(doc, allow_unicode=True, sort_keys=False,
                            default_flow_style=False, width=100),
            encoding="utf-8")

        # 渲染代码：把规格写死进模板，数据仍从 data 参数来。
        # 这样它就是一个正常的模板，能被预览、能绑实验、能进论文。
        import json as _json

        # 生成的模板文件内容。用列表拼行，避免长字符串里的引号
        # 和转义互相打架 —— 这里踩过一次，整个 api.py 直接语法错误。
        render_src = "\n".join([
            '"""由面板 DIY 生成。要改样式就在面板里重新保存。"""',
            "from __future__ import annotations",
            "",
            "import os",
            "import sys",
            "from typing import Any, Dict, Optional",
            "",
            "sys.path.insert(0, os.path.join(",
            "    os.path.dirname(os.path.abspath(__file__)),",
            "    '..', '..', '..', 'core'))",
            "",
            "from mcmcore.diyfig import render as _render",
            "",
            "_SPEC = " + _json.dumps(spec, ensure_ascii=False, indent=4),
            "",
            "",
            "def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):",
            "    \"\"\"数据由调用方给，样式沿用保存时的规格。\"\"\"",
            "    meta = dict(meta or {})",
            "    merged = dict(_SPEC)",
            "    for k in ('x', 'y', 'series', 'labels', 'matrix', 'z',",
            "              'errors', 'values'):",
            "        merged.pop(k, None)",
            "    merged.update({k: v for k, v in (data or {}).items()",
            "                   if k in ('x', 'y', 'series', 'labels', 'matrix',",
            "                           'z', 'errors', 'values')})",
            "    return _render(merged, meta)",
            "",
        ])
        (out_dir / "render.py").write_text(render_src, encoding="utf-8")

        return {"saved": f"fig.diy_{slug}", "path": str(out_dir),
                "findings": findings_payload(store())}

    @app.get("/api/math")
    def get_math() -> Dict[str, Any]:
        """符号表、公式、假设 —— 项目级数学内容。"""
        content = store().math.load()
        return {
            **content.model_dump(by_alias=True),
            "summary": content.summary(),
            "duplicate_glyphs": content.duplicate_glyphs(),
            "duplicate_equation_numbers": content.duplicate_equation_numbers(),
        }

    @app.put("/api/math/symbols/{symbol_id}")
    def put_symbol(symbol_id: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """新增或更新一个符号。"""
        from .schemas.model import Symbol

        st = store()
        payload.pop("id", None)
        existing = st.math.load().symbol_by_glyph(symbol_id)
        base = existing.model_dump() if existing else {}
        try:
            sym = Symbol(**{**base, **payload, "id": symbol_id})
        except Exception as exc:
            raise HTTPException(422, str(exc))
        st.math.upsert_symbol(sym)
        return {"symbol": sym.model_dump(by_alias=True),
                "findings": findings_payload(st)}

    @app.delete("/api/math/symbols/{symbol_id}")
    def delete_symbol(symbol_id: str) -> Dict[str, Any]:
        st = store()
        st.math.remove_symbol(symbol_id)
        return {"removed": symbol_id, "findings": findings_payload(st)}

    @app.put("/api/math/assumptions/{assumption_id}")
    def put_assumption(assumption_id: str,
                       payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """新增或更新一条假设。

        假设是评审最爱挑的地方，必须能在面板里直接改 ——
        否则用户就得去翻 math/math.yaml，那正是"改起来很麻烦"的来源。
        """
        from .schemas.model import Assumption

        st = store()
        payload.pop("id", None)
        existing = None
        for a in st.math.load().assumptions:
            if a.id == assumption_id:
                existing = a
                break
        base = existing.model_dump() if existing else {}
        try:
            asm = Assumption(**{**base, **payload, "id": assumption_id})
        except Exception as exc:
            raise HTTPException(422, str(exc))
        st.math.upsert_assumption(asm)
        return {"assumption": asm.model_dump(by_alias=True),
                "findings": findings_payload(st)}

    @app.delete("/api/math/assumptions/{assumption_id}")
    def delete_assumption(assumption_id: str) -> Dict[str, Any]:
        st = store()
        content = st.math.load()
        before = len(content.assumptions)
        content.assumptions = [a for a in content.assumptions
                               if a.id != assumption_id]
        if len(content.assumptions) == before:
            raise HTTPException(404, f"没有这条假设：{assumption_id}")
        st.math.save(content)
        return {"removed": assumption_id, "findings": findings_payload(st)}

    @app.delete("/api/math/equations/{equation_id}")
    def delete_equation(equation_id: str) -> Dict[str, Any]:
        """删一个公式。

        原来只有 PUT 没有 DELETE，用户建错了公式只能自己改 YAML。
        """
        st = store()
        content = st.math.load()
        before = len(content.equations)
        content.equations = [e for e in content.equations
                             if e.id != equation_id]
        if len(content.equations) == before:
            raise HTTPException(404, f"没有这个公式：{equation_id}")
        st.math.save(content)
        return {"removed": equation_id, "findings": findings_payload(st)}

    @app.put("/api/math/equations/{equation_id}")
    def put_equation(equation_id: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        from .schemas.model import Equation

        st = store()
        payload.pop("id", None)
        try:
            eq = Equation(**{**payload, "id": equation_id})
        except Exception as exc:
            raise HTTPException(422, str(exc))
        st.math.upsert_equation(eq)
        return {"equation": eq.model_dump(by_alias=True),
                "findings": findings_payload(st)}

    @app.get("/api/params")
    def get_params() -> Dict[str, Any]:
        """参数表 —— 每个数值从哪来。"""
        ps = store().params.load()
        return {
            **ps.model_dump(by_alias=True),
            "summary": {
                "total": len(ps.parameters),
                "unresolved": ps.unresolved(),
                "by_source": _count_by_source(ps),
            },
        }

    @app.put("/api/params/{name}")
    def put_param(name: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """按名字新增或更新一个参数。

        按**名字**而不是 id 定位：用户想的是 "gamma 是多少"，
        不是一个内部 id。
        """
        from .schemas.model import Parameter, ParameterSource

        st = store()
        existing = st.params.load().by_name().get(name)
        merged = dict(existing.model_dump() if existing else {})
        merged.update(payload)
        merged["name"] = name
        # id 由名字推导。用户在面板上想的是"加一个叫 beta 的参数"，
        # 不该被迫再编一个内部 id —— 之前漏了这步，新建参数必定 422。
        merged.setdefault("id", f"param:{name}")
        if not merged.get("id"):
            merged["id"] = f"param:{name}"
        # source 允许传字符串，转成枚举；传错值时给出中文提示。
        src = merged.get("source", "unknown")
        try:
            merged["source"] = ParameterSource(src)
        except ValueError:
            allowed = ", ".join(s.value for s in ParameterSource)
            raise HTTPException(
                422, f"参数来源 '{src}' 无效，只能是：{allowed}"
            )
        try:
            param = Parameter(**merged)
        except Exception as exc:
            raise HTTPException(422, str(exc))
        st.params.upsert(param)
        return {"params": st.params.load().model_dump(by_alias=True),
                "findings": findings_payload(st)}

    @app.delete("/api/params/{name}")
    def delete_param(name: str) -> Dict[str, Any]:
        st = store()
        st.params.remove(name)
        return {"removed": name, "findings": findings_payload(st)}

    @app.get("/api/notations")
    def get_notations() -> Dict[str, Any]:
        """论文符号表的视图。符号表是符号的**视图**，不手写。

        `exhaustive` 恒为 False：语料里 56% 的论文有符号表，
        且每一篇都声明它不穷尽。
        """
        content = store().math.load()
        rows = [
            {"symbol": s.glyph, "meaning": s.meaning, "unit": s.unit or "—"}
            for s in content.symbols
        ]
        return {
            "exhaustive": False,
            "disclaimer": content.notation_table.disclaimer
            or "There are some variables that are not listed here and will be "
               "discussed in detail in each section.",
            "count": len(rows),
            "rows": rows,
        }

    # ---------------------------------------------------------- experiments
    @app.get("/api/experiments")
    def list_experiments() -> List[Dict[str, Any]]:
        return [e.model_dump(by_alias=True) for e in store().list_experiments()]

    @app.get("/api/runs")
    def list_runs(experiment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """所有运行记录，按实验分组、按运行号升序。

        运行号是顺序编号，所以排序不需要看时间戳 —— 时钟被调整也不会乱。
        """
        return RunStore(store().root).list_runs(experiment_id)

    @app.get("/api/runs/summary")
    def runs_summary() -> Dict[str, Any]:
        """每个实验跑了多少次、最近一次什么状态、产出几个文件。"""
        rs = RunStore(store().root)
        data = rs.summary()
        data["stale_runs"] = rs.staleness(store().root)
        return data

    @app.get("/api/experiments/{exp_id}")
    def get_experiment(exp_id: str) -> Dict[str, Any]:
        st = store()
        try:
            exp = st.load_experiment(exp_id)
        except FileNotFoundError:
            raise HTTPException(404, f"no experiment {exp_id}")
        return exp.model_dump(by_alias=True)

    @app.post("/api/experiments/{exp_id}/run", status_code=202)
    def run_experiment(exp_id: str, req: RunRequest = Body(default=RunRequest())):
        """Execute a protocol.

        A dry run is fast and synchronous: it expands the protocol and returns
        the trials without executing. A real run executes synchronously too --
        a competition sweep is seconds, not minutes -- but reports the outcome
        per trial so the caller sees exactly what failed.
        """
        st = store()
        try:
            st.load_experiment(exp_id)
        except FileNotFoundError:
            raise HTTPException(404, f"no experiment {exp_id}")

        runner = ExperimentRunner(st, seed=req.seed)
        out = runner.run(exp_id, dry_run=req.dry_run)
        if not out.ok:
            raise HTTPException(422, out.error or "experiment failed")

        return {
            "experiment_id": exp_id,
            "dry_run": req.dry_run,
            "runs": [r.model_dump(by_alias=True) for r in out.runs],
            "atoms": [a.model_dump(by_alias=True) for a in out.atoms],
            "changed_atoms": out.changed,
            "stale": {
                "figures": out.stale.stale_figures if out.stale else [],
                "tables": out.stale.stale_tables if out.stale else [],
            },
            "messages": out.messages,
            "findings": findings_payload(st) if not req.dry_run else None,
        }

    @app.get("/api/experiments/{exp_id}/trials")
    def experiment_trials(exp_id: str) -> List[Dict[str, Any]]:
        """The concrete trials a protocol expands to, without executing."""
        st = store()
        try:
            exp = st.load_experiment(exp_id)
        except FileNotFoundError:
            raise HTTPException(404, f"no experiment {exp_id}")
        from .runner import condition_string, expand_trials

        names = [v.name for v in exp.varied]
        return [
            {
                "index": i,
                "parameters": t,
                "condition": condition_string(t, names, exp.held_fixed),
            }
            for i, t in enumerate(expand_trials(exp, st.params.load().parameters), start=1)
        ]

    @app.get("/api/experiments/{exp_id}/runs")
    def experiment_runs(exp_id: str) -> List[Dict[str, Any]]:
        return [
            r.model_dump(by_alias=True)
            for r in store().load_runs()
            if r.experiment_id == exp_id
        ]

    @app.get("/api/experiments/{exp_id}/results")
    def experiment_results(exp_id: str) -> List[Dict[str, Any]]:
        return [
            a.model_dump(by_alias=True)
            for a in store().load_atoms()
            if a.experiment_id == exp_id
        ]

    # -------------------------------------------------------------- results
    @app.get("/api/results")
    def list_results(
        experiment_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        atoms = store().load_atoms()
        if experiment_id:
            atoms = [a for a in atoms if a.experiment_id == experiment_id]
        if name:
            atoms = [a for a in atoms if a.name == name]
        return [a.model_dump(by_alias=True) for a in atoms]

    @app.get("/api/results/{atom_id}")
    def get_result(atom_id: str) -> Dict[str, Any]:
        for a in store().load_atoms():
            if a.atom_id == atom_id:
                return a.model_dump(by_alias=True)
        raise HTTPException(404, f"no result atom {atom_id}")

    # ------------------------------------------------------------ artifacts
    @app.get("/api/figures")
    def list_figures() -> List[Dict[str, Any]]:
        return [f.model_dump(by_alias=True) for f in store().list_figures()]

    @app.get("/api/figures/stale")
    def list_stale() -> Dict[str, Any]:
        figs, tabs = stale_artifacts(store())
        return {
            "figures": [f.model_dump(by_alias=True) for f in figs],
            "tables": [t.model_dump(by_alias=True) for t in tabs],
        }

    @app.get("/api/figures/{figure_id}/file")
    def figure_file(figure_id: str):
        """Serve the generated figure so the panel can display it.

        Figures are vector PDFs. The panel renders them in an <embed>, which
        keeps them crisp at any zoom -- the corpus shows 74% of embedded images
        are low-resolution screenshots, so the toolchain must not repeat that
        mistake by rasterising its own output for preview.
        """
        st = store()
        try:
            fig = st.load_figure(figure_id)
        except FileNotFoundError:
            raise HTTPException(404, f"no figure {figure_id}")
        if not fig.file:
            raise HTTPException(404, f"figure {figure_id} has no generated file")
        path = (st.root / fig.file).resolve()
        if not path.exists():
            raise HTTPException(404, f"figure file missing: {fig.file}")
        # Never serve outside the project directory.
        if st.root.resolve() not in path.parents:
            raise HTTPException(403, "figure path escapes the project directory")
        media = "application/pdf" if path.suffix == ".pdf" else "image/png"
        return FileResponse(path, media_type=media)

    @app.post("/api/figures/{figure_id}/regenerate")
    def regenerate_figure(
        figure_id: str, req: RegenerateRequest = Body(default=RegenerateRequest())
    ) -> Dict[str, Any]:
        st = store()
        try:
            st.load_figure(figure_id)
        except FileNotFoundError:
            raise HTTPException(404, f"no figure {figure_id}")
        gen = FigureGenerator(st)
        done = gen.regenerate(figure_ids=[figure_id], only_stale=req.only_stale)
        figs, tabs = stale_artifacts(st)
        return {
            "regenerated": done,
            "warnings": gen.warnings,
            "still_stale": [f.id for f in figs] + [t.id for t in tabs],
            "findings": findings_payload(st),
        }

    @app.get("/api/tables")
    def list_tables() -> List[Dict[str, Any]]:
        return [t.model_dump(by_alias=True) for t in store().list_tables()]

    @app.get("/api/tables/{table_id}/source")
    def table_source(table_id: str) -> Dict[str, Any]:
        """The generated LaTeX for a table, so the panel can show its content.

        There is no HTML table renderer: the table's real form is LaTeX, and a
        half-faithful HTML preview would show columns that the PDF does not
        have. Showing the source is honest.
        """
        st = store()
        try:
            st.load_table(table_id)
        except FileNotFoundError:
            raise HTTPException(404, f"no table {table_id}")
        path = st.root / "build" / "tables" / f"{table_id}.tex"
        if not path.exists():
            return {"table_id": table_id, "source": None,
                    "note": "not built yet; run POST /api/paper/build"}
        return {"table_id": table_id, "source": path.read_text(encoding="utf-8")}

    # ---------------------------------------------------------------- paper
    @app.get("/api/paper")
    def get_paper() -> Dict[str, Any]:
        return store().load_paper().model_dump(by_alias=True)

    # -- 参考文献 ---------------------------------------------------------
    @app.get("/api/references")
    def list_references() -> Dict[str, Any]:
        """参考文献列表 + 交叉核对结果。

        核对是重点：引了但没条目（编译成 [?]）、有条目但没引
        （语料 707/707 都被引过）—— 这两类错人眼很难查。
        """
        from .citations import ENTRY_TYPES, check_entries, cross_check, guidance

        st = store()
        refs = st.load_references()
        entries = [r.model_dump() for r in refs]
        paper = st.load_paper()
        prose = "\n".join(
            (sec.body or "") for sec in paper.sections
            if getattr(sec, "body", None))
        cross = cross_check(entries, prose)
        return {
            "references": entries,
            "count": len(entries),
            "problems": check_entries(entries),
            "cross_check": cross,
            "entry_types": [{"value": k, "label": v}
                            for k, v in ENTRY_TYPES.items()],
            "guidance": guidance(),
        }

    @app.post("/api/references/import")
    def import_references(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
        """粘贴 BibTeX 导入。

        比赛期间从期刊页或 Google Scholar 复制 BibTeX 是标准动作，
        让人手填 YAML 字段是不现实的。
        """
        from .citations import check_entries, parse_bibtex

        raw = payload.get("bibtex") or ""
        entries, warnings = parse_bibtex(raw)
        if not entries:
            raise HTTPException(
                422, "没有解析出任何文献条目。请确认粘贴的是 BibTeX 格式，"
                     "以 @article{ 或 @misc{ 开头。")

        st = store()
        existing = {r.key: r for r in st.load_references()}
        added, replaced = [], []
        for e in entries:
            key = e.get("key")
            if not key:
                continue
            if key in existing:
                replaced.append(key)
            else:
                added.append(key)
            existing[key] = _ref_from_dict(e)

        # 按 key 排序后落盘，让文件稳定、diff 可读
        st.save_references([existing[k] for k in sorted(existing)])
        return {
            "added": added, "replaced": replaced,
            "warnings": warnings,
            "problems": check_entries(
                [r.model_dump() for r in st.load_references()]),
            "count": len(existing),
        }

    @app.put("/api/references/{key}")
    def put_reference(key: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        st = store()
        refs = {r.key: r for r in st.load_references()}
        base = refs[key].model_dump() if key in refs else {}
        merged = {**base, **payload}
        merged.pop("key", None)
        try:
            ref = _ref_from_dict({**merged, "key": key})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, f"这条文献填得不对：{exc}")
        refs[key] = ref
        st.save_references([refs[k] for k in sorted(refs)])
        return {"reference": ref.model_dump(),
                "findings": findings_payload(st)}

    @app.delete("/api/references/{key}")
    def delete_reference(key: str) -> Dict[str, Any]:
        st = store()
        refs = {r.key: r for r in st.load_references()}
        if key not in refs:
            raise HTTPException(404, f"没有这条文献：{key}")
        del refs[key]
        st.save_references([refs[k] for k in sorted(refs)])
        return {"removed": key, "findings": findings_payload(st)}

    @app.get("/api/references/export")
    def export_references() -> Any:
        """导出 BibTeX，方便存档或投别的期刊。"""
        from fastapi.responses import Response

        from .citations import to_bibtex

        entries = [r.model_dump() for r in store().load_references()]
        return Response(
            content=to_bibtex(entries), media_type="text/plain",
            headers={"Content-Disposition":
                     'attachment; filename="references.bib"'})

    @app.get("/api/paper/outline")
    def paper_outline() -> Dict[str, Any]:
        """章节大纲：每节的篇幅建议、自查项、待填占位符。

        这是"填空题"的题面 —— 面板拿它渲染出待办清单。
        """
        st = store()
        paper = st.load_paper()
        rows = paperkit.outline(paper)
        return {
            "sections": rows,
            "budget_pages": sum(r["budget_pages"] or 0 for r in rows if r["enabled"]),
            "pending_placeholders": sum(len(r["placeholders"]) for r in rows),
        }

    @app.post("/api/paper/scaffold")
    def paper_scaffold(req: ScaffoldRequest = Body(default=ScaffoldRequest())):
        """按模板把空章节补进论文。**不覆盖已写正文。**"""
        st = store()
        paper = st.load_paper()
        paper, report = paperkit.scaffold(paper, fill_existing=req.fill_existing)
        st.save_paper(paper)
        return report

    @app.put("/api/paper/sections/{section_id}")
    def put_section(
        section_id: str, req: SectionUpdate = Body(...)
    ) -> Dict[str, Any]:
        st = store()
        paper = st.load_paper()
        target = next((s for s in paper.sections if s.id == section_id), None)
        if target is None:
            raise HTTPException(404, f"no section {section_id}")
        for field_name, value in req.model_dump(exclude_none=True).items():
            setattr(target, field_name, value)
        st.save_paper(paper)
        return {"section": target.model_dump(by_alias=True),
                "findings": findings_payload(st)}

    @app.get("/api/paper/budget")
    def get_budget() -> Dict[str, Any]:
        st = store()
        ov = build_overview(st)
        return {
            "pages": ov.counts.get("pages"),
            "budget": ov.counts.get("page_budget"),
            "remaining": ov.counts.get("page_remaining"),
        }

    @app.post("/api/paper/build")
    def build_paper() -> Dict[str, Any]:
        """Compile synchronously: bounded, seconds, and the user is waiting."""
        st = store()
        from .compiler import PaperCompiler

        result = PaperCompiler(st).build()
        return {
            "ok": result.ok,
            "pdf": str(result.pdf_path) if result.pdf_path else None,
            "messages": result.messages,
            "pages": result.pages if hasattr(result, "pages") else None,
            "findings": findings_payload(st),
        }

    @app.post("/api/paper/ai-usage")
    def set_ai_usage(req: AIUsageRequest) -> Dict[str, Any]:
        st = store()
        paper = st.load_paper()
        paper.ai_usage.ai_used = req.ai_used
        if req.entries:
            from .schemas import AIToolEntry

            paper.ai_usage.entries = [AIToolEntry(**t) for t in req.entries]
        st.save_paper(paper)
        return {
            "ai_usage": paper.ai_usage.model_dump(by_alias=True),
            "findings": findings_payload(st),
        }

    # ---------------------------------------------------------------- audit
    @app.post("/api/audit")
    def run_audit() -> Dict[str, Any]:
        st = store()
        report = audit_project(st)
        return {
            "verdict": report.verdict().value,
            "errors": [f.as_dict() for f in report.errors],
            "warnings": [f.as_dict() for f in report.warnings],
            "infos": [f.as_dict() for f in report.infos],
            "summary": report.summary_line(),
        }

    @app.get("/api/audit/strict")
    def strict_gate() -> Dict[str, Any]:
        """The pre-submission gate: is this safe to submit right now?"""
        from .cli import STRICT_CODES

        st = store()
        report = audit_project(st)
        promoted = [f for f in report.warnings
                    if getattr(f, "code", "") in STRICT_CODES]
        ready = report.ok() and not promoted
        return {
            "ready_to_submit": ready,
            "errors": [f.as_dict() for f in report.errors],
            "promoted_warnings": [f.as_dict() for f in promoted],
            "strict_codes": sorted(STRICT_CODES),
        }

    # --------------------------------------------------------------- export
    @app.get("/api/export/pdf")
    def export_pdf():
        pdf = root / "build" / "main.pdf"
        if not pdf.exists():
            raise HTTPException(404, "no built PDF; POST /api/paper/build first")
        return FileResponse(pdf, media_type="application/pdf",
                            filename="solution.pdf")

    @app.get("/api/export/bundle")
    def export_bundle():
        """Everything a submission needs, zipped, including the audit."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            pdf = root / "build" / "main.pdf"
            if pdf.exists():
                zf.write(pdf, "solution.pdf")
            tex = root / "build" / "main.tex"
            if tex.exists():
                zf.write(tex, "latex/main.tex")
            for sub in ("figures", "tables"):
                d = root / "build" / sub
                if d.is_dir():
                    for f in sorted(d.iterdir()):
                        zf.writestr(f"latex/{sub}/{f.name}", f.read_bytes())
            report = audit_project(store())
            import json

            zf.writestr("audit.json", json.dumps(
                {"verdict": report.verdict().value,
                 "findings": report.as_dicts()}, indent=2))
            for name in ("project.yaml", "paper.yaml"):
                p = root / name
                if p.exists():
                    zf.write(p, f"project/{name}")
            zf.writestr(
                "README.txt",
                "MCMtools submission bundle.\n\n"
                "solution.pdf   the compiled paper\n"
                "latex/         the LaTeX sources and generated artifacts\n"
                "audit.json     the audit report at export time\n"
                "project/       the project definition (reproducible inputs)\n",
            )
        buf.seek(0)
        return StreamingResponse(
            buf, media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="submission.zip"'},
        )

    # ------------------------------------------------------------------- ui
    # The panel is served from the same origin as the API. That is not just
    # convenient: it means the UI cannot be pointed at a different toolchain
    # than the one whose findings it displays, and there is no CORS surface.
    web_dir = Path(__file__).resolve().parents[2] / "web"

    @app.get("/", include_in_schema=False)
    def index():
        page = web_dir / "index.html"
        if not page.exists():
            return JSONResponse(
                {"error": "panel not found", "expected": str(page),
                 "api_docs": "/docs"},
                status_code=404,
            )
        return FileResponse(page, media_type="text/html")

    @app.get("/static/{name}", include_in_schema=False)
    def static_file(name: str):
        # Resolve and verify containment so `..` cannot escape web/.
        candidate = (web_dir / name).resolve()
        if web_dir.resolve() not in candidate.parents and candidate != web_dir.resolve():
            raise HTTPException(403, "path escapes the static directory")
        if not candidate.is_file():
            raise HTTPException(404, f"no static file {name}")
        media = {".css": "text/css", ".js": "text/javascript",
                 ".html": "text/html"}.get(candidate.suffix, "text/plain")
        return FileResponse(candidate, media_type=media)

    # -------------------------------------------------------------- health
    @app.get("/api/mode")
    def get_mode() -> Dict[str, Any]:
        """Run mode and anything competition mode blocked."""
        from . import mode as mode_mod

        st = store()
        cfg = st.layout.load_config()
        status = mode_mod.mode_status()
        status["project_mode"] = getattr(cfg.mode, "value", str(cfg.mode))
        return status

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "project": str(root), "version": app.version}

    return app


def serve(
    project_root: Path,
    host: str = "127.0.0.1",
    port: int = 8420,
    quiet: bool = False,
) -> None:
    """Run the API. Binds to localhost: this tool is offline by design.

    `quiet` suppresses uvicorn's per-request access log. The launcher's banner is
    the user-facing output; a scrolling wall of `GET /api/state 200` buries it.
    Errors are still shown.
    """
    import uvicorn

    uvicorn.run(
        create_app(project_root),
        host=host,
        port=port,
        access_log=not quiet,
        log_level="warning" if quiet else "info",
    )
