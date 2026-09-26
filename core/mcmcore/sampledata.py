"""给图模板生成"能直接跑"的示例数据。

为什么要生成而不是手写
----------------------
生图工作台原来在 app.js 里硬编码了 12 份示例。模板涨到 28 个之后，
剩下 16 个点"填入示例数据"只会得到 `{}` —— 用户面对一个空文本框，
既不知道要填哪些键，也不知道每个键要什么形状。这是用户
最直接的抱怨："填 json 形式的数据有点不方便，样例写法没给"。

手写 28 份会立刻过期（加模板的人多半忘了补）。所以改成**从模板自己的
声明推导**：每个输入都标了 role 和 type，role 说"这个键是什么东西"，
type 说"是标量还是序列"。照着生成，新模板自动就有示例。

生成的数字是**编的**，但形状和量纲是对的，用户改数字比从零写键快得多。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# 按 role 决定这一项填什么形状的值。
# 左边是模板里真实用过的 role（见 templates/figures/*/template.yaml），
# 不是想象出来的分类。
_SEQUENCE_ROLES = {
    "independent_variable", "metric", "reference", "reference_series",
    "uncertainty", "dispersion", "distribution", "residual", "contribution",
    "objective_1", "objective_2", "parameter_1", "parameter_2",
    "state_1", "state_2", "response",
}
_LABEL_ROLES = {"labels", "label"}
_GROUP_ROLES = {"grouping"}
_STRUCTURE_ROLES = {"structure"}
_MATRIX_ROLES = {"matrix"}
_DATAFRAME_ROLES = {"dataframe"}
_SCALAR_ROLES = {"parameter", "reference_value", "annotation"}

# 名字里带这些词的一律当标量，即使 role 说是序列 ——
# 例如 baseline / bins / converged_at 在模板里都是单个数。
_SCALAR_NAMES = {
    "baseline", "bins", "confidence", "converged_at", "identity_line",
    "lower_only", "median_annotation", "zero_line", "base", "start",
    "width_in", "n_folds", "n_runs",
}


def _series(n: int = 6, kind: str = "generic") -> List[float]:
    """造一条形状合理的小序列。

    用不同形状而不是同一个常数：一条水平直线会让人以为图画错了，
    而这正是"示例数据"要避免的误会。
    """
    if kind in ("metric", "reference", "reference_series"):
        # 先升后降，像一条有峰值的指标
        return [round(2.0 + 3.4 * (1 - abs(i - (n - 1) / 2) / ((n - 1) / 2)), 2)
                for i in range(n)]
    if kind == "residual":
        # 残差就该在 0 附近上下跳
        return [round(0.4 * (1 if i % 2 else -1) * (1 - i / n), 2) for i in range(n)]
    if kind == "uncertainty":
        # 标准差必须为正
        return [round(0.1 + 0.05 * i, 3) for i in range(n)]
    if kind in ("objective_1", "state_1", "parameter_1"):
        return [round(0.1 * (i + 1), 2) for i in range(n)]
    if kind in ("objective_2", "state_2", "parameter_2"):
        return [round(9.0 - 1.4 * i, 2) for i in range(n)]
    return [round(1.0 + 0.8 * i, 2) for i in range(n)]


def _matrix(rows: int = 3, cols: int = 3) -> List[List[float]]:
    """对角占优的方阵 —— 像相关矩阵，读者一眼认得出。"""
    if rows == cols:
        return [[1.0 if r == c else round(0.5 - 0.2 * abs(r - c), 2)
                 for c in range(cols)] for r in range(rows)]
    return [[round((r + 1) * (c + 1) * 0.5, 2) for c in range(cols)]
            for r in range(rows)]


def value_for(name: str, role: Optional[str], type_: str = "any",
              template_id: str = "") -> Any:
    """给一个输入造示例值。

    判断顺序：名字 > role > type。名字最可靠 —— 模板作者起名
    `baseline` 时意思非常明确，而 role 有时是复用的泛称。
    """
    key = (name or "").lower()

    # 自变量：线性递增。画成钟形会让人以为图错了 —— 时间不会先升后降。
    if key in ("t", "x", "iterations", "fpr", "starts", "index", "day"):
        if key == "fpr":
            return [0.0, 0.05, 0.2, 0.45, 1.0]
        if key == "starts":
            return [0, 3, 6]
        return [float(i + 1) for i in range(6)]

    if key in _SCALAR_NAMES:
        if key == "bins":
            return 6
        if key in ("identity_line", "zero_line", "lower_only"):
            return True
        if key == "confidence":
            return 0.95
        if key == "median_annotation":
            return True
        return 2.5

    # 结构类：流程图、模型框架、桑基、甘特用的都是这几个键名
    if key == "nodes":
        return [{"id": "n1", "label": "读入数据", "kind": "input"},
                {"id": "n2", "label": "建立模型", "kind": "process"},
                {"id": "n3", "label": "输出结果", "kind": "output"}]
    if key == "edges":
        return [["n1", "n2"], ["n2", "n3"]]
    if key == "models":
        return [{"id": "m1", "label": "数据预处理"},
                {"id": "m2", "label": "优化模型"}]
    if key == "flows":
        return [["m1", "m2", "清洗后数据"]]
    if key == "stages":
        return [["输入", "清洗"], ["建模", "输出"]]
    if key == "tasks":
        return ["任务A", "任务B", "任务C"]
    if key == "starts":
        return [0, 3, 6]
    if key == "durations":
        return [3, 2, 2]

    if key in _LABEL_ROLES or (role in _LABEL_ROLES):
        if key == "categories":
            return ["方案A", "方案B", "方案C"]
        if key == "regions":
            return ["北京", "上海", "广东", "四川"]
        if key == "variables":
            return ["变量1", "变量2", "变量3"]
        if key == "group_order":
            return ["甲组", "乙组"]
        return ["甲", "乙", "丙"]

    if role in _GROUP_ROLES:
        if key == "groups":
            # 分组名要和 values 一一对应，所以这里重复给出
            return ["甲", "甲", "甲", "乙", "乙", "乙"]
        if key == "frontier_idx":
            return [1, 1, 1, 0, 0]
        return ["甲", "甲", "甲", "乙", "乙", "乙"]

    if role in _MATRIX_ROLES or key == "matrix":
        return _matrix()

    # 每个方案一行：radar 的 series、stacked 的 values 都是这个形状。
    # 平铺成一维会被模板拒掉（"第 1 个方案有 6 个得分，categories 有 3 个"），
    # 示例数据必须是能跑的。
    if key == "series" and type_ == "matrix":
        return [[2.0, 3.0, 2.5], [2.8, 2.2, 3.4]]
    if key == "values" and type_ == "matrix":
        return [[1.0, 2.0, 3.0], [2.0, 2.0, 2.0]]

    if role in _DATAFRAME_ROLES or key == "frame":
        return {"甲": [1, 2, 3, 4, 5], "乙": [2, 4, 5, 4, 6]}

    # 真假值开关
    if type_ == "scalar" and role == "annotation":
        return 2.5

    if role in _SCALAR_ROLES:
        if role == "reference_value":
            return 5.0
        return 0.3

    if role in _SEQUENCE_ROLES or type_ == "array":
        return _series(6, role or "generic")

    # 兜底：与其给个 `{}` 让用户猜，不如给一条真实形状的序列
    return _series(5)


def sample_for(template) -> Dict[str, Any]:
    """按模板声明生成示例数据。

    只生成**必填**输入的示例：可选输入留空，用户需要时自己加。
    全都塞进去会让示例看起来比实际复杂，反而吓退人。

    关键是**内部一致**：模板之间有长度约束（categories 与 values 等长、
    labels 与 series 行数相等、stages 与 flows 的层号对应）。按角色
    各自生成会在 9 个模板上被拒 —— 模板拒绝得对，错的是生成器。
    所以先定"主轴长度"，再让相关键对齐它。
    """
    tid = getattr(template, "template_id", "")
    inputs = list(getattr(template, "inputs", []) or [])
    names = {i.name for i in inputs}
    out: Dict[str, Any] = {}

    # 主轴长度：以"数值序列"的典型长度为基准，标签类都对齐到它。
    N = 6

    for inp in inputs:
        if inp.optional:
            continue
        out[inp.name] = value_for(inp.name, inp.role, inp.type, tid)

    # -- 对齐长度 ---------------------------------------------------------
    # 名字里带这些的，都是"和主数据一一对应"的标签/分组
    n_main = N
    if "categories" in out and "values" in out:
        n_main = len(out["categories"])
        out["values"] = _series(n_main, "metric")
    if "regions" in out and "values" in out:
        n_main = len(out["regions"])
        out["values"] = _series(n_main, "metric")
    if "groups" in out and "values" in out:
        # 分组图里 groups 和 values 等长（每个值属于哪一组）
        g = out["groups"]
        out["values"] = _series(len(g), "metric")
    if "labels" in out and "values" in out:
        out["values"] = _series(len(out["labels"]), "contribution")
    if "tasks" in out:
        n = len(out["tasks"])
        out["starts"] = [3 * i for i in range(n)]
        out["durations"] = [2 + (i % 2) for i in range(n)]
    if "labels" in out and "series" in out and isinstance(out["series"], list) \
            and out["series"] and isinstance(out["series"][0], list):
        # 雷达图：labels 的个数 = series 的行数
        k = len(out["labels"])
        m = len(out.get("categories") or [1, 2, 3])
        out["series"] = [[round(2.0 + 0.5 * ((r + c) % 3), 1) for c in range(m)]
                         for r in range(k)]
    if "t" in out and "y" in out:
        n = len(out["t"])
        out["y"] = _series(n, "metric")

    # -- 新增 10 个图模板的长度对齐 ---------------------------------------
    # 下面这些模板都有"标签个数 = 数值个数"或"矩阵列数 = 参数个数"的
    # 硬约束，而按 role 各自生成时标签类给 3 个、数值类给 6 个、
    # 矩阵给 3x3 —— 直接喂进去会被模板拒掉。模板拒绝得对，错的是
    # 生成器，所以在这里把长度对齐好。

    # dumbbell：before / after 要和 categories 一一对应
    if "before" in out and "after" in out and "categories" in out:
        n = len(out["categories"])
        out["before"] = _series(n, "reference")
        out["after"] = _series(n, "metric")

    # bump_chart：periods 的个数 = ranks 的列数；entities = ranks 的行数
    if "ranks" in out and "entities" in out and "periods" in out:
        # 每一列是一个时期的名次，用 1..k 的循环排列，避免出现并列名次
        k = len(out["entities"])
        out["ranks"] = [[(r + c) % k + 1 for c in range(3)]
                        for r in range(k)]
        out["periods"] = [str(2021 + c) for c in range(3)]

    # model_metric_radar：scores 的行数 = models，列数 = metrics
    if "scores" in out and "models" in out and "metrics" in out:
        # 雷达图的顶点标注会和相邻模型的标注挤在一起，所以模型之间
        # 必须拉开差距。原来生成 [0.6,0.7,0.8] 和 [0.7,0.8,0.9]，
        # 两行只差 0.1 —— 在雷达坐标里 0.7 和 0.7 会落到**同一个像素**，
        # 三个数字叠成一团，只有一个能看清。
        k = len(out["models"])
        m = len(out["metrics"])
        out["scores"] = [
            [round(0.45 + 0.16 * ((r * 2 + c) % 3) + 0.12 * r, 2)
             for c in range(m)]
            for r in range(k)
        ]

    # grid_search_surface：param_x 的个数 = scores 的列数，
    # param_y 的个数 = scores 的行数
    if "scores" in out and "param_x" in out and "param_y" in out:
        rows, cols = 3, 5
        out["param_x"] = [float(2 ** c) for c in range(cols)]
        out["param_y"] = [round(0.1 * (r + 1), 2) for r in range(rows)]
        out["scores"] = [[round(1.0 + (r + c) * 0.7, 2) for c in range(cols)]
                         for r in range(rows)]

    # -- 结构性数据 -------------------------------------------------------
    if "nodes" in out:
        # network_graph 要的是节点名列表，flowchart 要的是带 id 的对象。
        # 用 min_items 之类的类型信息区分：这里有 edges 的按图处理。
        if "edges" in out:
            out["nodes"] = ["甲", "乙", "丙"]
            out["edges"] = [["甲", "乙"], ["乙", "丙"], ["甲", "丙"]]
    if "stages" in out and "flows" in out:
        st = out["stages"]
        # flows 是 [源层号, 源节点号, 目标层号, 目标节点号, 流量]
        out["flows"] = [[0, 0, 1, 0, 5], [0, 1, 1, 1, 3], [0, 0, 1, 1, 2]]
        out["stages"] = [["输入A", "输入B"], ["输出C", "输出D"]]

    # -- 可选但在这些图里是灵魂的键 ---------------------------------------
    if tid == "fig.timeseries" and "observed" in names:
        base = out.get("y") or _series(N, "metric")
        out["observed"] = [round(v * 1.08 + 0.15, 2) for v in base]
        out["events"] = [3]
    if tid == "fig.sensitivity_line" and "baseline" in names:
        out["baseline"] = 2.5
    if tid == "fig.surface_3d":
        n = len(out.get("x") or [1, 2, 3])
        m = len(out.get("y") or [1, 2, 3])
        out["z"] = [[round(1.0 + (r + c) * 0.7, 2) for c in range(m)]
                    for r in range(n)]
    if tid == "fig.stacked_area":
        # labels 的个数必须等于 values 的行数（每条分量一个名字），
        # 否则色块和图例会错位 —— 模板会直接拒绝。
        n = len(out.get("t") or [1, 2, 3])
        k = len(out.get("labels") or ["甲", "乙"])
        out["values"] = [[round(1.0 + c * 0.5 + r * 0.8, 1) for c in range(n)]
                         for r in range(k)]
    if tid == "fig.roc_curve":
        out.update({"fpr": [0.0, 0.05, 0.2, 0.45, 1.0],
                    "tpr": [0.0, 0.55, 0.82, 0.93, 1.0]})

    # -- 矩阵类：行/列数必须和标签对齐 --------------------------------
    # 这些图的数据是二维的，而标签是分开给的（行一套、列一套）。
    # 独立生成必然对不上，模板会拒绝 —— 报错是对的，生成器要负责对齐。
    if "matrix" in out and "row_labels" in out and "col_labels" in out:
        k = len(out["row_labels"])
        m = len(out["col_labels"])
        out["matrix"] = [[round((r + 1) * (c + 1) * 0.6, 2) for c in range(m)]
                         for r in range(k)]
    if "residual" in out:
        out["residual"] = _series(len(out["residual"]), "residual")
    if "lower" in out and "upper" in out and "mean" in out:
        # 置信带：下界 < 均值 < 上界，否则带子会翻过来
        mu = [round(2.0 + 1.5 * i, 2) for i in range(len(out["mean"]))]
        out["mean"] = mu
        out["lower"] = [round(v - 0.6, 2) for v in mu]
        out["upper"] = [round(v + 0.6, 2) for v in mu]
    if "y_left" in out and "y_right" in out:
        # 双轴：两个量纲差一个数量级，否则看不出是双轴
        n = len(out["y_left"])
        out["y_left"] = [round(10.0 + 3.0 * i, 2) for i in range(n)]
        out["y_right"] = [round(0.2 + 0.05 * i, 3) for i in range(n)]
    if "highlight" in out and "categories" in out:
        out["highlight"] = ["否"] * len(out["categories"])
    return out


def snippet_for(template) -> str:
    """给人看的填写说明：每个键一行，带中文解释和示例值。

    这是"样例写法没给"的直接解法 —— 用户不该为了知道
    `groups` 要重复写分组名而先读源码。
    """
    lines: List[str] = []
    for inp in getattr(template, "inputs", []) or []:
        val = value_for(inp.name, inp.role, inp.type,
                        getattr(template, "template_id", ""))
        import json as _json
        shown = _json.dumps(val, ensure_ascii=False)
        if len(shown) > 68:
            shown = shown[:65] + "..."
        req = "必填" if not inp.optional else "可选"
        desc = _ROLE_CN.get(inp.role or "", "")
        lines.append(f"{inp.name}（{req}{'，' + desc if desc else ''}）={shown}")
    return "\n".join(lines)


# role 的中文解释。用户看到 "role: grouping" 不知道什么意思，
# 看到"分组名"就知道了。
_ROLE_CN = {
    "independent_variable": "横轴自变量",
    "metric": "要展示的指标",
    "reference": "参考序列（用来对照）",
    "reference_series": "参考曲线",
    "reference_value": "参考值，画一条水平线",
    "uncertainty": "不确定度，画误差带",
    "dispersion": "离散度，画误差棒",
    "distribution": "要统计分布的数值",
    "residual": "残差值",
    "contribution": "各因素的贡献，可正可负",
    "objective_1": "第一个目标",
    "objective_2": "第二个目标",
    "parameter_1": "第一个参数",
    "parameter_2": "第二个参数",
    "state_1": "状态量之一",
    "state_2": "状态量之一",
    "response": "响应值（二维）",
    "labels": "各项名称",
    "label": "标注文字",
    "grouping": "分组名，长度要和数据一致",
    "structure": "结构数据（节点/边/流向）",
    "matrix": "二维数值矩阵",
    "dataframe": "多列数据表",
    "parameter": "数值参数",
    "annotation": "标注位置",
    "vector_field": "向量场分量",
    "event_marker": "事件位置",
}
