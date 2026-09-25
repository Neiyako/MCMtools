"""数学内容区：符号表、公式、假设。

为什么这块从"模型层"里拆出来
----------------------------
原来这些东西挂在 `Model` 对象下面，而 `Model` 里绝大部分字段是
**描述论文怎么称呼模型**的记账：label_style（罗马数字还是阿拉伯数字）、
title_form、relation_to_siblings、baseline、uses_method_of……

那些字段不产出任何代码、任何数字、任何检查。用户的原话是
"模型这个东西不都是我们人想出来的，根本不需要做出来"—— 说的是对的。

但同一个 Model 类里还挂着三类**真的有用**的东西：

    symbols     符号表 —— 审计靠它查"同一符号在两处含义不同"（SYMBOL_REDEFINED）
    equations   公式   —— 审计靠它查"公式编号重复"（DUPLICATE_EQUATION_NUMBER）
    assumptions 假设   —— 论文里必须逐条给理由

所以做法是：**拆掉 Model 这层壳，把这三类内容提到项目层**。
它们本来就不该从属于"某个模型"—— 一篇论文只有一张符号表、
一套贯穿全文的编号。

存储
----
    math/math.yaml     符号、公式、假设、符号表设置

与 params/ 平级：params 管"数值从哪来"，math 管"符号和公式是什么"。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .schemas.common import MCMBase
from .schemas.model import (
    Assumption,
    Equation,
    NotationTable,
    Objective,
    Symbol,
)

MATH_DIRNAME = "math"
MATH_FILENAME = "math.yaml"

# 符号表非穷尽声明：语料里近乎通用的措辞。缺了这句审计会提醒。
NOTATION_DISCLAIMER = (
    "There are some variables that are not listed here and will be discussed "
    "in detail in each section."
)


class MathContent(MCMBase):
    """一篇论文的全部数学内容。

    不是"某个模型的属性"，而是项目级：符号表和公式编号跨全文唯一。
    """

    symbols: List[Symbol] = []
    equations: List[Equation] = []
    assumptions: List[Assumption] = []
    objective: Optional[Objective] = None
    constraints: List[str] = []
    notation_table: NotationTable = NotationTable()

    # -- 查询 ---------------------------------------------------------------
    def symbol_by_glyph(self, glyph: str) -> Optional[Symbol]:
        return next((s for s in self.symbols if s.glyph == glyph), None)

    def equation_by_number(self, number: str) -> Optional[Equation]:
        return next((e for e in self.equations if e.number == number), None)

    def numbered_equations(self) -> List[Equation]:
        return [e for e in self.equations if e.number and e.is_numbered]

    def glyphs(self) -> List[str]:
        return [s.glyph for s in self.symbols]

    def duplicate_glyphs(self) -> List[str]:
        """同一个符号出现多次 —— 可能是重定义。

        语料证据：17/383 篇存在跨模型符号复用，2024 A 还有一处表格与
        正文对 `r1` 的矛盾。所以这是真问题，不是吹毛求疵。
        """
        seen: Dict[str, int] = {}
        for s in self.symbols:
            seen[s.glyph] = seen.get(s.glyph, 0) + 1
        return sorted(g for g, n in seen.items() if n > 1)

    def duplicate_equation_numbers(self) -> List[str]:
        seen: Dict[str, int] = {}
        for e in self.numbered_equations():
            seen[e.number] = seen.get(e.number, 0) + 1
        return sorted(n for n, c in seen.items() if c > 1)

    def summary(self) -> Dict[str, Any]:
        return {
            "symbols": len(self.symbols),
            "equations": len(self.equations),
            "numbered_equations": len(self.numbered_equations()),
            "assumptions": len(self.assumptions),
            "has_objective": self.objective is not None,
        }


class MathStore:
    """读写 math/math.yaml。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def path(self) -> Path:
        return self.root / MATH_DIRNAME / MATH_FILENAME

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> MathContent:
        """读数学内容。文件不存在时返回空内容，而不是报错 ——
        新项目还没建符号表是正常状态。"""
        if not self.exists():
            return MathContent()
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return MathContent.model_validate(raw)

    def save(self, content: MathContent) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            # mode="json" 是项目里的既定写法：把枚举等非 YAML 原生类型
            # 转成可序列化的形式，否则 Role.UNKNOWN 这类会直接报
            # "cannot represent an object"。
            yaml.safe_dump(content.model_dump(mode="json", exclude_none=True),
                           allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return self.path

    # -- 编辑 ---------------------------------------------------------------
    def upsert_symbol(self, symbol: Symbol) -> MathContent:
        content = self.load()
        for i, s in enumerate(content.symbols):
            if s.id == symbol.id:
                content.symbols[i] = symbol
                break
        else:
            content.symbols.append(symbol)
        self.save(content)
        return content

    def remove_symbol(self, symbol_id: str) -> MathContent:
        content = self.load()
        content.symbols = [s for s in content.symbols if s.id != symbol_id]
        self.save(content)
        return content

    def upsert_equation(self, equation: Equation) -> MathContent:
        content = self.load()
        for i, e in enumerate(content.equations):
            if e.id == equation.id:
                content.equations[i] = equation
                break
        else:
            content.equations.append(equation)
        self.save(content)
        return content

    def upsert_assumption(self, assumption: Assumption) -> MathContent:
        content = self.load()
        for i, a in enumerate(content.assumptions):
            if a.id == assumption.id:
                content.assumptions[i] = assumption
                break
        else:
            content.assumptions.append(assumption)
        self.save(content)
        return content

    def ensure_disclaimer(self) -> MathContent:
        """补上符号表非穷尽声明。

        语料里这句话近乎通用。缺了它不是错误，但审稿人会问
        "为什么你的符号表是封闭的"。所以自动补，而不是报错。
        """
        content = self.load()
        if not content.notation_table.exhaustive and not content.notation_table.disclaimer:
            content.notation_table.disclaimer = NOTATION_DISCLAIMER
            self.save(content)
        return content

    def build_notation_rows(self) -> List[Dict[str, str]]:
        """按符号表生成 LaTeX 表格行。符号表是符号的**视图**，不手写。"""
        content = self.load()
        rows = []
        for s in content.symbols:
            rows.append({
                "glyph": s.glyph,
                "meaning": s.meaning,
                "unit": s.unit or "—",
                "domain": s.domain or "—",
            })
        return rows
