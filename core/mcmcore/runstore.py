"""Each run gets its own folder, and nothing is ever overwritten.

The problem this solves
-----------------------
A competition paper is defended months later, and the first question anyone
asks is "where did that number come from?". If a run overwrites the previous
run's output, the answer is gone. So every execution writes a NEW folder:

    runs/EXP-001/RUN-001-001/
        run.yaml          完整记录：参数、耗时、状态、产生的原子
        params.json       本次运行实际用的参数（可直接喂给脚本）
        stdout.txt        脚本输出
        stderr.txt        脚本报错（失败运行尤其重要）
        artifacts/        脚本产出的文件，原样保存
        meta.json         脚本指纹：路径 + 内容哈希

Why a content hash
------------------
``artifact_paths`` existed in the Run schema from the start but was never
filled in, so a run record could not point at anything. Storing the hash means
a figure can be traced back to the exact script revision that drew it -- and
when the script changes, we can say so instead of guessing.

Ordering
--------
Run ids are sequential (``RUN-001-001``, ``RUN-001-002``, ...) and the folder
name IS the run id, so sorting folder names gives execution order with no
extra bookkeeping. A re-run of the same experiment appends; it never reuses a
number, which is what makes the history trustworthy.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .store import _to_plain

RUNS_DIRNAME = "runs"


def sha256_file(path: Path) -> Optional[str]:
    """内容哈希；文件不存在时返回 None（而不是抛异常）。"""
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def script_fingerprint(root: Path, script_rel: str) -> Dict[str, Any]:
    """记录脚本路径与内容哈希，让结果能追回"是哪一版代码算的"。"""
    p = (root / script_rel) if not Path(script_rel).is_absolute() else Path(script_rel)
    return {
        "path": script_rel,
        "sha256": sha256_file(p),
        "bytes": p.stat().st_size if p.is_file() else None,
    }


class RunStore:
    """把一次运行落成一个文件夹。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.base = self.root / RUNS_DIRNAME

    # ------------------------------------------------------------ 路径
    def run_dir(self, experiment_id: str, run_id: str) -> Path:
        return self.base / experiment_id / run_id

    def next_run_id(self, experiment_id: str) -> str:
        """下一个可用的运行号。**只增不减** —— 不复用编号。"""
        short = experiment_id.split("-")[-1]
        existing = self.base / experiment_id
        highest = 0
        if existing.is_dir():
            for child in existing.iterdir():
                if not child.is_dir():
                    continue
                tail = child.name.rsplit("-", 1)[-1]
                if tail.isdigit():
                    highest = max(highest, int(tail))
        return f"RUN-{short}-{highest + 1:03d}"

    # ------------------------------------------------------------ 写入
    def begin(
        self,
        experiment_id: str,
        run_id: str,
        *,
        parameters: Dict[str, Any],
        script: Optional[Dict[str, Any]] = None,
        trial_index: Optional[int] = None,
        condition: Optional[str] = None,
        random_seed: Optional[int] = None,
    ) -> Path:
        """建好文件夹并写下"运行前"就知道的信息。

        先写 meta，再跑脚本 —— 这样即使脚本崩了、机器断电了，
        这个文件夹也能说明"这里本该有一次运行"。
        """
        d = self.run_dir(experiment_id, run_id)
        (d / "artifacts").mkdir(parents=True, exist_ok=True)

        (d / "params.json").write_text(
            json.dumps(parameters, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        meta = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "trial_index": trial_index,
            "condition": condition,
            "random_seed": random_seed,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "script": script or {},
        }
        (d / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return d

    def collect_artifacts(
        self, experiment_id: str, run_id: str, paths: List[str], root: Path
    ) -> List[str]:
        """把脚本产出的文件复制进本次运行的 artifacts/。

        用复制而不是移动：脚本可能还要重读自己的输出，而且用户习惯在
        原位置找文件。复制一份是为了让历史运行**自包含** —— 半年后
        只看这个文件夹就知道当时产出了什么。
        """
        d = self.run_dir(experiment_id, run_id) / "artifacts"
        d.mkdir(parents=True, exist_ok=True)
        saved: List[str] = []
        seen: set = set()
        for rel in paths:
            src = Path(rel)
            if not src.is_absolute():
                # 相对路径的基准有歧义：脚本眼里是"相对当前工作目录"，
                # 而 runner 眼里是"相对项目根目录"。两种都要能解析，
                # 否则脚本报出来的产物会被静默丢掉。
                # 先按项目根试，再按 cwd 试。
                cand = root / rel
                if not cand.is_file():
                    alt = Path.cwd() / rel
                    if alt.is_file():
                        cand = alt
                src = cand
            if not src.is_file():
                continue
            # 去重：脚本可能把同一个文件报了两次（例如在多次调用间累积列表）。
            # 不去重就会归档出 file.csv 和 file_1.csv 两份同样的内容。
            key = str(src.resolve())
            if key in seen:
                continue
            seen.add(key)
            dest = d / src.name
            # 同名但内容不同的文件加序号，绝不覆盖。
            n = 1
            while dest.exists():
                dest = d / f"{src.stem}_{n}{src.suffix}"
                n += 1
            shutil.copy2(src, dest)
            saved.append(str(dest.relative_to(root)))
        return saved

    def finish(
        self,
        experiment_id: str,
        run_id: str,
        *,
        status: str,
        duration_seconds: Optional[float],
        exit_code: Optional[int],
        artifact_paths: List[str],
        atom_count: int,
        stdout: str = "",
        stderr: str = "",
    ) -> Path:
        """写下"运行后"才知道的信息，并生成给人看的 run.yaml。"""
        d = self.run_dir(experiment_id, run_id)
        d.mkdir(parents=True, exist_ok=True)

        if stdout:
            (d / "stdout.txt").write_text(stdout, encoding="utf-8", errors="replace")
        if stderr:
            (d / "stderr.txt").write_text(stderr, encoding="utf-8", errors="replace")

        record = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "status": status,
            "duration_seconds": duration_seconds,
            "exit_code": exit_code,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "atom_count": atom_count,
            "artifacts": [Path(p).name for p in artifact_paths],
            "artifact_paths": artifact_paths,
        }
        # 走 _to_plain：numpy 标量、枚举都要先转成普通类型，
        # 否则 safe_dump 会在归档阶段抛错（脚本其实已经跑完了）。
        (d / "run.yaml").write_text(
            yaml.safe_dump(_to_plain(record), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return d

    # ------------------------------------------------------------ 读取
    def list_runs(self, experiment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """按执行顺序返回运行记录（新的在后）。

        排序靠文件夹名的数字后缀，不靠时间戳 —— 时间戳会因时钟调整而错乱，
        编号不会。
        """
        if not self.base.is_dir():
            return []
        result: List[Dict[str, Any]] = []
        exps = [experiment_id] if experiment_id else [
            p.name for p in sorted(self.base.iterdir()) if p.is_dir()
        ]
        for exp in exps:
            exp_dir = self.base / exp
            if not exp_dir.is_dir():
                continue
            for child in sorted(exp_dir.iterdir()):
                if not child.is_dir():
                    continue
                rec: Dict[str, Any] = {"run_id": child.name, "experiment_id": exp}
                run_yaml = child / "run.yaml"
                meta_json = child / "meta.json"
                if run_yaml.is_file():
                    try:
                        rec.update(yaml.safe_load(run_yaml.read_text(encoding="utf-8")) or {})
                    except Exception:
                        pass
                if meta_json.is_file():
                    try:
                        m = json.loads(meta_json.read_text(encoding="utf-8"))
                        rec.setdefault("started_at", m.get("started_at"))
                        rec["trial_index"] = m.get("trial_index")
                        rec["condition"] = m.get("condition")
                        rec["script"] = m.get("script")
                    except Exception:
                        pass
                # 参数单独存在 params.json 里 —— 它同时也是"能直接重跑这次
                # 运行"的输入，所以不从 runs.yaml 里重复一份。
                params_json = child / "params.json"
                if params_json.is_file():
                    try:
                        rec["resolved_parameters"] = json.loads(
                            params_json.read_text(encoding="utf-8")
                        )
                    except Exception:
                        pass
                # 目录里的实际文件永远优先于记录里写的
                art_dir = child / "artifacts"
                rec["artifacts"] = (
                    sorted(p.name for p in art_dir.iterdir() if p.is_file())
                    if art_dir.is_dir() else []
                )
                rec["dir"] = str(child.relative_to(self.root))
                rec["sort_key"] = _seq(child.name)
                result.append(rec)

        result.sort(key=lambda r: (r["experiment_id"], r["sort_key"]))
        return result

    def summary(self) -> Dict[str, Any]:
        """给面板用的汇总：每个实验跑了多少次、最近一次是什么时候。"""
        runs = self.list_runs()
        by_exp: Dict[str, Dict[str, Any]] = {}
        for r in runs:
            e = by_exp.setdefault(
                r["experiment_id"], {"experiment_id": r["experiment_id"], "count": 0}
            )
            e["count"] += 1
            e["last_run_id"] = r["run_id"]
            e["last_status"] = r.get("status")
            e["last_at"] = r.get("finished_at") or r.get("started_at")
            e["last_artifacts"] = len(r.get("artifacts") or [])
        return {
            "total_runs": len(runs),
            "experiments": sorted(by_exp.values(), key=lambda x: x["experiment_id"]),
        }


    # ------------------------------------------------------- 自动识别过期
    def staleness(self, root: Path) -> List[Dict[str, Any]]:
        """找出"代码改过、但结果还是旧的"的那些实验。

        这是整个归档机制存在的理由：跑了实验、拿到结果，然后又改了脚本 ——
        此时 runs/ 里的结果是**旧代码**算出来的，但磁盘上没有任何迹象。
        手工做建模最常出的错就是这个：论文里的图和代码对不上。

        判据只有一条：本次运行记录的脚本哈希 ≠ 当前脚本哈希。
        """
        runs = self.list_runs()
        # 每个实验取最近一次运行来比。历史运行本来就会"过期"，
        # 拿它们比较会把每条都报成过期，反而看不出问题。
        latest: Dict[str, Dict[str, Any]] = {}
        for r in runs:
            latest[r["experiment_id"]] = r  # list_runs 已按序号升序

        out: List[Dict[str, Any]] = []
        for exp_id, rec in sorted(latest.items()):
            script = rec.get("script") or {}
            rel = script.get("path")
            if not rel:
                continue
            recorded = script.get("sha256")
            current = sha256_file(root / rel)
            if current is None:
                out.append({
                    "experiment_id": exp_id,
                    "run_id": rec["run_id"],
                    "script": rel,
                    "reason": "script_missing",
                    "message": f"脚本 {rel} 已不存在，但运行记录还在。"
                               "要么恢复文件，要么重跑。",
                })
            elif recorded and current != recorded:
                out.append({
                    "experiment_id": exp_id,
                    "run_id": rec["run_id"],
                    "script": rel,
                    "reason": "script_changed",
                    "message": f"{rel} 在 {rec['run_id']} 之后被改过，"
                               "这次运行的结果来自旧代码。请重跑该实验。",
                })
        return out


def _seq(run_id: str) -> int:
    tail = run_id.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0
