"""fig.sankey_flow —— 桑基 / 流向图（多层节点 + 贝塞尔流量带）。

为什么自己画，不用第三方库
--------------------------
matplotlib 自带的 `Sankey` 类只能画**单向链**：一个节点最多一进一出，
`add()` 时流量对不上就报错。而建模题目里的流向图几乎都是分叉的——
"总需求分给 5 个仓库，再分给 12 个客户"，这是 Sankey 类做不了的。
plotly / pySankey / floweaver 之类能画，但比赛环境里多一个第三方依赖
就多一个装不上的风险（而且 plotly 出的是位图，论文要矢量）。

所以这里用纯 matplotlib 实现，几何全部自己算：
    每层的节点画成矩形条，条高正比于该节点的总流量；
    层与层之间的流量用**三次贝塞尔带**（matplotlib.path.Path）连接，
    带子宽度正比于流量。

数据从哪来
----------
    stages  每层的节点名，形如 [['总需求'], ['仓库A', '仓库B'], ['客户1', '客户2']]
    flows   流量列表，每条形如 [源层号, 源节点号, 目标层号, 目标节点号, 流量]
            层号 / 节点号都是 **0 起的下标**，指向 stages 里的位置

meta 里可能有：caption / x_label / y_label / width_in / stage_titles

诚实说明（图的边界）
--------------------
这是**带状的流向图**，不是严格的桑基图：本实现不做流量守恒检查，
也不强制"每个节点的出流之和 = 入流之和"。原因是在建模论文里，
流量往往是模型算出来的**非守恒结果**（损耗、库存变化都发生在层内），
强行守恒反而会画错。如果题目确实守恒，图的左右端会对齐；
如果不守恒，带子的粗细差异本身就是结论的一部分。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、字号、数字格式化）。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path  # noqa: E402

# 节点条的宽度（x 方向）。宽度是画布坐标下的常量：
# 节点条本身不代表数值，只有**高度**代表流量。
# 层内间隙不在这里定，它必须随节点个数自适应（见 render 里的 gap）。
_NODE_W = 0.055
_BAND_ALPHA = 0.55


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    stages_raw = data.get("stages")
    if stages_raw is None or len(stages_raw) == 0:
        raise ValueError(
            "缺少必填输入 stages：请提供每层的节点名，"
            "例如 [['总需求'], ['仓库A', '仓库B'], ['客户1', '客户2']]。"
        )

    stages: List[List[str]] = []
    for i, layer in enumerate(stages_raw):
        layer = list(layer or [])
        if not layer:
            raise ValueError(f"stages 的第 {i + 1} 层是空的，每层至少要有一个节点。")
        # 中文标签统一过 safe()：中文字体画不出某些科研常用符号，
        # 不过这一步会画成空心方框而且不报错。
        stages.append([mcmplot.safe(str(x)) for x in layer])
    n_stages = len(stages)

    if n_stages < 2:
        # 只有一层没有"流"可言，画出来是一列孤立的条。
        raise ValueError(
            f"stages 只有 {n_stages} 层，流向图至少需要 2 层才能体现流动。"
        )

    flows_raw = data.get("flows")
    if flows_raw is None or len(flows_raw) == 0:
        raise ValueError(
            "缺少必填输入 flows：请提供流量列表，每条形如 "
            "[源层号, 源节点号, 目标层号, 目标节点号, 流量]（下标从 0 开始）。"
        )

    flows: List[Tuple[int, int, int, int, float]] = []
    for i, f in enumerate(flows_raw):
        f = list(f or [])
        if len(f) < 5:
            raise ValueError(
                f"flows 的第 {i + 1} 条只有 {len(f)} 个元素，"
                "必须形如 [源层号, 源节点号, 目标层号, 目标节点号, 流量]。"
            )
        try:
            s_lv, s_nd, d_lv, d_nd = (int(f[0]), int(f[1]), int(f[2]), int(f[3]))
            w = float(f[4])
        except (TypeError, ValueError):
            raise ValueError(
                f"flows 的第 {i + 1} 条不是合法的数字："
                f"{f}。层号/节点号必须是整数，流量必须是数。"
            )
        # 下标越界是这类输入最容易犯的错（人写 1 起下标，或层号写反）。
        # 不检查的话会画出一条指向画布外的带子，图"成功"但是残的。
        if not 0 <= s_lv < n_stages:
            raise ValueError(
                f"flows 的第 {i + 1} 条的源层号 {s_lv} 越界，"
                f"stages 只有 {n_stages} 层（下标 0~{n_stages - 1}）。"
            )
        if not 0 <= d_lv < n_stages:
            raise ValueError(
                f"flows 的第 {i + 1} 条的目标层号 {d_lv} 越界，"
                f"stages 只有 {n_stages} 层（下标 0~{n_stages - 1}）。"
            )
        if not 0 <= s_nd < len(stages[s_lv]):
            raise ValueError(
                f"flows 的第 {i + 1} 条的源节点号 {s_nd} 越界，"
                f"第 {s_lv + 1} 层只有 {len(stages[s_lv])} 个节点。"
            )
        if not 0 <= d_nd < len(stages[d_lv]):
            raise ValueError(
                f"flows 的第 {i + 1} 条的目标节点号 {d_nd} 越界，"
                f"第 {d_lv + 1} 层只有 {len(stages[d_lv])} 个节点。"
            )
        if w < 0:
            raise ValueError(
                f"flows 的第 {i + 1} 条流量是负数（{mcmplot.fmt(w)}），"
                "请把反向流拆成另一条正向 flow，或先取绝对值。"
            )
        flows.append((s_lv, s_nd, d_lv, d_nd, w))

    total = sum(f[4] for f in flows)
    if total <= 0:
        raise ValueError(
            "flows 里所有流量都是 0，画出来只有空节点条，没有任何带子。"
            "请检查数据是否还没算完。"
        )

    # ---- 每个节点的吞吐量 ------------------------------------------------
    # 节点条的高度按"穿过它的流量之和"定。取源与目标两端的**较大值**，
    # 是因为不守恒时两端接的带子宽度不同，用较小值会让较宽的一头
    # 从节点条上漫出来，看起来像画错了。
    node_out: Dict[Tuple[int, int], float] = {}
    node_in: Dict[Tuple[int, int], float] = {}
    for s_lv, s_nd, d_lv, d_nd, w in flows:
        node_out[(s_lv, s_nd)] = node_out.get((s_lv, s_nd), 0.0) + w
        node_in[(d_lv, d_nd)] = node_in.get((d_lv, d_nd), 0.0) + w

    node_size: Dict[Tuple[int, int], float] = {}
    for lv, layer in enumerate(stages):
        for nd in range(len(layer)):
            node_size[(lv, nd)] = max(
                node_out.get((lv, nd), 0.0), node_in.get((lv, nd), 0.0)
            )

    # 总尺度：最高的那一层决定整体高度，这样不同层之间粗细才可比。
    #
    # 这里有一个坑：不能只按"流量总量"定尺。每一层的节点条之间还有间隙，
    # 间隙也占画布高度，而各层的节点**个数**可以差很多（第 2 层 12 个节点、
    # 第 3 层 2 个）。按流量定尺会让节点多的那层被间隙撑爆画布。
    # 每层 block_flow = 该层节点条高度之和（用流量单位表示）。
    # 该层的实占高度 = block_flow * unit + gap * (节点数-1)。
    # 要让最"挤"的那层正好占满 1.0，就得解方程：
    #
    #     max_lv [ block_flow[lv] * unit + gap*(n_lv-1) ] = 1
    #     unit = (1 - max_lv[gap*(n_lv-1)]) / max_lv[block_flow[lv]]
    #
    # 注意 gap 只能**减一次**。把 gap 加进分母又加进
    # 每层的 block，等于加了两遍，结果每层都超出量程 0.125 —— 节点条的
    # y 落在 [-0.125, 1.125]，上下各有一截被裁掉，而且因为裁掉的是
    # 边缘、主体还在，看缩略图不容易发现。
    n_layers = len(stages)
    max_nodes = max(len(layer) for layer in stages)

    # 间隙占多少画布高度：节点越多间隙越小，保证 12 个节点的那层也放得下。
    # 上限定在 0.35，否则两三个节点的小图会散得太开。
    gap = min(0.35, 1.0 / (4.0 * max(1, max_nodes - 1))) if max_nodes > 1 else 0.0

    block_flow = [
        sum(node_size[(lv, nd)] for nd in range(len(layer)))
        for lv, layer in enumerate(stages)
    ]
    worst_flow = max(block_flow)
    worst_gap = max(gap * max(0, len(layer) - 1) for layer in stages)
    if worst_flow <= 0:
        raise ValueError("所有节点的流量都是 0，无法确定节点条高度。")
    # 间隙已经占满画布（层里节点极多）时留一点余量，避免 unit 变 0 或负数。
    unit = max(1e-9, (1.0 - worst_gap)) / worst_flow

    # ---- 节点的几何位置 --------------------------------------------------
    # 每层在垂直方向**居中**摆放：不居中的话，节点少的层会全部顶在上边，
    # 带子全往下斜，看起来像有额外的流向。
    node_y: Dict[Tuple[int, int], Tuple[float, float]] = {}   # (y0, y1)
    for lv, layer in enumerate(stages):
        heights = [node_size[(lv, nd)] * unit for nd in range(len(layer))]
        block = sum(heights) + gap * max(0, len(layer) - 1)
        # 从上往下铺：第一个节点贴住该层顶部，然后整体平移到垂直居中。
        # 居中让"层与层之间"的带子大致水平，读者更容易顺着读。
        y = (1.0 + block) / 2.0
        for nd in range(len(layer)):
            y -= heights[nd]
            node_y[(lv, nd)] = (y, y + heights[nd])
            y -= gap

    # 每层节点条的 x 位置：从左到右等距铺开。
    node_x = [i / (n_stages - 1) if n_stages > 1 else 0.0 for i in range(n_stages)]

    width = float(meta.get("width_in", 6.6))
    # 层数多 / 节点多时画布要高一点，否则带子会被压成细线。
    height = max(3.6, min(9.0, 0.72 * max_nodes + 1.6 * (n_stages - 1)))
    fig, ax = plt.subplots(figsize=(width, height))

    # ---- 每条流量带子的垂直落点 ------------------------------------------
    # 关键：带子在节点条上的**接出位置**要按顺序堆叠，不能都从中心出发，
    # 否则同一节点的多条带子会完全重叠，看起来只有一条。
    # 这里对每个节点的出流/入流各自维护一个游标，从条顶往下依次分配。
    out_cursor: Dict[Tuple[int, int], float] = {
        k: node_y[k][1] for k in node_y
    }
    in_cursor: Dict[Tuple[int, int], float] = {
        k: node_y[k][1] for k in node_y
    }

    # 颜色按**最左端的起点节点**分配：同一来源的流用同色，
    # 读者顺着颜色就能追踪"这批货最后去了哪"。这是流向图最主要的读法。
    cmap = plt.get_cmap("tab20")
    src_keys = sorted({(f[0], f[1]) for f in flows})
    color_of = {k: cmap(i % 20) for i, k in enumerate(src_keys)}

    # 画带子：先画的在下层。按流量升序画，大流量带压在上面更醒目。
    for s_lv, s_nd, d_lv, d_nd, w in sorted(flows, key=lambda f: f[4]):
        h = w * unit
        s_top = out_cursor[(s_lv, s_nd)]
        s_bot = s_top - h
        out_cursor[(s_lv, s_nd)] = s_bot

        d_top = in_cursor[(d_lv, d_nd)]
        d_bot = d_top - h
        in_cursor[(d_lv, d_nd)] = d_bot

        x0 = node_x[s_lv] + _NODE_W
        x1 = node_x[d_lv]
        # 贝塞尔控制点放在水平中点：这样带子离开节点条时是水平的，
        # 到达时也是水平的，中间平滑过渡。控制点若按直线插值，
        # 带子在节点处会有尖角，看起来像折线而不是"流"。
        xm = (x0 + x1) / 2.0

        verts = [
            (x0, s_top),
            (xm, s_top), (xm, d_top), (x1, d_top),     # 上边缘
            (x1, d_bot),                                # 右侧封口
            (xm, d_bot), (xm, s_bot), (x0, s_bot),     # 下边缘
            (x0, s_top),                                # 左侧封口
        ]
        codes = [
            Path.MOVETO,
            Path.CURVE4, Path.CURVE4, Path.CURVE4,
            Path.LINETO,
            Path.CURVE4, Path.CURVE4, Path.CURVE4,
            Path.CLOSEPOLY,
        ]
        ax.add_patch(
            PathPatch(
                Path(verts, codes),
                facecolor=color_of[(s_lv, s_nd)],
                edgecolor="none",
                alpha=_BAND_ALPHA,
                zorder=1,
            )
        )

    # ---- 节点条 ----------------------------------------------------------
    # 节点条压在带子上面（zorder 更高），带子的接口被条子盖住，边缘才干净。
    nd_cmap = plt.get_cmap("tab20")
    bar_colors = [nd_cmap(i % 20) for i in range(max_nodes)]
    for lv, layer in enumerate(stages):
        for nd in range(len(layer)):
            y0, y1 = node_y[(lv, nd)]
            if y1 - y0 <= 0:
                continue
            ax.add_patch(
                Rectangle(
                    (node_x[lv], y0), _NODE_W, y1 - y0,
                    facecolor=bar_colors[nd], edgecolor="#333333",
                    linewidth=0.6, zorder=3,
                )
            )
            # 节点名标在条子旁边。名字长的时候横排会互相压住，
            # 所以奇数层放左边、偶数层放右边，给文字让出空间。
            label_x = node_x[lv] + _NODE_W / 2.0
            ax.text(
                label_x, (y0 + y1) / 2.0,
                f"{layer[nd]}  ({mcmplot.fmt(node_size[(lv, nd)])})",
                ha="center", va="center", zorder=4,
                fontsize=7.5,
                bbox=dict(boxstyle="round,pad=0.16", facecolor="white",
                          edgecolor="none", alpha=0.82),
            )

    # 层标题：说明每一层代表什么（"第 1 周"、"仓库"、"客户"）。
    stage_titles = data.get("stage_titles") or meta.get("stage_titles")
    if stage_titles:
        stage_titles = list(stage_titles)
        if len(stage_titles) != n_stages:
            raise ValueError(
                f"stage_titles 有 {len(stage_titles)} 个，stages 有 {n_stages} 层，"
                "数量必须一致。"
            )
    else:
        stage_titles = [f"第 {i + 1} 层" for i in range(n_stages)]
    for lv in range(n_stages):
        ax.text(node_x[lv] + _NODE_W / 2.0, 1.045,
                mcmplot.safe(str(stage_titles[lv])),
                ha="center", va="bottom", fontsize=8.5, color="#333333")

    ax.set_xlim(-0.06, 1.06)
    ax.set_ylim(-0.03, 1.12)
    # 关掉坐标轴：流向图的坐标没有物理含义，留着刻度只会误导。
    ax.axis("off")
    if meta.get("x_label"):
        ax.set_xlabel(mcmplot.safe(meta["x_label"]))
    # 用 y 轴标题位写单位说明 —— 流量是有量纲的，论文里必须标出来。
    ax.text(-0.06, 1.045, mcmplot.safe(str(meta.get("y_label", "流量"))),
            ha="left", va="bottom", fontsize=8.5, color="#333333")
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    fig.tight_layout()
    return fig
