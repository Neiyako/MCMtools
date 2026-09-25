"""Figure regeneration: turn a stale Figure record back into a current artifact.

This is the final link in the chain. The experiment runner marks a figure STALE
when a bound atom changes; this module re-renders it from the atom's CURRENT
values and clears the flag.

The corpus justification for generating rather than pasting: 74% of embedded
images in real papers are under 500px wide, and only 37% of figures are ever
cross-referenced. A generated figure bound to atoms cannot go stale silently.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .schemas import ArtifactStatus, Figure, ResultAtom
from .templates import default_registry_root
from .store import Store


class NoBoundData(Exception):
    """绑定的结果原子一个都解析不出来 —— 绑定失效了。"""


class FigureGenerator:
    """Renders Figure records to vector PDFs from their bound atoms."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.warnings: List[str] = []

    # -- public API --------------------------------------------------------
    def regenerate(
        self, figure_ids: Optional[List[str]] = None, only_stale: bool = True
    ) -> List[str]:
        """Regenerate figures and clear their STALE status."""
        atoms = {a.atom_id: a for a in self.store.load_atoms()}
        done: List[str] = []

        for fig in self.store.list_figures():
            if figure_ids and fig.id not in figure_ids:
                continue
            if only_stale and fig.status.value != "stale":
                continue
            try:
                path = self.render(fig, atoms)
            except Exception as exc:
                self.warnings.append(f"{fig.id}: {type(exc).__name__}: {exc}")
                continue
            fig.file = str(path.relative_to(self.store.root))
            fig.status = ArtifactStatus.GENERATED
            from datetime import datetime, timezone

            fig.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.store.save_figure(fig)
            done.append(fig.id)

        return done

    # -- rendering ---------------------------------------------------------
    def render(self, fig: Figure, atoms: Dict[str, ResultAtom]) -> Path:
        """按模板渲染成矢量 PDF。

        模板是**动态发现**的：每个 templates/figures/<name>/render.py
        自带 render(data, meta)。早先这里是一串 if template == 'fig.xxx'
        分支，加一个图模板就要改核心源码 —— 库再大也只能用已接线的几个。
        """
        out_dir = self.store.root / "figures"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{fig.id}.pdf"

        meta = {
            "caption": fig.caption or fig.id,
            "width_in": fig.width_in or 6.0,
        }

        try:
            data = self._collect_bindings(fig, atoms)
        except NoBoundData as exc:
            # 一个坏绑定不该卡住其它图：画占位图并记录警告。
            self.warnings.append(str(exc))
            return self._fallback(fig, atoms, out_path, meta)

        tmpl = self._load_template(fig.template_id)
        if tmpl is None:
            self.warnings.append(
                f"{fig.id}: 找不到模板 '{fig.template_id}' 的绘制代码，"
                f"已用通用图代替。请检查 templates/figures/ 下是否有该模板。"
            )
            return self._fallback(fig, atoms, out_path, meta)

        # drawio 类模板（流程图、结构图）不返回 matplotlib Figure，
        # 它们产出**可编辑的 .drawio 源文件**。之前没走这条分支，
        # 结果是流程图被当成"缺 render()"处理，画出一张写着
        # "缺绘制代码"的占位图 —— 图有，但是废的。
        if hasattr(tmpl, "build") and not hasattr(tmpl, "render"):
            result = tmpl.render_to_file(data, str(out_dir), fig.id, meta)
            pdf = result.get("pdf")
            if not pdf:
                # 没有 drawio 命令行就要**自己画一张 PDF**：论文编译只认
                # PDF。早先这里直接把 .drawio 当产出返回，编译器把它复制成
                # FIG-005.pdf，里面其实是 XML —— LaTeX 报
                # "reading PDF image failed"，而且文件确实存在，
                # 排查时会以为是图内容的问题，其实是格式不对。
                self.warnings.append(
                    f"{fig.id}: 没找到 drawio 命令行，已用等价示意图替代 PDF；"
                    f"可编辑源文件在 {result['drawio']}。"
                )
                return self._fallback(fig, atoms, out_path, meta,
                                      note="流程图（drawio 源文件见同目录 .drawio）",
                                      data=data)
            return Path(pdf)

        # 模板返回 matplotlib Figure。
        try:
            fig_obj = tmpl.render(data, meta)
        except TypeError as exc:
            # 只有在**调用本身**失败时才是签名问题。
            # 早期版本把所有 TypeError 都报成"签名不对"，结果模板内部
            # 真正的 TypeError（比如数据形状不对）被掩盖，用户照着提示
            # 去改签名，怎么改都还是这个错。这里按消息判断一下。
            if "argument" in str(exc) and "render()" in str(exc):
                raise TypeError(
                    f"模板 {fig.template_id} 的 render() 签名不对，"
                    "应为 render(data, meta) -> Figure。"
                )
            raise
        fig_obj.savefig(out_path, dpi=300, bbox_inches="tight")
        _close(fig_obj)
        return out_path

    def _load_template(self, template_id: str):
        """按 template_id 找到并加载模板的 render.py。

        模块名必须唯一 —— 每个模板文件都叫 render.py，用普通 import
        会让它们互相顶掉（第二次 import 拿到的是第一次的缓存）。
        """
        import importlib.util

        name = template_id.split(".")[-1]          # fig.bar_comparison -> bar_comparison
        path = default_registry_root() / "figures" / name / "render.py"
        if not path.is_file():
            return None
        mod_name = f"mcmfig_{name}"
        if mod_name in sys.modules:
            return sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod

    def _collect_bindings(
        self, fig: Figure, atoms: Dict[str, ResultAtom]
    ) -> Dict[str, object]:
        """把绑定的 ResultAtom 整理成模板声明的输入形状。

        关键的语义：**一个 y 序列共享一条 x 轴**。
        FIG-001 绑了 3 个 y（三次试验的峰值）和 1 个 x（被扫的参数）。
        被扫的值不在那个 x 原子里 —— 它在**每个 y 原子自己的 condition 里**：

            RES-EXP001-PEAK-ACTIVE-001  value=119299.92  condition="beta=0.1, ..."
            RES-EXP001-PEAK-ACTIVE-002  value=172428.61  condition="beta=0.177, ..."

        所以 x 要从 condition 里解析出来。这正是 ResultAtom 必须带
        condition 的原因：一个值脱离了它的条件就没有意义。
        """
        # 先处理序列绑定：这些直接给整条曲线，不参与"y 列表"的组装。
        series: Dict[str, object] = {}
        for b in fig.bindings:
            if b.is_literal():
                # 人写的结构内容：直接就是模板要的形状，不做任何解析。
                series[b.role] = b.value
                continue
            if not b.is_series():
                continue
            col = self._read_artifact_column(b)
            if col is None:
                raise NoBoundData(
                    f"{fig.id} 的序列绑定取不到数据："
                    f"{b.artifact_path} 的 {b.column} 列。"
                    "请确认该实验已经成功运行过、且文件里有这一列。"
                )
            series[b.role] = col

        roles: Dict[str, list] = {}
        for b in fig.bindings:
            if b.is_series() or b.is_literal():
                continue
            atom = atoms.get(b.atom_id)
            if atom is not None:
                roles.setdefault(b.role, []).append(atom)

        # 关键：绑定里的 role 如果**正好是模板声明的输入名**，就直接认。
        # 不认会怎样：FIG-002 绑了 r2/rmse/peak 三个原子都标 role="y"，
        # 于是 actual 和 predicted 拿到同一批数，画出一条 R²=1、RMSE=0 的
        # 完美直线 —— 图看着正常，结论全错。这种错必须在这里挡住。
        declared_names = set(self._declared_inputs(fig.template_id))
        pinned: Dict[str, object] = {}
        for role, group in list(roles.items()):
            if role in declared_names and role not in ("x", "y", "value"):
                pinned[role] = [_num(a) for a in group]

        ys = roles.get("y") or [a for a in roles.get("value", [])]
        if not ys:
            # 没声明 role 时，把所有非基准的原子当数据点
            ys = [a for r, group in roles.items() if r != "reference" for a in group]

        if not ys and not series and _is_structural(fig.template_id):
            # 结构图（流程图、模型结构图）画的是"流程长什么样"，
            # 本来就没有数据要绑。没有绑定不是错误。
            return {}

        if not ys and not series:
            # 绑定的原子一个都找不到（原子被删了、或 id 写错了）。
            # 这种情况要**优雅降级**：画一张说明问题的占位图，
            # 而不是让整次重新生成失败 —— 否则一个坏绑定会卡住所有图。
            raise NoBoundData(
                f"{fig.id} 绑定的结果原子都找不到（绑定可能已失效）"
            )

        if series and not ys:
            # 整张图全靠序列绑定（曲线类图都是这样）。
            # 直接把它们交给模板，不再走"从标量拼 y 列表"那条路。
            data = dict(series)
            data.update(self._align_to_template(fig.template_id, dict(series), []))
            return data

        # x：优先用每个 y 自己 condition 里的自变量；解析不出来就退化成序号
        xs = roles.get("x") or []
        swept = _param_name(xs[0]) if xs else None
        x_vals = []
        for i, a in enumerate(ys):
            v = _condition_value(a.condition, swept) if swept else None
            x_vals.append(v if v is not None else i)

        data: Dict[str, object] = {
            "x": x_vals,
            "y": [_num(a) for a in ys],
        }
        ref = roles.get("reference") or roles.get("baseline")
        if ref:
            data["baseline"] = ref[0].numeric()

        # 模板声明的其它 role 直接透传，方便新模板扩展
        if roles.get("series"):
            data["series"] = [a.name for a in roles["series"]]
        if roles.get("categories"):
            data["categories"] = [a.name for a in roles["categories"]]

        # 按模板自己声明的输入名对齐。
        # 各个模板的输入名不一样（bar 要 categories+values，
        # sensitivity_line 要 x+y，pred_vs_actual 要 actual+predicted），
        # 而 Figure 的绑定只声明 role。所以这里读模板的 inputs 声明，
        # 把已解析出的通用数据映射到它期望的键名上。
        data = self._align_to_template(fig.template_id, data, ys)
        # 序列绑定是"整条曲线"，直接覆盖掉从标量推出来的任何东西。
        data.update(series)
        # 显式钉住的 role 覆盖猜测出来的映射：用户写 role="predicted"
        # 的意图比"看模板要什么就塞什么"更可信。
        for k, v in pinned.items():
            if len(v) == 1:
                v = v[0]
            data[k] = v
            if k in ("actual", "predicted", "values", "fitted", "y"):
                # 数值序列同时补齐通用的 x 轴，否则模板可能缺 x
                pass
        return data

    def _read_direct_column(self, b) -> Optional[list]:
        """读 code/output 下的文件。

        不是每个数据文件都值得为它注册一个实验 —— 人写的脚本直接把
        结果写到 code/output，图也应该能绑到那里。
        """
        import csv as _csv

        direct = self.store.root / "code" / "output" / (b.artifact_path or "")
        if not direct.is_file():
            return None
        try:
            with direct.open(newline="", encoding="utf-8") as fh:
                rows = list(_csv.DictReader(fh))
        except Exception:
            return None
        if not rows or b.column not in rows[0]:
            return None
        out = []
        for r in rows:
            v = r[b.column]
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                out.append(v)              # 类别列原样保留
        return out or None

    def _read_artifact_column(self, b) -> Optional[list]:
        """从运行归档里读出一列。

        找文件的顺序：指定的 run_id → 该实验最近一次成功运行。
        **只认成功的运行** —— 失败的那次可能只写了半截文件，
        拿它画图会画出一条看着像样但其实是残骸的曲线。
        """
        import csv as _csv

        import yaml

        runs_root = self.store.root / "runs"
        if not runs_root.is_dir():
            # 没有 runs/ 不代表读不到数据：code/output 下的人写产物
            # 也能绑。早先这里直接 return None，导致纯脚本产出的图
            # 永远绑不上，报错还只说是"取不到数据"。
            return self._read_direct_column(b)

        candidates = []
        if b.run_id:
            candidates = sorted(runs_root.glob(f"*/{b.run_id}"))
        else:
            # 倒序：最近的优先
            for exp_dir in sorted(runs_root.iterdir(), reverse=True):
                if not exp_dir.is_dir():
                    continue
                for run_dir in sorted(exp_dir.iterdir(), reverse=True):
                    rec = run_dir / "run.yaml"
                    if not rec.is_file():
                        continue
                    try:
                        meta = yaml.safe_load(rec.read_text(encoding="utf-8")) or {}
                    except Exception:
                        continue
                    if meta.get("status") == "success":
                        candidates.append(run_dir)
                        break

        for run_dir in candidates:
            path = run_dir / "artifacts" / (b.artifact_path or "")
            if not path.is_file():
                continue
            try:
                with path.open(newline="", encoding="utf-8") as fh:
                    rows = list(_csv.DictReader(fh))
            except Exception:
                continue
            if not rows or b.column not in rows[0]:
                continue
            out = []
            for r in rows:
                try:
                    out.append(float(r[b.column]))
                except (TypeError, ValueError):
                    continue
            if out:
                return out
        # 归档里没有，再试 code/output
        return self._read_direct_column(b)

    def _declared_inputs(self, template_id: str) -> list:
        """读模板 template.yaml 里声明的输入名。"""
        import yaml

        name = template_id.split(".")[-1]
        spec = default_registry_root() / "figures" / name / "template.yaml"
        if not spec.is_file():
            return []
        try:
            declared = yaml.safe_load(spec.read_text(encoding="utf-8")) or {}
        except Exception:
            return []
        return [i.get("name") for i in (declared.get("inputs") or []) if i.get("name")]

    def _align_to_template(self, template_id, data, ys):
        """把通用数据映射到模板声明的输入名。

        不做这一步会怎样：FIG-01 用 bar_comparison 模板、只绑了一个 y，
        但 bar_comparison 要的是 categories+values —— 于是报"缺少必填输入"，
        图生成不出来。而这些信息其实都有，只是名字对不上。
        """
        import yaml

        name = template_id.split(".")[-1]
        spec = default_registry_root() / "figures" / name / "template.yaml"
        if not spec.is_file():
            return data
        try:
            declared = yaml.safe_load(spec.read_text(encoding="utf-8")) or {}
        except Exception:
            return data
        wanted = [i.get("name") for i in (declared.get("inputs") or []) if i.get("name")]
        if not wanted:
            return data

        out = dict(data)

        # 防呆：actual 和 predicted 拿到**同一个**原子序列时，
        # pred_vs_actual 会画出一条完美对角线并标 R²=1、RMSE=0。
        # 那不是拟合得好，那是数据绑错了 —— 必须报出来。
        if "actual" in out and "predicted" in out and out["actual"] == out["predicted"]:
            raise NoBoundData(
                "actual 与 predicted 绑到了同一批数据，画出来必然是完美拟合。"
                "请把两个输入分别绑定到不同的结果原子。"
            )

        # 类别/标签类输入：用原子名当标签，这是唯一合理的默认
        for key in ("categories", "labels", "regions", "groups", "nodes", "models"):
            if key in wanted and key not in out and ys:
                out[key] = [a.name for a in ys]
        # 数值类输入
        for key in ("values", "predicted", "fitted", "actual", "y"):
            if key in wanted and key not in out and ys:
                out[key] = [_num(a) for a in ys]
        if "residual" in wanted and "residual" not in out and ys:
            out["residual"] = [_num(a) for a in ys]
        # 自变量类
        for key in ("iterations", "x"):
            if key in wanted and key not in out and "x" in data:
                out[key] = data["x"]
        if "frame" in wanted and "frame" not in out and ys:
            out["frame"] = {a.name: [_num(a)] for a in ys}
        if "matrix" in wanted and "matrix" not in out and ys:
            out["matrix"] = [[_num(a) for a in ys]]
        return out

    def _fallback(self, fig, atoms, out_path, meta, note=None, data=None) -> Path:
        """画一张诚实的示意图，而不是静默产出空页或假文件。

        note 用于说明为什么走了这条路（模板缺失 / 没有 drawio 命令行）。
        data 里如果有 nodes，就照着画方框，让图仍然有用。
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        mcmplot = self._load_mcmplot()
        if mcmplot is not None:
            mcmplot.setup()

        nodes = list((data or {}).get("nodes") or [])
        if nodes:
            # 有节点数据就照着画：图仍然有用，只是样式比 drawio 朴素。
            # 比画一张"缺代码"的红字占位图强得多 —— 用户要的是能插进论文的图。
            return self._draw_node_fallback(fig, nodes, out_path, meta, note)

        f, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 3.7))
        msg = note or f"缺少模板 {fig.template_id} 的绘制代码"
        ax.text(0.5, 0.5, f"{fig.id}\n{msg}",
                ha="center", va="center", fontsize=11, color="#b03030",
                transform=ax.transAxes, wrap=True)
        ax.axis("off")
        f.savefig(out_path, bbox_inches="tight")
        _close(f)
        return out_path

    def _draw_node_fallback(self, fig, nodes, out_path, meta, note) -> Path:
        """把节点画成一列方框，作为 drawio 不可用时的等价示意图。"""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

        n = len(nodes)
        f, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 0.62 * n + 1.0))
        colors = {"input": "#dbeafe", "process": "#e8f0e8",
                  "decision": "#fdf0d5", "output": "#e5e0f0"}
        for i, nd in enumerate(nodes):
            label = nd.get("label", nd.get("id", "")) if isinstance(nd, dict) else str(nd)
            kind = nd.get("kind", "process") if isinstance(nd, dict) else "process"
            y = n - i - 1
            box = FancyBboxPatch((0.12, y + 0.16), 0.76, 0.56,
                                 boxstyle="round,pad=0.02,rounding_size=0.06",
                                 linewidth=1.0, edgecolor="#4a5568",
                                 facecolor=colors.get(kind, "#eeeeee"))
            ax.add_patch(box)
            ax.text(0.5, y + 0.44, label, ha="center", va="center", fontsize=9.5)
            if i < n - 1:
                ax.add_patch(FancyArrowPatch((0.5, y + 0.16), (0.5, y + 0.02),
                                             arrowstyle="-|>", mutation_scale=11,
                                             linewidth=1.0, color="#4a5568"))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, n)
        ax.axis("off")
        if note:
            ax.set_title(note, fontsize=8, color="#718096")
        f.savefig(out_path, bbox_inches="tight")
        _close(f)
        return out_path

    def _load_mcmplot(self):
        """加载共享绘图设置（中文字体等）。"""
        import importlib.util

        path = default_registry_root() / "figures" / "mcmplot.py"
        if not path.is_file():
            return None
        if "mcmplot" in sys.modules:
            return sys.modules["mcmplot"]
        spec = importlib.util.spec_from_file_location("mcmplot", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["mcmplot"] = mod
        spec.loader.exec_module(mod)
        return mod

def _axis_value(atom: ResultAtom, xs: List[ResultAtom]) -> Optional[float]:
    """Position a series atom on the x-axis using its condition.

    A sensitivity figure's x-value IS the swept parameter, which lives in the
    condition string ('beta=0.1, gamma=0.0177(fixed)'). Parsing it means the
    figure follows the sweep automatically, with no manual x-array to maintain.
    """
    if xs:
        return xs[0].numeric()
    cond = atom.condition or ""
    for part in cond.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        _, _, raw = part.partition("=")
        raw = raw.replace("(fixed)", "").strip()
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def _x_label(xs: List[ResultAtom]) -> str:
    if xs:
        return xs[0].name.replace("_", " ")
    return "parameter value"


def _short(atom: ResultAtom) -> str:
    cond = atom.condition or ""
    first = cond.split(",")[0].strip()
    return first if first else atom.name


def _fmt_num(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:g}"


def _close(fig_obj) -> None:
    """渲染完立刻释放 figure，避免批量出图时内存持续上涨。"""
    try:
        import matplotlib.pyplot as plt

        plt.close(fig_obj)
    except Exception:
        pass


# drawio 类模板：画结构，不画数据
_STRUCTURAL = {"fig.flowchart", "fig.model_structure"}


def _is_structural(template_id: str) -> bool:
    return template_id in _STRUCTURAL


def _num(atom: ResultAtom):
    """取数值；取不到就退回原值（可能是字符串或列表）。"""
    v = atom.numeric()
    return v if v is not None else atom.value


def _param_name(atom: ResultAtom) -> Optional[str]:
    """从 x 绑定推断被扫的参数名。

    RES-1001 这类"参数原子"的 condition 往往是 'fitted'，没有可解析的
    键值对；此时回退到用它的 name。
    """
    if atom.condition and "=" in atom.condition:
        first = atom.condition.split(",")[0].strip()
        if "=" in first and "(" not in first:
            return first.split("=")[0].strip()
    return atom.name or None


def _condition_value(condition: Optional[str], param: Optional[str]):
    """从 'beta=0.1, gamma=0.025(fixed)' 里取出 beta 的值。"""
    if not condition or not param:
        return None
    for part in condition.split(","):
        part = part.strip()
        if "(" in part:          # gamma=0.025(fixed) 是被固定的，不是自变量
            continue
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        if k.strip() == param:
            try:
                return float(v.strip())
            except ValueError:
                return None
    return None
