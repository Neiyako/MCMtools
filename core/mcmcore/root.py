"""安装路径的唯一真源。

为什么需要单独一个模块
----------------------
打包成 `MCMtools.app` 之后，出现了一类很难查的故障：模板库、面板、
git 版本号全都"有时候在、有时候不在"。根因是**路径解析散落在 6 个文件里**，
每一处都各写一遍 `Path(__file__).resolve().parents[N]`：

    templates.py   上溯找 templates/
    api.py         parents[2] / "web"
    figures.py     parents[2] / "templates"（三处）
    paperkit.py    parents[2] / "templates"（两处）
    deploy.py      parents[2]
    __init__.py    parents[2]（求 git 提交号）

这种写法有两个具体的坑：

1. **上溯会被"碰巧同名"骗到**。`templates.py` 原本这样找模板库：从本文件
   往上走，哪一层有 `templates/` 就用哪一层。如果用户把项目建在
    `~/mcm/`、而 `~/mcm/templates/` 恰好存在（哪怕是论文里的一个同名
   文件夹），模板库就指向那里 —— 服务照常启动、照常响应，只是模板
   少了一半，"看起来正常"。

2. **`.app` 被移动或单独分发时，上溯三级根本走不到仓库**。
   `MCMtools.app/Contents/MacOS/MCMtools` 上溯三级才是仓库根，
   把 .app 拖到别处，或者只把 .app 拷给队友，这条路就断了。

所以这里把路径收成一处，并且按**明确的优先级**解析，而不是猜：

    1. 环境变量            MCMTOOLS_HOME / MCMTOOLS_TEMPLATES / MCMTOOLS_WEB
    2. 冻结态               PyInstaller 之类的 sys.frozen / sys._MEIPASS
    3. 源码上溯             要求同时看到 core/mcmcore/__init__.py
    4. .app 内嵌兜底        Contents/Resources/{core,templates,web}

第 1 条是给 `build-app.sh` 用的：构建时把路径烘进启动脚本，
启动时导出为环境变量。这样"程序在哪"是**被明确告知**的，不是猜出来的。

第 3 条的上溯条件刻意收紧成"必须看到 core/mcmcore/__init__.py"，
而不是"看到一个叫 templates 的目录"—— 后者正是上面第 1 个坑。

第 4 条让 `MCMtools.app` 可以单独拷给别人：仓库整个不在时，
包内的 `Contents/Resources` 就是完整的程序。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

__all__ = [
    "repo_root",
    "core_root",
    "templates_root",
    "web_root",
    "user_templates_root",
    "user_home_dir",
    "template_roots",
    "find_template_file",
    "describe_paths",
]

# 用户自定内容（DIY 存的图模板）落在这里，而不是程序目录。
# 理由：程序目录在 .app 里是只读的，而且 `git pull` 会覆盖它 ——
# 用户辛苦调好的图不该因为一次升级就没了。
USER_DIR_ENV = "MCMTOOLS_USER_DIR"
DEFAULT_USER_DIR = ".mcmtools"

# template_id 里的 kind 是单数（figure/model/...），而 templates/ 下的
# 目录名是复数（figures/models/...）。这份映射收在一处 —— 数模板个数、
# 找模板文件都靠它，散开写迟早对不上。
TEMPLATE_FOLDERS = {
    "figure": "figures",
    "model": "models",
    "table": "tables",
    "experiment": "experiments",
    "paper": "paper",
    "code": "code",
}


def user_home_dir() -> Path:
    """用户自定内容的家目录，默认 ``~/.mcmtools``。"""
    override = os.environ.get(USER_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / DEFAULT_USER_DIR).resolve()


def user_templates_root() -> Path:
    """用户自定模板库。和程序自带的模板库分开，升级不会覆盖。"""
    return user_home_dir() / "templates"


def _looks_like_repo(p: Path) -> bool:
    """这个目录是不是 MCMtools 本体。

    判据是"有没有 core/mcmcore/__init__.py"，不是"有没有一个叫
    templates 的目录" —— 后者会把任何一个同名文件夹都认成本体。
    """
    return (p / "core" / "mcmcore" / "__init__.py").is_file()


def _from_env_source(name: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p.resolve() if p.exists() else None


def _bundle_dir(env_name: str) -> Optional[Path]:
    """app 包内的一份副本（Contents/Resources/...），存在才算数。

    判定条件是"真有这么个目录"，不是"环境变量被设了" ——
    启动器无条件导出这些变量，而本机开发时希望用的仍是仓库那一份。
    """
    p = _from_env_source(env_name)
    return p if p is not None and p.is_dir() else None


def _bundled_home() -> Optional[Path]:
    """包内副本所在的那一层（Contents/Resources/）。

    它含 core/ 和 templates/，可以当仓库用，但**不是**真的仓库：
    没有 .git，也不能 `git pull`。所以只在仓库确实找不到时才落到这里。
    """
    bundled_core = _bundle_dir("MCMTOOLS_BUNDLE_CORE")
    if bundled_core is None:
        return None
    parent = bundled_core.parent
    if (parent / "templates").is_dir() or (parent / "web").is_dir():
        return parent
    return None


def repo_root() -> Path:
    """MCMtools 本体所在目录。

    解析顺序见模块文档。全部落空时返回源码上溯的结果（即使不存在），
    让调用方拿到一个**确定的**路径去报错，而不是抛一个无法处理的异常 ——
    双击启动的 app 没有终端可以打印 traceback。
    """
    # 1. 明确告知的路径（build-app.sh 烘进来的就是它）
    env = _from_env_source("MCMTOOLS_HOME")
    if env is not None and _looks_like_repo(env):
        return env

    # 2. 冻结态（PyInstaller 等）
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        cand = Path(frozen).resolve()
        if _looks_like_repo(cand):
            return cand

    # 3. 源码上溯：core/mcmcore/root.py -> core/mcmcore -> core -> <root>
    here = Path(__file__).resolve()
    for parent in here.parents:
        if _looks_like_repo(parent):
            return parent

    # 4. app 包内副本。仓库被删掉、或者 app 被单独拷到别的机器时走这里。
    bundled = _bundled_home()
    if bundled is not None:
        return bundled

    # 5. 兜底：本文件在 <root>/core/mcmcore/ 下，上溯两级
    return here.parents[2]


def core_root() -> Path:
    """``core/`` 目录（Python 包所在处）。"""
    return repo_root() / "core"


def templates_root() -> Path:
    """程序自带的模板库。

    ``MCMTOOLS_TEMPLATES`` 是 `build-app.sh` 为自包含 app 准备的覆盖点：
    app 里带一份 `Contents/Resources/templates`，仓库不在时就用它。

    顺序是"仓库优先，包内兜底"：仓库那一份是开发中的版本，改完立即生效；
    包内那一份是构建时的快照，只在仓库整个不见了（app 被单独拷走）才用。
    """
    env = _from_env_source("MCMTOOLS_TEMPLATES")
    if env is not None:
        return env

    repo = repo_root() / "templates"
    if repo.is_dir():
        return repo

    bundled = _bundle_dir("MCMTOOLS_BUNDLE_TEMPLATES")
    if bundled is not None:
        return bundled
    return repo


def web_root() -> Path:
    """面板静态资源目录（index.html / app.js / app.css）。

    和模板库同样的"仓库优先、包内兜底"。原来是 `parents[2] / "web"`，
    在 .app 里这个上溯根本走不到仓库，面板直接 404 ——
    而服务本身是活的，用户看到的是"页面打不开"而不是"路径错了"。
    """
    env = _from_env_source("MCMTOOLS_WEB")
    if env is not None:
        return env

    repo = repo_root() / "web"
    if (repo / "app.js").is_file():
        return repo

    bundled = _bundle_dir("MCMTOOLS_BUNDLE_WEB")
    if bundled is not None:
        return bundled
    return repo


def template_roots() -> list:
    """模板库的**全部**根目录，按优先级排列。

    自带库在前，用户自定库在后。同一个 template_id 在两处都有时，
    自带库胜出 —— 那是官方版本，行为可预期。

    这样 DIY 存的自定模板（落在用户目录）`git pull` 之后还在，
    而升级时改动过的官方模板不会被旧副本顶掉。
    """
    out = [templates_root()]
    user = user_templates_root()
    if user.is_dir() and user not in out:
        out.append(user)
    return out


def find_template_file(kind: str, name: str, filename: str) -> Optional[Path]:
    """按分区和目录名找到某个模板文件，自带库优先。

    为什么需要它：``figures.py`` / ``paperkit.py`` 原来直接拼
    ``templates_root()/figures/<name>/render.py``。自从 DIY 保存的模板
    落在 ``~/.mcmtools/templates`` 之后，那条路径就找不到它们了 ——
    面板里能选到、预览时却报"找不到绘制代码"，而文件其实好好的。

    所以查找必须**遍历全部根**，而不是只看自带库。
    """
    for root in template_roots():
        p = root / kind / name / filename
        if p.is_file():
            return p
    return None


def describe_paths() -> dict:
    """给面板「设置」页看的路径清单。

    用户报"模板没了"的时候，第一个要问的就是"程序认为模板在哪"。
    把它显示出来，这类问题就不用靠猜。
    """
    troot = templates_root()
    per = {}
    total = 0
    # 目录名是复数（figures/models/...），而 TEMPLATE_KINDS 是单数
    # （figure/model/...）。不映射的话每个分区都数出 0，面板上显示
    # "模板 24 个、figure 0 个"这种自相矛盾的数字。
    for kind, folder in TEMPLATE_FOLDERS.items():
        d = troot / folder
        if not d.is_dir():
            per[kind] = 0
            continue
        n = sum(1 for _ in d.rglob("template.yaml"))
        per[kind] = n
        total += n

    other = []
    for r in template_roots()[1:]:
        n = sum(1 for _ in r.rglob("template.yaml"))
        if n:
            other.append({"path": str(r), "templates": n})

    return {
        "repo_root": str(repo_root()),
        "core_root": str(core_root()),
        "templates_root": str(troot),
        "templates_exists": troot.is_dir(),
        "templates_total": total,
        "templates_per_kind": per,
        "templates_extra_roots": other,
        "web_root": str(web_root()),
        "web_exists": (web_root() / "app.js").is_file(),
        "user_dir": str(user_home_dir()),
        "user_templates_root": str(user_templates_root()),
        "templates_source": os.environ.get("MCMTOOLS_TEMPLATES") or (
            "bundled" if troot == repo_root() / "templates" else "override"),
        "home_source": os.environ.get("MCMTOOLS_HOME") or "detected",
        "app_bundle": _app_bundle_path(),
        "python": sys.executable,
        "python_version": sys.version.split()[0],
    }


def _app_bundle_path() -> Optional[str]:
    """.app 包路径 —— 只在真的从 .app 里跑时才有值。

    启动器会设置 ``MCMTOOLS_APP_BUNDLE``；直接跑 `./start` 时没有。
    """
    return os.environ.get("MCMTOOLS_APP_BUNDLE") or None
