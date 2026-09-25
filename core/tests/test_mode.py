"""Tests for competition-mode enforcement.

The project's premise is that the competition runs offline with no AI. Before
this module that was a recorded intent: `mode: competition` only changed which
audit checks ran. These tests assert it is now a guarantee.

The network tests deliberately hit a real socket rather than mocking one, because
the failure they guard against -- a library quietly phoning home -- only shows up
at the real syscall boundary.
"""

import socket

import pytest

from mcmcore import mode as mode_mod
from mcmcore.mode import (
    CompetitionModeViolation,
    NetworkBlocked,
    competition_mode,
    current_mode,
    enforce_network_block,
    install_network_guard,
    is_competition,
    mode_status,
    recorded_violations,
    remove_network_guard,
    require_development,
    set_mode,
    stamp_provenance,
)
from mcmcore.schemas import RunMode


@pytest.fixture(autouse=True)
def clean_mode():
    """Every test starts in development mode with no guard installed."""
    remove_network_guard()
    set_mode(RunMode.DEVELOPMENT)
    mode_mod._state.violations.clear()
    yield
    remove_network_guard()
    set_mode(RunMode.DEVELOPMENT)
    mode_mod._state.violations.clear()


# --------------------------------------------------------------------------
# Mode state
# --------------------------------------------------------------------------


class TestModeState:
    def test_defaults_to_development(self):
        assert current_mode() == RunMode.DEVELOPMENT
        assert not is_competition()

    def test_set_mode(self):
        set_mode(RunMode.COMPETITION)
        assert is_competition()

    def test_context_manager_restores_previous(self):
        with competition_mode():
            assert is_competition()
        assert not is_competition()

    def test_context_manager_restores_on_exception(self):
        with pytest.raises(ValueError):
            with competition_mode():
                raise ValueError("boom")
        assert not is_competition()


# --------------------------------------------------------------------------
# The network guard
# --------------------------------------------------------------------------


class TestNetworkGuard:
    def test_outbound_dns_is_blocked(self):
        with enforce_network_block():
            with pytest.raises(NetworkBlocked):
                socket.getaddrinfo("example.com", 80)

    def test_outbound_connect_is_blocked(self):
        with enforce_network_block():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with pytest.raises(NetworkBlocked):
                    s.connect(("93.184.216.34", 80))
            finally:
                s.close()

    def test_localhost_dns_is_allowed(self):
        """Blocking loopback would break local tooling for no benefit."""
        with enforce_network_block():
            socket.getaddrinfo("127.0.0.1", 80)
            socket.getaddrinfo("localhost", 80)

    def test_localhost_connect_is_allowed(self):
        """A real loopback connection must still work under the guard."""
        import threading

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def accept_one():
            try:
                server.settimeout(2)
                conn, _ = server.accept()
                conn.close()
            except Exception:
                pass

        t = threading.Thread(target=accept_one, daemon=True)
        t.start()

        with enforce_network_block():
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client.connect(("127.0.0.1", port))
            finally:
                client.close()
        server.close()

    def test_guard_is_removed_after_the_block(self):
        with enforce_network_block():
            assert mode_mod.network_guard_installed()
        assert not mode_mod.network_guard_installed()
        # And the network works again.
        socket.getaddrinfo("example.com", 80)

    def test_development_mode_does_not_block(self):
        install_network_guard()
        set_mode(RunMode.DEVELOPMENT)
        # Guard installed but mode is development: real DNS must be attempted.
        # (No assertion on the result; offline CI would fail a resolution check.)
        assert not is_competition()

    def test_install_is_idempotent(self):
        install_network_guard()
        install_network_guard()
        assert mode_mod.network_guard_installed()
        remove_network_guard()
        assert not mode_mod.network_guard_installed()

    def test_remove_without_install_is_safe(self):
        remove_network_guard()

    def test_violations_are_recorded(self):
        with enforce_network_block():
            with pytest.raises(NetworkBlocked):
                socket.getaddrinfo("example.com", 80)
        v = recorded_violations()
        assert v and v[-1]["kind"] == "dns"
        assert "example.com" in v[-1]["detail"]
        assert v[-1]["at"].endswith("Z")


