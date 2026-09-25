"""RunStore 的归档、排序、代码指纹与过期检测。

这一层是"结果能不能追溯"的全部依据，所以测试围绕四个具体承诺写：
每次运行独立归档、编号只增不复用、产物原样保存、代码改了要报出来。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from mcmcore.runstore import RunStore, sha256_file, script_fingerprint


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """一个最小项目：一个脚本 + 一个产物文件。"""
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "run.py").write_text("def run(params):\n    return {}\n")
    return tmp_path


class TestSequencing:
    def test_first_run_id(self, project: Path) -> None:
        assert RunStore(project).next_run_id("EXP-001") == "RUN-001-001"

    def test_ids_increment_and_never_reuse(self, project: Path) -> None:
        """编号必须只增不复用 —— 复用了历史就无法信任。"""
        rs = RunStore(project)
        for expected in ("RUN-001-001", "RUN-001-002", "RUN-001-003"):
            rid = rs.next_run_id("EXP-001")
            assert rid == expected
            rs.begin("EXP-001", rid, parameters={})

    def test_gap_in_numbering_is_not_reused(self, project: Path) -> None:
        """删掉中间一次运行后，下一次仍要接着最大编号往后排。"""
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        rs.begin("EXP-001", "RUN-001-002", parameters={})
        rs.begin("EXP-001", "RUN-001-003", parameters={})
        import shutil
        shutil.rmtree(rs.run_dir("EXP-001", "RUN-001-002"))
        assert rs.next_run_id("EXP-001") == "RUN-001-004"

    def test_experiments_are_independent(self, project: Path) -> None:
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        assert rs.next_run_id("EXP-002") == "RUN-002-001"


class TestArchive:
    def test_begin_writes_params_and_meta_before_the_script_runs(
        self, project: Path
    ) -> None:
        """脚本崩溃也不能丢"这里跑过"这件事，所以先写记录。"""
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={"beta": 0.1},
                 condition="beta=0.1", trial_index=1)
        d = rs.run_dir("EXP-001", "RUN-001-001")
        assert json.loads((d / "params.json").read_text()) == {"beta": 0.1}
        meta = json.loads((d / "meta.json").read_text())
        assert meta["condition"] == "beta=0.1"
        assert meta["trial_index"] == 1

    def test_artifacts_are_copied_not_moved(self, project: Path) -> None:
        """脚本可能还要重读自己的输出，所以归档用复制。"""
        src = project / "code" / "out.csv"
        src.write_text("a,b\n1,2\n")
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        saved = rs.collect_artifacts("EXP-001", "RUN-001-001",
                                     ["code/out.csv"], project)
        assert src.exists(), "原文件必须还在"
        assert len(saved) == 1
        assert (project / saved[0]).read_text() == "a,b\n1,2\n"

    def test_duplicate_paths_are_archived_once(self, project: Path) -> None:
        """脚本可能把同一个文件报两次；归档不该出现两份副本。"""
        (project / "code" / "out.csv").write_text("x\n")
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        saved = rs.collect_artifacts(
            "EXP-001", "RUN-001-001",
            ["code/out.csv", "code/out.csv"], project,
        )
        assert len(saved) == 1

    def test_same_name_different_content_is_kept_apart(
        self, project: Path
    ) -> None:
        """同名不同内容要保留两份，绝不覆盖。"""
        (project / "a").mkdir()
        (project / "b").mkdir()
        (project / "a" / "r.csv").write_text("first\n")
        (project / "b" / "r.csv").write_text("second\n")
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        saved = rs.collect_artifacts("EXP-001", "RUN-001-001",
                                     ["a/r.csv", "b/r.csv"], project)
        assert len(saved) == 2
        bodies = sorted((project / s).read_text() for s in saved)
        assert bodies == ["first\n", "second\n"]

    def test_missing_artifact_is_skipped_not_fatal(self, project: Path) -> None:
        """脚本报了一个不存在的文件，归档跳过即可，不该让整次运行失败。"""
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        assert rs.collect_artifacts("EXP-001", "RUN-001-001",
                                    ["nope.csv"], project) == []

    def test_finish_writes_readable_run_yaml(self, project: Path) -> None:
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        rs.finish("EXP-001", "RUN-001-001", status="success",
                  duration_seconds=0.5, exit_code=0,
                  artifact_paths=["runs/EXP-001/RUN-001-001/artifacts/a.csv"],
                  atom_count=5)
        rec = yaml.safe_load(
            (rs.run_dir("EXP-001", "RUN-001-001") / "run.yaml").read_text()
        )
        assert rec["atom_count"] == 5
        assert rec["artifacts"] == ["a.csv"]

    def test_failure_keeps_stderr(self, project: Path) -> None:
        """失败的运行尤其要留下报错，否则无法诊断。"""
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        rs.finish("EXP-001", "RUN-001-001", status="failed",
                  duration_seconds=0.1, exit_code=1, artifact_paths=[],
                  atom_count=0, stderr="ZeroDivisionError: division by zero")
        d = rs.run_dir("EXP-001", "RUN-001-001")
        assert "ZeroDivisionError" in (d / "stderr.txt").read_text()


class TestListing:
    def test_runs_come_back_in_execution_order(self, project: Path) -> None:
        """顺序靠编号而不是时间戳 —— 时钟被改动也不会打乱。"""
        rs = RunStore(project)
        for i in (1, 2, 3, 10):
            rid = f"RUN-001-{i:03d}"
            rs.begin("EXP-001", rid, parameters={})
            rs.finish("EXP-001", rid, status="success", duration_seconds=0.1,
                      exit_code=0, artifact_paths=[], atom_count=0)
        got = [r["run_id"] for r in rs.list_runs("EXP-001")]
        assert got == ["RUN-001-001", "RUN-001-002", "RUN-001-003", "RUN-001-010"]

    def test_declared_artifacts_come_from_disk(self, project: Path) -> None:
        """目录里的实际文件优先于记录里写的 —— 记录可能与磁盘不一致。"""
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        (rs.run_dir("EXP-001", "RUN-001-001") / "artifacts").mkdir(
            parents=True, exist_ok=True
        )
        (rs.run_dir("EXP-001", "RUN-001-001") / "artifacts" / "real.csv"
         ).write_text("x\n")
        rs.finish("EXP-001", "RUN-001-001", status="success",
                  duration_seconds=0.1, exit_code=0, artifact_paths=[],
                  atom_count=0)
        assert rs.list_runs("EXP-001")[0]["artifacts"] == ["real.csv"]

    def test_params_json_is_exposed(self, project: Path) -> None:
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={"beta": 0.25})
        rs.finish("EXP-001", "RUN-001-001", status="success",
                  duration_seconds=0.1, exit_code=0, artifact_paths=[],
                  atom_count=0)
        rec = rs.list_runs("EXP-001")[0]
        assert rec["resolved_parameters"] == {"beta": 0.25}

    def test_no_runs_dir_is_not_an_error(self, tmp_path: Path) -> None:
        assert RunStore(tmp_path).list_runs() == []
        assert RunStore(tmp_path).summary()["total_runs"] == 0

    def test_summary_counts_per_experiment(self, project: Path) -> None:
        rs = RunStore(project)
        for exp, n in (("EXP-001", 2), ("EXP-002", 1)):
            for i in range(1, n + 1):
                rid = f"RUN-{exp.split('-')[-1]}-{i:03d}"
                rs.begin(exp, rid, parameters={})
                rs.finish(exp, rid, status="success", duration_seconds=0.1,
                          exit_code=0, artifact_paths=[], atom_count=0)
        s = rs.summary()
        assert s["total_runs"] == 3
        by = {e["experiment_id"]: e["count"] for e in s["experiments"]}
        assert by == {"EXP-001": 2, "EXP-002": 1}


class TestScriptFingerprint:
    def test_hash_matches_file(self, project: Path) -> None:
        fp = script_fingerprint(project, "code/run.py")
        assert fp["path"] == "code/run.py"
        assert fp["sha256"] == sha256_file(project / "code" / "run.py")
        assert fp["bytes"] > 0

    def test_missing_script_gives_none_hash(self, project: Path) -> None:
        fp = script_fingerprint(project, "code/gone.py")
        assert fp["sha256"] is None


class TestStaleness:
    def _run(self, rs: RunStore, rid: str = "RUN-001-001") -> None:
        rs.begin("EXP-001", rid, parameters={},
                 script=script_fingerprint(rs.root, "code/run.py"))
        rs.finish("EXP-001", rid, status="success", duration_seconds=0.1,
                  exit_code=0, artifact_paths=[], atom_count=0)

    def test_unchanged_code_is_not_stale(self, project: Path) -> None:
        rs = RunStore(project)
        self._run(rs)
        assert rs.staleness(project) == []

    def test_changed_code_is_reported(self, project: Path) -> None:
        """核心承诺：改了脚本，结果必须被标出来是从旧代码来的。"""
        rs = RunStore(project)
        self._run(rs)
        (project / "code" / "run.py").write_text("def run(p):\n    return 1\n")
        out = rs.staleness(project)
        assert len(out) == 1
        assert out[0]["reason"] == "script_changed"
        assert out[0]["experiment_id"] == "EXP-001"
        assert "code/run.py" in out[0]["message"]

    def test_deleted_script_is_reported(self, project: Path) -> None:
        rs = RunStore(project)
        self._run(rs)
        (project / "code" / "run.py").unlink()
        out = rs.staleness(project)
        assert out[0]["reason"] == "script_missing"

    def test_only_the_latest_run_per_experiment_is_compared(
        self, project: Path
    ) -> None:
        """历史运行本来就是旧的，全报出来反而看不出真正的问题。"""
        rs = RunStore(project)
        self._run(rs, "RUN-001-001")
        (project / "code" / "run.py").write_text("# v2\n")
        self._run(rs, "RUN-001-002")   # 用新代码重跑
        assert rs.staleness(project) == [], "重跑之后就不该再报过期"

    def test_run_without_fingerprint_is_ignored(self, project: Path) -> None:
        """老记录没有脚本指纹，跳过而不是误报。"""
        rs = RunStore(project)
        rs.begin("EXP-001", "RUN-001-001", parameters={})
        rs.finish("EXP-001", "RUN-001-001", status="success",
                  duration_seconds=0.1, exit_code=0, artifact_paths=[],
                  atom_count=0)
        assert rs.staleness(project) == []


class TestRunnerSequencing:
    """回归：重跑实验不能复用运行号。

    这里曾经有一个真实的 bug —— runner 用 trial 序号拼 run_id
    （f"RUN-{exp}-{i:03d}"），于是"再跑一次这个实验"会拿到同样的编号，
    新一轮的产物直接倒进旧文件夹。实测连跑三轮后，每个文件夹里堆了
    3 份产物、含不同参数的文件混在一起，而 run.yaml 只记了 1 份。
    归档一旦这样，就完全不能用来追溯了。
    """

    def test_repeated_execution_gets_fresh_ids(self, tmp_path: Path) -> None:
        rs = RunStore(tmp_path)
        seen: list = []
        for _ in range(3):                      # 模拟连跑三轮
            base = int(rs.next_run_id("EXP-001").rsplit("-", 1)[-1]) - 1
            for i in (1, 2, 3):                 # 每轮三个 trial
                rid = f"RUN-001-{base + i:03d}"
                seen.append(rid)
                rs.begin("EXP-001", rid, parameters={"trial": i})
                rs.finish("EXP-001", rid, status="success",
                          duration_seconds=0.1, exit_code=0,
                          artifact_paths=[], atom_count=0)
        assert seen == [f"RUN-001-{i:03d}" for i in range(1, 10)]
        assert len(set(seen)) == 9, "运行号必须互不相同"

    def test_no_folder_receives_two_runs(self, tmp_path: Path) -> None:
        """每个文件夹只能属于一次运行 —— 这正是"永不覆盖"的含义。"""
        rs = RunStore(tmp_path)
        (tmp_path / "out.csv").write_text("first\n")
        base = int(rs.next_run_id("EXP-001").rsplit("-", 1)[-1]) - 1
        rid = f"RUN-001-{base + 1:03d}"
        rs.begin("EXP-001", rid, parameters={})
        rs.collect_artifacts("EXP-001", rid, ["out.csv"], tmp_path)

        # 第二次运行必须落到别的文件夹，不能追加到上面那个
        base2 = int(rs.next_run_id("EXP-001").rsplit("-", 1)[-1]) - 1
        assert base2 == base + 1
        rid2 = f"RUN-001-{base2 + 1:03d}"
        rs.begin("EXP-001", rid2, parameters={})
        d1 = rs.run_dir("EXP-001", rid) / "artifacts"
        assert len(list(d1.iterdir())) == 1, "旧运行的产物不该被改动"
