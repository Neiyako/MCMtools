"""部署自检：确认这个目录拷到别的机器上能用。

为什么需要它
------------
"把文件夹拷过去就能跑"是个**承诺**。承诺最容易在别人机器上破功的地方
不是代码，是拷贝过程本身：漏了 templates/、node_modules 带过去但架构不对、
从 U 盘拷来丢了可执行权限、路径里带了中文或空格。

这份自检回答一个问题：**现在这个目录，能不能直接给别人用？**
它检查的是"部署完整性"，不是"代码正确性"（那是 pytest 的事）。

设计上刻意不依赖网络和 pip：装依赖是 launcher 的活，这里只管
"该有的文件在不在、能不能读、跑不跑得起来"。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# 本体必须有这些东西。少任何一个，拷过去都是坏的。
REQUIRED = [
    ("core/mcm", "命令行入口"),
    ("core/mcmcore/__init__.py", "核心包"),
    ("core/mcmcore/launcher.py", "启动器逻辑"),
    ("core/mcmcore/api.py", "面板后端"),
    ("web/index.html", "面板页面"),
    ("web/app.js", "面板逻辑"),
    ("web/app.css", "面板样式"),
    ("start", "跨平台启动器"),
    ("templates", "模板库"),
]

# 可选的：缺了也能跑，但功能会打折。
OPTIONAL = [
    ("start.sh", "macOS/Linux 备用入口（权限丢失时用）"),
    ("start.bat", "Windows 双击入口"),
    ("build-app.sh", "生成 macOS .app"),
    ("docs", "文档"),
    ("examples", "示例项目"),
]

# 模板库的五个分区。少一个都说明拷贝不完整 ——
# 排除规则写错时很容易只拷过去一部分：74 个模板变 7 个，
# 而服务照常启动、照常响应，**不报任何错**。所以这里要数数。
TEMPLATE_KINDS = ["figures", "models", "tables", "experiments", "paper", "code"]


@dataclass
class Finding:
    level: str          # ok | warn | fail
    name: str
    detail: str = ""
    fix: str = ""

    def line(self) -> str:
        mark = {"ok": "正常", "warn": "注意", "fail": "失败"}[self.level]
        out = f"  [{mark}] {self.name}"
        if self.detail:
            out += f"  {self.detail}"
        return out


@dataclass
class Report:
    root: Path
    findings: List[Finding] = field(default_factory=list)

    @property
    def failures(self) -> List[Finding]:
        return [f for f in self.findings if f.level == "fail"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.level == "warn"]

    def ok(self) -> bool:
        return not self.failures


def _count_templates(reg_root: Path) -> Tuple[int, dict]:
    """数一遍模板。返回 (总数, 各分区数量)。"""
    import yaml

    per = {}
    total = 0
    for kind in TEMPLATE_KINDS:
        d = reg_root / kind
        if not d.is_dir():
            per[kind] = 0
            continue
        n = 0
        for f in d.rglob("template.yaml"):
            try:
                yaml.safe_load(f.read_text(encoding="utf-8"))
                n += 1
            except Exception:  # noqa: BLE001  坏模板由 load_strict 负责报
                pass
        per[kind] = n
        total += n
    return total, per


def inspect(root: Optional[Path] = None) -> Report:
    """检查这个目录能不能直接部署。"""
    if root is None:
        from mcmcore.root import repo_root

        root = repo_root()
    root = Path(root).resolve()
    rep = Report(root=root)

    # -- 本体文件 ---------------------------------------------------------
    for rel, desc in REQUIRED:
        p = root / rel
        if p.exists():
            rep.findings.append(Finding("ok", desc, rel))
        else:
            rep.findings.append(Finding(
                "fail", desc, f"缺 {rel}",
                fix=f"拷贝时把 {rel} 一起带上"))

    for rel, desc in OPTIONAL:
        p = root / rel
        if p.exists():
            rep.findings.append(Finding("ok", desc, rel))
        else:
            rep.findings.append(Finding(
                "warn", desc, f"没有 {rel}（不影响使用）"))

    # -- 可执行权限 -------------------------------------------------------
    # 从压缩包或 U 盘拷过来经常会丢。丢了不影响 start.sh，但
    # ./start 会 permission denied，用户会以为坏了。
    start = root / "start"
    if start.exists():
        if os.access(start, os.X_OK):
            rep.findings.append(Finding("ok", "start 可执行"))
        else:
            rep.findings.append(Finding(
                "warn", "start 没有执行权限",
                detail="用 ./start 会 permission denied",
                fix="chmod +x start   或者改用  sh start.sh"))

    # -- 模板库 -----------------------------------------------------------
    reg_root = root / "templates"
    if reg_root.is_dir():
        total, per = _count_templates(reg_root)
        detail = "、".join(f"{k} {v}" for k, v in per.items() if v)
        # 这个阈值不是审美，是分界线：模板数掉到几十个以下时，
        # 用户会开始找不到需要的图，而功能"看起来"还是好的。
        if total >= 70:
            rep.findings.append(Finding("ok", "模板库完整", f"{total} 个（{detail}）"))
        elif total > 0:
            rep.findings.append(Finding(
                "fail", "模板库不完整",
                detail=f"只有 {total} 个（{detail}）",
                fix="templates/ 下的分区没拷全，重新完整拷贝"))
        else:
            rep.findings.append(Finding(
                "fail", "模板库是空的", "templates/ 下没有模板",
                fix="拷贝时漏掉了 templates/"))

        missing = [k for k in TEMPLATE_KINDS if not (reg_root / k).is_dir()]
        if missing:
            rep.findings.append(Finding(
                "warn", "缺少模板分区", "、".join(missing),
                fix="如果确实不需要可以忽略"))
    else:
        rep.findings.append(Finding("fail", "没有 templates/ 目录"))

    # -- 模板能否真的加载 -------------------------------------------------
    # 数完数还要真的加载一遍：文件在但内容坏了，数数是发现不了的。
    try:
        sys.path.insert(0, str(root / "core"))
        from mcmcore.templates import TemplateLoadError, load_registry

        reg = load_registry(strict=False)
        if reg._errors:
            rep.findings.append(Finding(
                "fail", "有模板加载失败",
                detail=f"{len(reg._errors)} 个，第一个：{reg._errors[0][:80]}",
                fix="这些模板不会出现在面板里，检查它们的 template.yaml"))
        else:
            rep.findings.append(Finding(
                "ok", "模板全部可加载", f"{len(reg)} 个"))
    except Exception as exc:  # noqa: BLE001
        rep.findings.append(Finding(
            "fail", "模板加载失败", f"{type(exc).__name__}: {exc}"))

    # -- 面板资源 ---------------------------------------------------------
    js = root / "web" / "app.js"
    if js.exists() and js.stat().st_size < 5000:
        rep.findings.append(Finding(
            "fail", "web/app.js 不完整",
            detail=f"只有 {js.stat().st_size} 字节",
            fix="重新拷贝 web/"))

    # -- 路径里的坑 -------------------------------------------------------
    s = str(root)
    if any(ord(c) > 127 for c in s):
        rep.findings.append(Finding(
            "warn", "安装路径含非 ASCII 字符",
            detail=s,
            fix="某些 TeX 发行版在中文路径下会失败，建议移到纯英文路径"))
    if " " in s:
        rep.findings.append(Finding(
            "warn", "安装路径含空格",
            detail="命令行调用时需要加引号",
            fix="建议移到不含空格的路径"))

    # -- 解释器 -----------------------------------------------------------
    if sys.version_info >= (3, 9):
        rep.findings.append(Finding(
            "ok", "Python 版本", f"{sys.version.split()[0]}"))
    else:
        rep.findings.append(Finding(
            "fail", "Python 版本过低",
            detail=sys.version.split()[0],
            fix="需要 3.9 或更新版本"))

    return rep


def format_report(rep: Report) -> str:
    lines = [
        "",
        "MCMtools 部署自检",
        f"  目录：{rep.root}",
        "",
    ]
    for f in rep.findings:
        lines.append(f.line())
        if f.level == "fail" and f.fix:
            lines.append(f"          → {f.fix}")
    lines.append("")
    if rep.ok():
        n_warn = len(rep.warnings)
        if n_warn:
            lines.append(f"结论：可以部署（{n_warn} 条提示，都不影响使用）")
        else:
            lines.append("结论：可以部署，一切就绪。")
    else:
        lines.append(f"结论：还不能部署，有 {len(rep.failures)} 个问题要修。")
    lines.append("")
    return "\n".join(lines)