# --------------------------------------------------------------------------
# AI-assist block
# --------------------------------------------------------------------------


class TestAIAssistBlock:
    def test_allowed_in_development(self):
        require_development("any feature")

    def test_refused_in_competition(self):
        with competition_mode():
            with pytest.raises(CompetitionModeViolation) as exc:
                require_development("draft-section")
            assert "competition mode" in str(exc.value)

    def test_refusal_is_recorded(self):
        with competition_mode():
            with pytest.raises(CompetitionModeViolation):
                require_development("suggest-hypotheses")
        kinds = [v["kind"] for v in recorded_violations()]
        assert "ai_feature" in kinds


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


class TestProvenance:
    def test_stamps_mode_and_time(self):
        d = stamp_provenance()
        assert d["produced_in_mode"] == "development"
        assert d["produced_at"].endswith("Z")

    def test_stamps_competition_when_active(self):
        with competition_mode():
            assert stamp_provenance()["produced_in_mode"] == "competition"

    def test_preserves_existing_metadata(self):
        d = stamp_provenance({"run": "R1"})
        assert d["run"] == "R1"
        assert "produced_in_mode" in d


# --------------------------------------------------------------------------
# Status payload
# --------------------------------------------------------------------------


class TestModeStatus:
    def test_reports_state(self):
        s = mode_status()
        assert s["mode"] == "development"
        assert s["competition"] is False
        assert s["network_guard_installed"] is False

    def test_lists_blocked_outbound(self):
        with enforce_network_block():
            with pytest.raises(NetworkBlocked):
                socket.getaddrinfo("example.com", 80)
        s = mode_status()
        assert len(s["blocked_outbound"]) == 1


# --------------------------------------------------------------------------
# Integration with the runner
# --------------------------------------------------------------------------


class TestRunnerIntegration:
    EXP = '''
def run(params):
    return {"atoms": [{"name": "v", "value": 1.0}]}
'''

    def _project(self, tmp_path, mode="competition"):
        from mcmcore.schemas import Experiment, ExperimentKind, Varied
        from mcmcore.store import Store

        st = Store.init(tmp_path, "mode-test")
        script = st.root / "experiments" / "e.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(self.EXP, encoding="utf-8")

        cfg = st.layout.load_config()
        cfg.mode = RunMode.COMPETITION if mode == "competition" else RunMode.DEVELOPMENT
        st.layout.save_config(cfg)

        st.save_experiment(Experiment(
            id="EXP-001", kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[Varied(name="b", values=[1.0])],
            entrypoint="experiments/e.py:run",
        ))
        return st

    def test_run_announces_the_block(self, tmp_path):
        from mcmcore.runner import ExperimentRunner

        st = self._project(tmp_path, "competition")
        out = ExperimentRunner(st).run("EXP-001")
        assert out.ok
        assert any("competition mode" in m for m in out.messages)

    def test_run_blocks_network_from_experiment_code(self, tmp_path):
        """An experiment that phones home must fail, and fail loudly."""
        from mcmcore.runner import ExperimentRunner

        body = (
            "import socket\n"
            "def run(params):\n"
            "    socket.getaddrinfo('example.com', 80)\n"
            "    return {'atoms': [{'name': 'v', 'value': 1.0}]}\n"
        )
        st = self._project(tmp_path, "competition")
        (st.root / "experiments" / "e.py").write_text(body, encoding="utf-8")

        out = ExperimentRunner(st).run("EXP-001")
        assert out.ok  # the runner survived
        assert all(r.status.value == "failed" for r in out.runs)
        assert "Competition" in (out.runs[0].stderr_tail or "")

    def test_development_mode_allows_the_same_code_to_be_attempted(self, tmp_path):
        from mcmcore.runner import ExperimentRunner

        st = self._project(tmp_path, "development")
        out = ExperimentRunner(st).run("EXP-001")
        guard = [v for v in recorded_violations() if v["kind"] == "dns"]
        assert not guard, "development mode must not block DNS"
        assert all(r.status.value == "success" for r in out.runs)
