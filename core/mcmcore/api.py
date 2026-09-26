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
    from .templates import load_registry

    return load_registry()


def _template_has_code(template_id: str) -> bool:
    """模板是否自带绘制代码。

    只有元数据、没有 render.py 的模板在工作台里画不出东西，
    面板要如实标出来，而不是让用户点了才发现。

    必须遍历全部模板根：DIY 存的模板在 ~/.mcmtools/templates 下，
    只看自带库会把它标成"没有绘制代码"，而它明明能画。
    """
    from .root import find_template_file

    name = template_id.split(".")[-1]
    return find_template_file("figures", name, "render.py") is not None


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


def _num_or_str(x: str):
    """面板里填的变动参数一律是文本，能当数字就当数字。

    实验的变动轴经常是 ``0.1, 0.5, 1.0`` 这种，全按字符串存下去的话，
    参数表里会出现 "0.1" 和 0.1 两种写法，算指纹和画图时对不上。
    """
    try:
        f = float(x)
    except (TypeError, ValueError):
        return x
    return int(f) if f.is_integer() and "." not in x else f


def _snippet_runner_source(snippet_id: str, purpose: str,
                           param_names: List[str]) -> str:
    """生成一个能直接跑的实验脚本，基于某个代码骨架。

    生成的不是骨架的副本，而是一段**适配层**：

    * 骨架是独立脚本（``main()`` + 自造模拟数据 + 把图写进临时目录），
      而实验协议要的是 ``run(trial) -> {"atoms": [...]}``；
    * 直接把骨架拷过来会因签名不对而跑不起来，用户得自己琢磨怎么接。

    所以这里给的是一份自带最小模型、结构完整的 run.py：契约是对的、
    跑得通、有结果原子，用户只要把 MODEL 那一段换成自己的模型。
    骨架 id 写在文件头，方便回头去看它的完整实现。
    """
    params_doc = "、".join(f"`{n}`" for n in param_names)
    lines = [
        f'"""由代码骨架 {snippet_id} 生成 —— 可直接运行，改 MODEL 一段即可。',
        "",
        f"骨架用途：{purpose}",
        "",
        "这个文件是一层**适配**，不是骨架的副本：实验协议要的是",
        '    def run(trial: dict) -> {"atoms": [...]}',
        "而骨架本身是独立脚本（有 main()、自己造模拟数据、把图写到临时目录），",
        "签名对不上。所以这里保留契约、内嵌一个最小模型，",
        "你把 MODEL 那一段换成自己的模型就行。",
        "",
        "要改的地方（就这三处）：",
        "  1. MODEL 段       —— 换成你的模型函数",
        "  2. load_data()    —— 换成读你自己的数据（工作目录是项目根，",
        "                       所以写 data/xxx.csv，不是 ../data/xxx.csv）",
        "  3. atoms 里的名字 —— macro_alias 决定论文里怎么写：",
        '                       macro_alias="score" 对应 \\numScore{}',
        "",
        f"协议里可用的参数：{params_doc}。",
        "没在协议里声明变动参数时，trial 就是空的。",
        "完整参考：docs/coderread.md",
        '"""',
        "from __future__ import annotations",
        "",
        "from typing import Any, Dict, List",
        "",
        "import numpy as np",
        "",
        "",
        "# --------------------------------------------------------------- MODEL",
        "# ↓↓↓ 换成你的模型 ↓↓↓",
        "def model(params: Dict[str, Any]) -> float:",
        '    """模型的输出。这里先用一个占位公式，跑得通但没意义。"""',
        '    w = float(params.get("w") or 1.0)',
        "    x = load_data()",
        "    if x.size == 0:",
        "        return 0.0",
        "    return float(np.exp(-w * float(np.mean(x))))",
        "# ↑↑↑ 换成你的模型 ↑↑↑",
        "# --------------------------------------------------------------- /MODEL",
        "",
        "",
        "def load_data() -> np.ndarray:",
        '    """你的数据。默认造一组模拟数据，保证脚本开箱能跑。',
        "",
        "    换成真数据时用相对项目根的路径 —— 运行脚本的工作目录",
        "    就是项目根目录。",
        '    """',
        '    # return np.loadtxt("data/your_data.csv", delimiter=",", skiprows=1)',
        "    rng = np.random.default_rng(0)",
        "    return rng.normal(loc=1.0, scale=0.2, size=200)",
        "",
        "",
        "def run(trial: Dict[str, Any]) -> Dict[str, Any]:",
        '    """实验入口。契约见 docs/coderread.md。',
        "",
        '    注意返回值**必须**包在 {"atoms": [...]} 里。直接返回',
        '    {"score": 0.7} 不会报错，但产生 0 个原子 —— 实验显示成功、',
        "    结果页却是空的，这是最常见的坑。",
        '    """',
        "    params = dict(trial or {})",
        "    value = model(params)",
        "",
        "    atoms: List[Dict[str, Any]] = [",
        "        {",
        '            "name": "score",',
        '            "value": value,',
        '            "macro_alias": "score",',
        '            "direction": "higher_is_better",',
        '            "unit": "",',
        "        },",
        "    ]",
        "",
        '    # 把这次的参数也记成原子：论文里要能写出"在 w=0.5 时"，',
        "    # 而这些数字同样得只有一个来源。",
        "    for name, v in params.items():",
        "        if v is None:",
        "            continue",
        "        atoms.append({",
        '            "name": f"param_{name}",',
        '            "value": v,',
        '            "macro_alias": f"param{name[:1].upper()}{name[1:]}",',
        '            "direction": "neutral",',
        "        })",
        "",
        '    return {"atoms": atoms}',
        "",
        "",
        'if __name__ == "__main__":',
        "    # 直接 `python3 run.py` 也能看到结果，不用先建协议 ——",
        "    # 调试模型时比走一遍面板快。",
        "    import json",
        "",
        "    print(json.dumps(run({}), ensure_ascii=False, indent=2))",
        "",
    ]
    return "\n".join(lines)


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

    # ------------------------------------------------------------------ 系统
    @app.get("/api/system")
    def get_system() -> Dict[str, Any]:
        """程序装在哪、模板库在哪、用的是哪个 Python。

        这个接口存在的理由很直接：打包成 .app 之后用户报的第一句话是
        "模板没了"，而这类问题的第一步永远是问"程序认为模板在哪"。
        以前没有任何地方能看到这个值，只能靠猜。现在把它显示出来。

        全部数据来自 ``root.py`` —— 和程序实际使用的路径是同一个来源，
        不是另外算一份（两份算法迟早不一致，那比不显示更糟）。
        """
        from .root import describe_paths

        info = describe_paths()
        info["project_root"] = str(root)
        # 数据目录也跟着项目走，用户要找自己导入的 CSV 时需要它。
        info["data_dir"] = str(root / "data")
        info["experiments_dir"] = str(root / "experiments")
        info["readonly"] = not _writable(info["templates_root"])
        return info

    def _writable(p: str) -> bool:
        import os as _os
        return _os.access(p, _os.W_OK)

    # -- 数据集 -----------------------------------------------------------
    @app.post("/api/datasets/import")
    def import_dataset(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """登记一份数据文件。

        面板此前让用户去命令行加数据，而那条命令根本不存在，也没有
        任何别的入口。照着提示做只会得到 "invalid choice"。这里把真正的
        入口补上：读文件本身，把行数、列、类型都查出来，而不是让用户手抄。
        """
        import csv
        import hashlib

        from .schemas import Column, Dataset, DatasetFile, DatasetSource

        st = store()
        raw = str(payload.get("path") or "").strip()
        if not raw:
            raise HTTPException(422, "要指定数据文件路径。")
        src = Path(raw).expanduser()
        if not src.is_absolute():
            # 相对路径按项目根解析，和别的命令保持一致
            src = (st.layout.root / src).resolve()
        if not src.is_file():
            raise HTTPException(404, f"找不到文件：{src}")
        if src.suffix.lower() not in (".csv", ".tsv", ".txt"):
            # 别的格式不做支持，报清楚而不是存一个读不了的记录
            raise HTTPException(
                422, f"目前只支持 CSV/TSV，收到 {src.suffix or '无扩展名'}。")

        delim = "\t" if src.suffix.lower() == ".tsv" else ","
        try:
            with src.open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh, delimiter=delim))
        except UnicodeDecodeError:
            raise HTTPException(
                422, f"{src.name} 不是 UTF-8 文本。请先转成 UTF-8 再导入。")
        if not rows:
            raise HTTPException(422, f"{src.name} 是空文件。")

        header = [str(h).strip() for h in rows[0]]
        body = rows[1:]
        if not header or not any(header):
            raise HTTPException(422, f"{src.name} 第一行不是表头。")

        def _isnum(v: str) -> bool:
            try:
                float(v)
                return True
            except (TypeError, ValueError):
                return False

        cols: List[Column] = []
        for i, name in enumerate(header):
            vals = [r[i] for r in body if i < len(r) and r[i] != ""]
            dtype = "number" if vals and all(_isnum(v) for v in vals) else "text"
            missing = sum(1 for r in body if i >= len(r) or r[i] == "")
            cols.append(Column(name=name or f"col{i + 1}", dtype=dtype,
                               missing_count=missing))

        did = (payload.get("dataset_id") or
               f"DS-{src.stem.upper().replace(' ', '_')[:24]}")
        if any(d.dataset_id == did for d in st.list_datasets()):
            raise HTTPException(409, f"数据集 {did} 已存在。换个编号。")

        digest = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
        # 来源要如实标：比赛方给的数据和网上找的数据，可信度不一样，
        # 论文里也要分别说明。默认按"比赛方提供"处理，可改。
        kind = payload.get("kind") or "competition_provided"
        if kind not in ("competition_provided", "external", "derived", "simulated"):
            raise HTTPException(
                422, f"来源类型只能是 competition_provided / external / derived / "
                     f"simulated，收到 {kind!r}。")
        ds = Dataset(
            dataset_id=did,
            name=payload.get("name") or src.name,
            stage=payload.get("stage") or "raw",
            source=DatasetSource(kind=kind, ref=str(src)),
            content_hash=digest,
            files=[DatasetFile(path=str(src), rows=len(body),
                               bytes=src.stat().st_size, content_hash=digest)],
            schema_=cols,
        )
        st.save_dataset(ds)
        return {"dataset": ds.model_dump(by_alias=True),
                "rows": len(body), "columns": [c.model_dump() for c in cols]}

    @app.delete("/api/datasets/{dataset_id}")
    def delete_dataset(dataset_id: str) -> Dict[str, Any]:
        st = store()
        try:
            path = st.layout.dataset_path(dataset_id)
        except AttributeError:
            path = st.layout.root / "datasets" / f"{dataset_id}.yaml"
        if not path.is_file():
            raise HTTPException(404, f"没有这个数据集：{dataset_id}")
        path.unlink()
        return {"removed": dataset_id}

    # -- 选题 -------------------------------------------------------------
    @app.get("/api/problems")
    def list_problems() -> List[Dict[str, Any]]:
        """候选题目清单。

        选题是流程的第一步，但面板此前只有"看一眼有没有锁定"，
        既列不出题目、也没法新建或锁定 —— 用户第一步就卡死。
        这里把缺的读接口补上。
        """
        st = store()
        return [p.model_dump(by_alias=True) for p in st.list_problems()]

    @app.post("/api/problems")
    def create_problem(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """新增一道候选题目。

        比赛时最常见的情形是"先把 A-F 六道都登记进来，边读边排除"，
        所以允许只填最少信息就建，不必一开始写全。
        """
        from .schemas import Problem

        st = store()
        letter = (payload.get("letter") or "").strip().upper()
        title = (payload.get("title") or "").strip()
        if not letter and not title:
            raise HTTPException(422, "至少要有题号（A-F）或标题，否则之后认不出是哪道题。")
        # id 用题号，天然唯一、也方便对照官方题面。已存在就报错，
        # 而不是静默覆盖 —— 覆盖会丢掉已登记的附件路径。
        pid = (payload.get("id") or f"PROB-{letter or 'X'}").strip()
        if any(p.id == pid for p in st.list_problems()):
            raise HTTPException(409, f"题目 {pid} 已存在。换个题号，或直接编辑那一条。")

        try:
            prob = Problem(
                id=pid, letter=letter or None, title=title or None,
                year=payload.get("year"),
                statement_path=payload.get("statement_path") or None,
                summary=payload.get("summary") or None,
                status=(payload.get("status") or "candidate"),
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, f"这道题填得不对：{exc}")
        st.save_problem(prob)
        return {"problem": prob.model_dump(by_alias=True),
                "problems": [p.model_dump(by_alias=True)
                             for p in st.list_problems()]}

    @app.put("/api/problems/{problem_id}")
    def update_problem(problem_id: str,
                       payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        from .schemas import Problem

        st = store()
        existing = {p.id: p for p in st.list_problems()}
        if problem_id not in existing:
            raise HTTPException(404, f"没有这道题：{problem_id}")
        base = existing[problem_id].model_dump()
        merged = {**base, **payload, "id": problem_id}
        allowed = set(Problem.model_fields.keys())
        try:
            prob = Problem(**{k: v for k, v in merged.items() if k in allowed})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, f"这道题填得不对：{exc}")
        st.save_problem(prob)
        return {"problem": prob.model_dump(by_alias=True)}

    @app.delete("/api/problems/{problem_id}")
    def delete_problem(problem_id: str) -> Dict[str, Any]:
        st = store()
        path = st.layout.problem_path(problem_id)
        if not path.is_file():
            raise HTTPException(404, f"没有这道题：{problem_id}")
        cfg = st.layout.load_config()
        if cfg.locked_problem_id == problem_id:
            # 删掉已锁定的题目会让项目指向一个不存在的题，
            # 后续审计和正文引用都会莫名其妙地失败。
            raise HTTPException(
                409, f"{problem_id} 已锁定，不能删除。先改锁到别的题，或直接换项目。")
        path.unlink()
        return {"removed": problem_id}

    @app.post("/api/project/unlock")
    def unlock_problem() -> Dict[str, Any]:
        """解锁：退回选题阶段。

        锁定会把侧栏收窄到构建流程，如果锁错了题、或者想重新比较几道题，
        没有退路就会很难受 —— 用户只能去手工改 project.yaml。
        已经产出的结果不删：换题之后它们会显示为过期，
        由用户决定是重跑还是放弃。
        """
        from .schemas import ProjectPhase

        st = store()
        cfg = st.layout.load_config()
        was = cfg.locked_problem_id
        if not was:
            raise HTTPException(409, "当前没有锁定任何题目，不需要解锁。")
        cfg.locked_problem_id = None
        cfg.phase = ProjectPhase.PROBLEM_SELECTION
        st.layout.save_config(cfg)
        return {"unlocked": was,
                "project": cfg.model_dump(by_alias=True),
                "findings": findings_payload(st)}

    @app.put("/api/project")
    def update_project(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """改项目级设置。

        目前只有队伍控制号需要在这里改：它印在摘要页上，比赛期间
        可能后补或改动，没有入口的话用户就得去手工编辑 project.yaml。
        """
        st = store()
        cfg = st.layout.load_config()
        if "team_control_number" in payload:
            v = payload.get("team_control_number")
            cfg.team_control_number = (str(v).strip() or None) if v else None
        if "name" in payload:
            v = payload.get("name")
            cfg.name = (str(v).strip() or None) if v else None
        st.layout.save_config(cfg)
        return {"project": cfg.model_dump(by_alias=True)}

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

        # 外观覆盖在模板画完之后施加，所以 38 个模板自己不用知道这件事。
        # 一个旋钮填错不该让图出不来 —— apply_overrides 内部吞掉异常。
        from . import mcmplot as _mcmplot

        _mcmplot.apply_overrides(fig, payload.get("meta") or {})

        buf = io.BytesIO()
        fig.savefig(buf, format="pdf", bbox_inches="tight")
        _close_fig(fig)
        buf.seek(0)
        return Response(content=buf.read(), media_type="application/pdf")

    # ------------------------------------------------------- math & params
    # -- DIY 生图 ---------------------------------------------------------
    @app.get("/api/diy/options")
    def diy_options() -> Dict[str, Any]:
        """DIY 能选的图形类型、配色，以及外观微调旋钮。

        前端不硬编码这些清单 —— 加一种图或一个旋钮要同时改两处，
        早晚不一致。
        """
        from . import mcmplot
        from .diyfig import catalog
        return {**catalog(), **mcmplot.catalog(),
                "has_cjk_font": mcmplot.has_cjk()}

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
        实验上重复用，存规格才能改数据重用。

        落盘位置是**用户目录** ``~/.mcmtools/templates/figures/``，
        不是程序自带的 templates/。原因有两个，都是实际的故障：
        程序目录在 .app 包里是只读的（写进去直接报错），
        而且 `git pull` 会把它整个覆盖掉 —— 用户调好的图不该因为
        一次升级就消失。自带库和用户库由 TemplateRegistry 一起加载。
        """
        import re as _re

        import yaml as _yaml

        from .diyfig import CATEGORICAL, CHART_TYPES, MATRIX_TYPES, render
        from .root import core_root, user_templates_root

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

        chart = spec.get("chart") or "line"
        out_dir = (user_templates_root() / "figures" / f"diy_{slug}")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(
                422, f"写不进自定模板目录 {out_dir.parent}：{exc}")

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
        #
        # core 路径写成**绝对路径 + 环境变量兜底**：模板现在落在
        # ~/.mcmtools/templates/ 下，和程序目录没有固定的相对关系，
        # 靠 '../../../core' 上溯必然指错地方（原来那份就是这么写的，
        # 只是因为当时存在仓库里才碰巧成立）。
        core_abs = str(core_root())
        render_src = "\n".join([
            '"""由面板 DIY 生成。要改样式就在面板里重新保存。"""',
            "from __future__ import annotations",
            "",
            "import os",
            "import sys",
            "from typing import Any, Dict, Optional",
            "",
            "# 生成时记下的 core 路径；程序被移动过就用 MCMTOOLS_HOME 重新定位。",
            "_CORE = os.environ.get('MCMTOOLS_CORE') or " + repr(core_abs),
            "if _CORE not in sys.path:",
            "    sys.path.insert(0, _CORE)",
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

    @app.post("/api/experiments")
    def create_experiment(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """新建一个实验协议。

        实验页此前只列已有实验，空项目下就是一句"还没有定义实验" ——
        没有任何新建入口，后端也只有"运行"没有"创建"。新用户因此
        永远跑不出第一个结果，整条结果追踪链在这里断掉。
        """
        from .schemas import Experiment, Varied

        st = store()
        label = str(payload.get("label") or "").strip()
        kind = payload.get("kind") or "other"
        allowed_kinds = [e.value for e in Experiment.model_fields["kind"].annotation]
        if kind not in allowed_kinds:
            raise HTTPException(
                422, f"实验类型 {kind!r} 不认识。可选：{'、'.join(allowed_kinds)}。")

        eid = str(payload.get("id") or "").strip()
        if not eid:
            # 编号按已有数量递增，和 EXP-001 这种写法保持一致
            n = len(st.list_experiments()) + 1
            while True:
                eid = f"EXP-{n:03d}"
                if not st.layout.experiment_path(eid).is_file():
                    break
                n += 1
        elif st.layout.experiment_path(eid).is_file():
            raise HTTPException(409, f"实验 {eid} 已存在。")

        # 变动参数：面板传来的是 [{name, values|range, step, unit}]
        varied: List[Varied] = []
        for v in (payload.get("varied") or []):
            if not isinstance(v, dict) or not str(v.get("name") or "").strip():
                continue
            kw: Dict[str, Any] = {"name": str(v["name"]).strip()}
            if v.get("values"):
                kw["values"] = v["values"]
            if v.get("range"):
                kw["range"] = v["range"]
            if v.get("step") is not None:
                kw["step"] = v["step"]
            if v.get("unit"):
                kw["unit"] = v["unit"]
            if "values" not in kw and "range" not in kw:
                raise HTTPException(
                    422, f"变动参数「{kw['name']}」要给出取值列表或区间，否则没法展开试验。")
            varied.append(Varied(**kw))

        # 套模板：模板带 defaults（n_runs、aggregation 等）和输入说明。
        # 光有 schema 不够 —— 新用户不知道 sensitivity_oat 该填什么参数，
        # 也不知道运行脚本长什么样，跑不起来就永远拿不到第一个结果。
        tpl = payload.get("template_id")
        tpl_defaults: Dict[str, Any] = {}
        tpl_inputs: List[Dict[str, Any]] = []
        if tpl:
            from .templates import load_registry

            reg = load_registry()
            try:
                t = reg.get(str(tpl))
            except KeyError:
                t = None
            # reg.get() 找不到时返回 None 而不是抛异常，两种都要接住
            if t is None:
                raise HTTPException(404, f"没有这个实验模板：{tpl}")
            tkind = getattr(t.kind, "value", t.kind)
            if tkind != "experiment":
                raise HTTPException(
                    422, f"{tpl} 不是实验模板，它的类型是 {tkind}。")
            tpl_defaults = dict(getattr(t, "defaults", None) or {})
            # 模板目录名和 ExperimentKind 是同义词但不是同一个字符串，
            # 所以显式列出来，不做字符串猜测 —— 猜错会让实验类型
            # 与实际做的分析对不上，而类型决定默认出图。
            _KIND_OF_TPL = {
                "exp.sensitivity_oat": "sensitivity_oat",
                "exp.sensitivity_grid": "sensitivity_grid",
                "exp.model_comparison": "model_comparison",
                "exp.robustness_noise": "robustness_noise",
                "exp.monte_carlo": "monte_carlo",
                "exp.cross_validation": "cross_validation",
                "exp.convergence_study": "convergence_study",
                "exp.scenario": "scenario",
                "exp.train_test": "train_test",
            }
            if not payload.get("kind") and str(tpl) in _KIND_OF_TPL:
                kind = _KIND_OF_TPL[str(tpl)]
            for i in (getattr(t, "inputs", None) or []):
                tpl_inputs.append(
                    i.model_dump() if hasattr(i, "model_dump") else dict(i))

        # 模板的 defaults 里有些键不是 Experiment 的字段（例如
        # dispersion_kind —— 它是"怎么算离散度"的说明，不是模型属性）。
        # schema 是 extra="forbid"，直接透传会整条建不出来。
        # 所以只取认识的那些，剩下的作为提示返回，不静默丢掉。
        if varied:
            # 用户填了变动轴就说明他知道自己要什么，不该被模板默认值覆盖
            accepted_defaults: Dict[str, Any] = {}
        else:
            fields = set(Experiment.model_fields.keys())
            accepted_defaults = {k: v for k, v in tpl_defaults.items() if k in fields}
        ignored_defaults = {k: v for k, v in tpl_defaults.items()
                            if k not in accepted_defaults}

        try:
            exp = Experiment(
                id=eid, label=label or None, kind=kind,
                dataset_id=payload.get("dataset_id") or None,
                model_id=payload.get("model_id") or None,
                motivation=payload.get("motivation") or None,
                entrypoint=payload.get("entrypoint") or None,
                varied=varied,
                random_seed=payload.get("random_seed"),
                **accepted_defaults,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, f"实验协议填得不对：{exc}")
        st.save_experiment(exp)
        out: Dict[str, Any] = {"experiment": exp.model_dump(by_alias=True)}
        if tpl_inputs:
            out["template_inputs"] = tpl_inputs
        if ignored_defaults:
            # 这些默认值没有对应的模型字段，告诉用户而不是咽掉
            out["template_notes"] = ignored_defaults
        return out

    # -- 代码骨架：在 app 内写程序跑数据 ----------------------------------
    # 为什么需要这一组接口：templates/code/ 下本来就有 16 个能直接跑的
    # 骨架（敏感性、蒙特卡洛、AHP、TOPSIS…），但要用它们必须先手写
    # experiments/EXP-xxx/run.py、再手工把 entrypoint 填进协议 ——
    # 而 run.py 的契约（收一个 trial 字典、返回 {"atoms": [...]}）
    # 是新用户最容易写错的地方（见 docs/coderread.md）。
    # 于是"有 16 个骨架"和"能跑出第一个结果"之间隔着一道坎。
    # 这组接口把这道坎拆掉：选骨架 → 自动生成 run.py → 直接能跑。
    @app.get("/api/snippets")
    def list_snippets() -> List[Dict[str, Any]]:
        """可选用的代码骨架清单（来自 templates/code/）。"""
        reg = _registry()
        out = []
        for t in reg.by_kind("code"):
            out.append({
                "template_id": t.template_id,
                "purpose": reg.headline(t),
                "description": t.description,
                "entrypoint": t.entrypoint,
                "inputs": [{"name": i.name, "role": i.role, "type": i.type,
                            "optional": i.optional,
                            "description": i.description} for i in t.inputs],
                "defaults": t.defaults,
                "dependencies": t.dependencies,
                # 骨架源码要能直接看到 —— "这行要改成我的"比读文档快
                "source": _snippet_source(t),
            })
        return sorted(out, key=lambda x: x["template_id"])

    def _snippet_source(t) -> str:
        from .root import find_template_file

        if not t.entrypoint:
            return ""
        # entrypoint 形如 code/ahp_evaluation/snippet.py
        parts = t.entrypoint.split("/")
        if len(parts) < 3:
            return ""
        p = find_template_file("code", parts[-2], parts[-1])
        if p is None:
            return ""
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return ""

    @app.post("/api/experiments/from-snippet")
    def experiment_from_snippet(payload: Dict[str, Any] = Body(...)
                                ) -> Dict[str, Any]:
        """用代码骨架建一个实验，并自动写好能跑的 run.py。

        生成的 run.py 不是把骨架原样拷过来 —— 骨架是**独立脚本**
        （有 main()、自己造模拟数据、把图写到临时目录），而实验协议要的是
        ``run(trial) -> {"atoms": [...]}``。直接拷过来会因为签名不对
        而跑不起来，用户还得自己琢磨怎么接。

        所以这里生成的是一个**适配层**：保留骨架的模型函数不改，
        把它的输出接到结果原子上，并在文件里写清楚"要改哪几行"。
        """
        import re as _re

        from .schemas import Experiment
        from .templates import load_registry

        st = store()
        snippet_id = str(payload.get("snippet_id") or "").strip()
        if not snippet_id:
            raise HTTPException(422, "要指定用哪个代码骨架。")

        reg = load_registry()
        t = reg.get(snippet_id)
        if t is None:
            raise HTTPException(404, f"没有这个骨架：{snippet_id}")
        tkind = getattr(t.kind, "value", t.kind)
        if tkind != "code":
            raise HTTPException(422, f"{snippet_id} 不是代码骨架（kind={tkind}）。")

        # 实验编号：和 create_experiment 一样的递增规则
        eid = str(payload.get("id") or "").strip()
        if not eid:
            n = len(st.list_experiments()) + 1
            while True:
                eid = f"EXP-{n:03d}"
                if not st.layout.experiment_path(eid).is_file():
                    break
                n += 1
        elif st.layout.experiment_path(eid).is_file():
            raise HTTPException(409, f"实验 {eid} 已存在。")

        label = str(payload.get("label") or "").strip() or \
            (reg.headline(t) or snippet_id).split("：")[0][:40]

        # 变动参数：面板填的 "名字=值,值,值" 形式，或直接给数组
        varied = []
        for v in (payload.get("varied") or []):
            if not isinstance(v, dict) or not str(v.get("name") or "").strip():
                continue
            name = str(v["name"]).strip()
            vals = v.get("values")
            if isinstance(vals, str):
                vals = [x.strip() for x in _re.split(r"[,，\s]+", vals) if x.strip()]
                vals = [_num_or_str(x) for x in vals]
            if not vals:
                continue
            varied.append({"name": name, "values": list(vals)})

        entrypoint_rel = f"experiments/{eid}/run.py"
        # trial 里实际会出现哪些键，取决于**用户声明的变动参数**，
        # 不是骨架自己声明的输入（那两个是"骨架脚本的输入"，
        # 跟实验协议的 trial 不是一回事）。
        #
        # 这里一度取的是骨架的 inputs，于是建了 w=0.1,0.5,1.0 的实验，
        # 生成的 run.py 却教用户去读 model/base_params/sweep_spec ——
        # 三个永远不会出现在 trial 里的键。脚本照样能跑（`.get` 有默认值），
        # 但注释和代码说的参数是错的，用户按它改必然改错地方。
        param_names = [v["name"] for v in varied] or \
            [i.name for i in (t.inputs or []) if not i.optional] or ["x"]

        exp = Experiment(
            id=eid,
            label=label,
            kind=payload.get("kind") or "other",
            dataset_id=payload.get("dataset_id") or None,
            motivation=payload.get("motivation") or
            f"由代码骨架 {snippet_id} 生成；改 run.py 里的 MODEL 段落即可。",
            entrypoint=f"{entrypoint_rel}:run",
            varied=[{"name": v["name"], "values": v["values"]} for v in varied],
        )
        st.save_experiment(exp)

        script_dir = st.root / "experiments" / eid
        script_dir.mkdir(parents=True, exist_ok=True)
        script = _snippet_runner_source(snippet_id, reg.headline(t), param_names)
        (script_dir / "run.py").write_text(script, encoding="utf-8")

        return {
            "experiment": exp.model_dump(by_alias=True),
            # 键名说清是路径还是内容：叫 "script" 而给一条路径，
            # 调用方几乎必然当成源码用（面板最初就是这么读的）。
            "script_path": str(script_dir / "run.py"),
            "script_source": script,
            "script_rel": entrypoint_rel,
            "snippet_id": snippet_id,
            "parameter_names": param_names,
            "findings": findings_payload(st),
        }

    @app.get("/api/experiments/{exp_id}/script")
    def get_experiment_script(exp_id: str) -> Dict[str, Any]:
        """读实验脚本的源码，供面板内编辑。

        面板内编辑的意义：run.py 的契约容易写错，而"报错 → 看 stderr →
        回去改"如果要在两个程序之间来回切，一轮调试就断成两截。
        """
        st = store()
        try:
            exp = st.load_experiment(exp_id)
        except Exception:
            raise HTTPException(404, f"没有实验 {exp_id}")
        ep = getattr(exp, "entrypoint", None)
        if not ep:
            return {"experiment_id": exp_id, "path": None, "source": "",
                    "exists": False,
                    "hint": "这个实验还没有指定脚本。可以在下面写一个，"
                            "然后保存 —— 保存时会自动填好 entrypoint。"}
        rel = ep.split(":")[0]
        path = (st.root / rel).resolve()
        # 目录穿越防护：脚本必须落在项目目录内
        if st.root.resolve() not in path.parents:
            raise HTTPException(403, "脚本路径超出项目目录。")
        if not path.is_file():
            return {"experiment_id": exp_id, "path": str(path), "source": "",
                    "exists": False,
                    "hint": f"文件还不存在：{rel}。写点内容保存就会创建它。"}
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise HTTPException(422, f"{rel} 不是 UTF-8 文本，没法在面板里编辑。")
        return {"experiment_id": exp_id, "path": str(path),
                "rel": rel, "source": src, "exists": True,
                "entrypoint": ep}

    @app.put("/api/experiments/{exp_id}/script")
    def put_experiment_script(exp_id: str,
                              payload: Dict[str, Any] = Body(...)
                              ) -> Dict[str, Any]:
        """把面板里编辑的脚本写回磁盘。

        写之前先做语法检查（compile）—— 让一个语法错误的文件落盘，
        下次运行时报的是 Python 的 SyntaxError，用户还得自己回到
        面板里找是哪一行。这里直接拒掉并指出行号。
        """
        st = store()
        try:
            exp = st.load_experiment(exp_id)
        except Exception:
            raise HTTPException(404, f"没有实验 {exp_id}")

        source = payload.get("source")
        if not isinstance(source, str):
            raise HTTPException(422, "source 要是字符串。")
        if len(source) > 400_000:
            raise HTTPException(422, "脚本太长了（超过 400KB）。")

        rel = (getattr(exp, "entrypoint", None) or "").split(":")[0] or \
            f"experiments/{exp_id}/run.py"
        path = (st.root / rel).resolve()
        if st.root.resolve() not in path.parents:
            raise HTTPException(403, "脚本路径超出项目目录。")

        # 语法预检。编译成字节码能顺带查缩进、括号、关键字拼写。
        try:
            compile(source, rel, "exec")
        except SyntaxError as exc:
            where = f"第 {exc.lineno} 行" if exc.lineno else "某处"
            raise HTTPException(
                422, f"语法错误（{where}）：{exc.msg}。改好再保存。")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

        # 原来没声明 entrypoint 的，顺手补上 —— 否则保存了也跑不起来，
        # 用户会以为"保存没生效"。
        if not getattr(exp, "entrypoint", None):
            exp.entrypoint = f"{rel}:run"
            st.save_experiment(exp)
            return {"saved": str(path), "rel": rel, "entrypoint": exp.entrypoint,
                    "note": f"已自动设置 entrypoint = {exp.entrypoint}"}
        return {"saved": str(path), "rel": rel, "entrypoint": exp.entrypoint}

    @app.delete("/api/experiments/{exp_id}")
    def delete_experiment(exp_id: str) -> Dict[str, Any]:
        st = store()
        # experiment_path() 返回的是**文件**路径（…/experiments/EXP-001/experiment.yaml），
        # 不是目录。当成目录用会让删除和查重都失效。
        f = st.layout.experiment_path(exp_id)
        if not f.is_file():
            raise HTTPException(404, f"没有实验 {exp_id}")
        if st.load_experiment(exp_id).run_ids:
            # 跑过的实验直接删会把结果原子变成孤儿，审计会指向不存在的来源
            raise HTTPException(
                409, f"{exp_id} 已经有运行记录了，不能直接删除。"
                     f"先确认那些结果不需要，再手工清理。")
        f.unlink()
        try:
            f.parent.rmdir()   # 目录空了才删掉，里面还有别的文件就留着
        except OSError:
            pass
        return {"removed": exp_id}

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
    # 路径统一走 root.py：.app 打包后 parents[2] 上溯不到仓库，
    # 面板会 404 而服务"看起来正常"。
    from .root import web_root as _web_root

    web_dir = _web_root()

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
