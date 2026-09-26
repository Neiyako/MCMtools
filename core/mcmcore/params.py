"""参数区：一个实验里所有用到的常数，集中登记。

为什么参数要单独放一层
----------------------
参数是**建模里唯一必须写下来、又最容易写错来源的东西**。真实论文里
"参数没有出处"是最常见的硬伤之一，评审一眼就能看见：这个 0.041 是哪来的？

这些登记不适合挂在「模型」对象下。"模型"那层真正在做的事，是记录论文
*怎么称呼*模型（Model I / Model II、哪个是基线、谁是兄弟模型）—— 那是
关于描述的分类学，不产生任何代码或结果。参数不一样：它直接进脚本、
直接进论文、直接决定结果对不对。

所以参数单独成区，和模型那套分类学脱钩。

存放位置
--------
    <项目>/params/parameters.yaml    全部参数，一个文件

一个文件而不是每个参数一个目录：参数天然是**一起被查、一起被对比**的
（哪些是拟合的、哪些是查文献的），拆开反而难用。

与实验的关系
------------
实验声明它扫哪个参数、固定哪些参数，引用的是**参数名**：

    varied:     [beta]
    held_fixed: [gamma, lambda, phi]

具体值从本区取。所以改一个参数值 → 实验的解析结果变了 → 结果原子被
标过期。这条链路是"改了参数忘了重跑"能被发现的原因。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import Field

from .schemas.common import MCMBase
from .schemas.model import Parameter, ParameterSource

PARAMS_DIRNAME = "params"
PARAMS_FILENAME = "parameters.yaml"


class ParameterSet(MCMBase):
    """项目里的全部参数。"""

    parameters: List[Parameter] = Field(default_factory=list)

    def by_name(self) -> Dict[str, Parameter]:
        return {p.name: p for p in self.parameters}

    def values(self) -> Dict[str, Any]:
        """只取值，用于喂给实验脚本。"""
        return {p.name: p.value for p in self.parameters if p.value is not None}

    def unresolved(self) -> List[Parameter]:
        """来源未登记的参数 —— 审计要报的就是这些。"""
        return [p for p in self.parameters if p.source == ParameterSource.UNKNOWN]

    def get(self, name: str) -> Optional[Parameter]:
        return self.by_name().get(name)

    def names(self) -> List[str]:
        return [p.name for p in self.parameters]


class ParameterStore:
    """读写 <项目>/params/parameters.yaml。"""

    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def path(self) -> Path:
        return self.root / PARAMS_DIRNAME / PARAMS_FILENAME

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> ParameterSet:
        """读参数。文件不存在时返回空集，而不是抛异常 ——
        新项目还没写参数是正常状态。"""
        if not self.exists():
            return ParameterSet()
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return ParameterSet(**raw)

    def save(self, ps: ParameterSet) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump(
                ps.model_dump(mode="json", exclude_none=True),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return self.path

    def upsert(self, param: Parameter) -> Path:
        """新增或按名字更新一个参数。"""
        ps = self.load()
        keep = [p for p in ps.parameters if p.name != param.name]
        keep.append(param)
        keep.sort(key=lambda p: p.name)
        return self.save(ParameterSet(parameters=keep))

    def remove(self, name: str) -> Path:
        ps = self.load()
        return self.save(
            ParameterSet(parameters=[p for p in ps.parameters if p.name != name])
        )

    def init_scaffold(self, force: bool = False) -> Path:
        """写一个带示例的参数文件，供填空用。"""
        if self.exists() and not force:
            return self.path
        return self.save(ParameterSet(parameters=[]))
