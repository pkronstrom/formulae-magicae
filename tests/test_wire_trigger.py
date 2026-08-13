"""Standalone wire-trigger skill behavior."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.client import IncompleteRead
from pathlib import Path

import pytest

WIRE_PATH = Path(__file__).resolve().parents[1] / "skills/wire-trigger/wire.py"
SKILL_PATH = WIRE_PATH.with_name("SKILL.md")


def load_wire():
    spec = importlib.util.spec_from_file_location("wire_trigger", WIRE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wire():
    return load_wire()


@pytest.fixture
def paths(wire, tmp_path):
    return wire.resolve_paths(
        {
            "WIRE_TRIGGER_STATE_HOME": str(tmp_path / "state"),
            "WIRE_TRIGGER_CONFIG_HOME": str(tmp_path / "config"),
            "WIRE_TRIGGER_RUNTIME_HOME": str(tmp_path / "runtime"),
        }
    )


def test_paths_prefer_explicit_overrides(wire, tmp_path):
    paths = wire.resolve_paths(
        {
            "WIRE_TRIGGER_STATE_HOME": str(tmp_path / "state"),
            "WIRE_TRIGGER_CONFIG_HOME": str(tmp_path / "config"),
            "WIRE_TRIGGER_RUNTIME_HOME": str(tmp_path / "runtime"),
        }
    )
    assert paths.state == tmp_path / "state"
    assert paths.config == tmp_path / "config"
    assert paths.runtime == tmp_path / "runtime"


@pytest.mark.parametrize("value", ["", "relative/cache"])
def test_paths_ignore_empty_or_relative_xdg(wire, monkeypatch, tmp_path, value):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    paths = wire.resolve_paths(
        {
            "XDG_STATE_HOME": value,
            "XDG_CONFIG_HOME": value,
            "TMPDIR": str(tmp_path / "tmp"),
        },
        platform="linux",
    )
    assert paths.state == tmp_path / "home" / ".local/state/wire-trigger"
    assert paths.config == tmp_path / "home" / ".config/wire-trigger"


def test_create_task_is_private_and_metadata_free(wire, paths, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    task = wire.create_task(
        paths,
        summary="Re-review PR 7",
        prompt="Re-review PR 7 now.",
        cwd=repo,
        target={"kind": "session", "tool": "codex", "session_id": "thread-7"},
        allow_unconfirmed_get=True,
        allow_session_permissions=True,
        start_listener=False,
    )
    task_path = paths.tasks / f"{task['id']}.json"
    assert task["state"] == "armed"
    assert task["revision"] == 1
    assert task["transport"]["topic"].startswith("wt_")
    assert "Re-review" not in task["transport"]["topic"]
    assert len(task["transport"]["topic"]) >= 40
    assert stat.S_IMODE(task_path.stat().st_mode) == 0o600
    assert json.loads(task_path.read_text()) == task


def test_create_task_arms_two_minutes_after_creation(
    wire, paths, tmp_path, monkeypatch
):
    created = datetime(2026, 8, 13, 8, 0, 0, 750000, tzinfo=timezone.utc)
    monkeypatch.setattr(wire, "utc_now", lambda: created)

    task = wire.create_task(
        paths,
        summary="Re-review",
        prompt="Review now",
        cwd=tmp_path,
        target={"kind": "foreground"},
        allow_unconfirmed_get=True,
    )

    assert wire.parse_time(task["arm_at"]) == datetime(
        2026, 8, 13, 8, 2, 1, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (-1, False),
        (0, True),
        (1, True),
    ],
)
def test_event_is_eligible_at_arm_boundary(wire, monkeypatch, offset, expected):
    arm_at = datetime(2026, 8, 13, 8, 2, tzinfo=timezone.utc)
    message_time = arm_at + timedelta(seconds=offset)
    monkeypatch.setattr(wire, "utc_now", lambda: arm_at)

    assert wire.event_is_eligible(
        {"arm_at": wire.iso(arm_at)},
        {"time": message_time.timestamp()},
    ) is expected


@pytest.mark.parametrize("published", [None, "1786608120", True, float("inf")])
def test_event_is_eligible_rejects_invalid_new_task_timestamps(wire, published):
    assert wire.event_is_eligible(
        {"arm_at": "2026-08-13T08:02:00Z"},
        {"time": published},
    ) is False


def test_event_is_eligible_accepts_legacy_task_without_arm_at(wire):
    assert wire.event_is_eligible({}, {}) is True


def test_event_is_ineligible_before_local_arm_even_if_server_clock_is_ahead(
    wire, monkeypatch
):
    arm_at = datetime(2026, 8, 13, 8, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(wire, "utc_now", lambda: arm_at - timedelta(seconds=1))

    assert wire.event_is_eligible(
        {"arm_at": wire.iso(arm_at)},
        {"time": (arm_at + timedelta(minutes=5)).timestamp()},
    ) is False


def test_create_refuses_unacknowledged_direct_get(wire, paths, tmp_path):
    with pytest.raises(wire.UnsafeTriggerError, match="unconfirmed"):
        wire.create_task(
            paths,
            summary="Review",
            prompt="Review now",
            cwd=tmp_path,
            target={"kind": "fresh", "tool": "codex"},
            start_listener=False,
        )


def test_session_target_requires_permission_acknowledgement(wire, paths, tmp_path):
    with pytest.raises(wire.UnsafeTriggerError, match="session"):
        wire.create_task(
            paths,
            summary="Review",
            prompt="Review now",
            cwd=tmp_path,
            target={"kind": "session", "tool": "codex", "session_id": "x"},
            allow_unconfirmed_get=True,
            start_listener=False,
        )


def test_create_refuses_missing_working_directory(wire, paths, tmp_path):
    with pytest.raises(wire.WireError, match="working directory"):
        wire.create_task(
            paths,
            summary="Review",
            prompt="Review now",
            cwd=tmp_path / "missing",
            target={"kind": "fresh", "tool": "codex"},
            allow_unconfirmed_get=True,
            start_listener=False,
        )


def test_detects_exact_codex_thread_from_environment(wire):
    assert wire.detect_current_session("codex", {"CODEX_THREAD_ID": "abc"}) == "abc"


def test_refuses_to_guess_current_session(wire):
    with pytest.raises(wire.SessionUnavailableError, match="exact"):
        wire.detect_current_session("claude", {})


def test_foreground_target_is_tool_neutral(wire):
    assert wire.normalize_target({"kind": "foreground"}) == {"kind": "foreground"}


def test_foreground_target_cannot_build_agent_command(wire):
    with pytest.raises(wire.WireError, match="foreground"):
        wire.build_agent_command(
            {"target": {"kind": "foreground"}, "prompt": "Review now"}
        )


@pytest.mark.parametrize(
    ("tool", "session_id", "prefix"),
    [
        ("codex", "c1", ["codex", "exec", "resume", "c1"]),
        ("claude", "c2", ["claude", "--resume", "c2", "-p"]),
        ("agy", "c3", ["agy", "--print", "--conversation", "c3"]),
        ("opencode", "c4", ["opencode", "run", "--session", "c4"]),
    ],
)
def test_session_adapter_commands_are_exact_argv(wire, tool, session_id, prefix):
    task = {
        "target": {"kind": "session", "tool": tool, "session_id": session_id},
        "prompt": "review now",
    }
    argv = wire.build_agent_command(task)
    assert argv[: len(prefix)] == prefix
    assert argv[-1] == "review now"
    assert "--last" not in argv and "--continue" not in argv


@pytest.mark.parametrize(
    ("tool", "prefix"),
    [
        ("codex", ["codex", "exec", "-s", "read-only"]),
        ("claude", ["claude", "-p", "--permission-mode", "plan"]),
        ("agy", ["agy", "--print", "--mode", "plan"]),
        ("opencode", ["opencode", "run"]),
    ],
)
def test_fresh_adapter_commands_default_to_read_only(wire, tool, prefix):
    task = {"target": {"kind": "fresh", "tool": tool}, "prompt": "review now"}
    argv = wire.build_agent_command(task)
    assert argv[: len(prefix)] == prefix
    assert argv[-1] == "review now"


def test_explicit_executable_override_changes_only_program(wire):
    task = {
        "target": {
            "kind": "session",
            "tool": "codex",
            "session_id": "c1",
            "executable": "/opt/codex",
        },
        "prompt": "review now",
    }
    assert wire.build_agent_command(task)[0] == "/opt/codex"


def test_executor_kind_requires_explicit_tool(wire):
    with pytest.raises(wire.WireError, match="executor"):
        wire.normalize_target({"kind": "executor"})


def make_task(wire, paths, tmp_path, *, executable=None):
    target = {"kind": "fresh", "tool": "codex"}
    if executable:
        target["executable"] = str(executable)
    return wire.create_task(
        paths,
        summary="Review",
        prompt="Review now",
        cwd=tmp_path,
        target=target,
        allow_unconfirmed_get=True,
        start_listener=False,
    )


def executable_script(path: Path, body: str) -> Path:
    path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_only_first_claim_wins(wire, paths, tmp_path):
    task = make_task(wire, paths, tmp_path)
    first = wire.claim_task(paths, task["id"], message_id="m1")
    second = wire.claim_task(paths, task["id"], message_id="m1")
    assert first["generation"] == 1
    assert second is None
    saved = wire.load_task(paths, task["id"])
    assert saved["state"] == "claimed"
    assert saved["claim_generation"] == 1


def test_orphaned_durable_claim_becomes_uncertain_without_overwrite(wire, paths, tmp_path):
    task = make_task(wire, paths, tmp_path)
    claim_dir = paths.claims / task["id"]
    wire.ensure_private_dir(claim_dir)
    orphan = {
        "task_id": task["id"],
        "generation": 1,
        "attempt_id": "orphan-attempt",
        "message_id": "m1",
        "claimed_at": wire.iso(wire.utc_now()),
        "target": task["target"],
        "revision": 2,
    }
    wire.atomic_write_json(claim_dir / "1.json", orphan)
    before = (claim_dir / "1.json").read_bytes()

    assert wire.claim_task(paths, task["id"], message_id="m1-replay") is None
    recovered = wire.load_task(paths, task["id"])
    assert recovered["state"] == "uncertain"
    assert recovered["claim_generation"] == 1
    assert recovered["latest_run"] == "orphan-attempt"
    assert (claim_dir / "1.json").read_bytes() == before


def test_listener_restart_marks_interrupted_claim_uncertain(wire, paths, tmp_path):
    task = make_task(wire, paths, tmp_path)
    wire.claim_task(paths, task["id"], message_id="m1")
    assert wire.load_task(paths, task["id"])["state"] == "claimed"

    assert wire.active_topic_groups(paths) == {}
    assert wire.load_task(paths, task["id"])["state"] == "uncertain"


def test_expired_task_cannot_be_claimed(wire, paths, tmp_path):
    task = make_task(wire, paths, tmp_path)
    task["expires_at"] = wire.iso(datetime.now(timezone.utc) - timedelta(seconds=1))
    wire.save_task(paths, task)
    assert wire.claim_task(paths, task["id"], message_id="m1") is None
    assert wire.load_task(paths, task["id"])["state"] == "expired"


def test_attach_and_cancel_share_the_claim_boundary(wire, paths, tmp_path):
    task = make_task(wire, paths, tmp_path)
    attached = wire.attach_task(
        paths,
        task["id"],
        {"kind": "session", "tool": "codex", "session_id": "new-thread"},
        allow_session_permissions=True,
    )
    assert attached["target"]["session_id"] == "new-thread"
    wire.claim_task(paths, task["id"], message_id="m1")
    with pytest.raises(wire.StateError, match="claimed"):
        wire.cancel_task(paths, task["id"])
    with pytest.raises(wire.StateError, match="claimed"):
        wire.attach_task(
            paths,
            task["id"],
            {"kind": "fresh", "tool": "claude"},
        )


def test_attach_session_target_requires_permission_acknowledgement(
    wire, paths, tmp_path
):
    task = make_task(wire, paths, tmp_path)

    with pytest.raises(wire.UnsafeTriggerError, match="session"):
        wire.attach_task(
            paths,
            task["id"],
            {"kind": "session", "tool": "codex", "session_id": "new-thread"},
        )


def test_task_lock_ignores_a_persistent_file_left_after_process_exit(wire, paths):
    lock = paths.runtime / "task-locks" / "trg_stale.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("abandoned metadata")

    with wire.task_lock(paths, "trg_stale", timeout=0.1):
        assert lock.is_file()

    assert lock.is_file()


def test_task_lock_never_steals_from_a_live_old_holder(wire, paths):
    lock = paths.runtime / "task-locks" / "trg_live.lock"

    with wire.task_lock(paths, "trg_live", timeout=0.1):
        os.utime(lock, (0, 0))
        with pytest.raises(wire.StateError, match="busy"):
            with wire.task_lock(paths, "trg_live", timeout=0.02):
                pytest.fail("stole a live lock")


def test_cancelled_task_cannot_be_claimed(wire, paths, tmp_path):
    task = make_task(wire, paths, tmp_path)
    cancelled = wire.cancel_task(paths, task["id"])
    assert cancelled["state"] == "cancelled"
    assert wire.claim_task(paths, task["id"], message_id="m1") is None


def test_dispatch_captures_output_and_completion(wire, paths, tmp_path):
    fake = executable_script(
        tmp_path / "fake-agent",
        "import sys; print('review complete'); print('diagnostic', file=sys.stderr)",
    )
    task = make_task(wire, paths, tmp_path, executable=fake)
    claim = wire.claim_task(paths, task["id"], message_id="m1")
    run = wire.dispatch_claim(paths, task["id"], claim["generation"])
    assert run["classification"] == "completed"
    saved = wire.load_task(paths, task["id"])
    assert saved["state"] == "completed"
    run_dir = paths.runs / task["id"] / run["attempt_id"]
    assert "review complete" in (run_dir / "stdout.log").read_text()
    assert "diagnostic" in (run_dir / "stderr.log").read_text()


def test_failed_dispatch_retries_with_new_generation(wire, paths, tmp_path):
    marker = tmp_path / "attempt"
    fake = executable_script(
        tmp_path / "flaky-agent",
        (
            "import pathlib, sys; p=pathlib.Path(" + repr(str(marker)) + "); "
            "seen=p.exists(); p.write_text('x'); print('again' if seen else 'fail'); "
            "raise SystemExit(0 if seen else 9)"
        ),
    )
    task = make_task(wire, paths, tmp_path, executable=fake)
    first_claim = wire.claim_task(paths, task["id"], message_id="m1")
    first = wire.dispatch_claim(paths, task["id"], first_claim["generation"])
    assert first["classification"] == "failed"
    second = wire.retry_task(paths, task["id"])
    assert second["classification"] == "completed"
    assert wire.load_task(paths, task["id"])["claim_generation"] == 2
    assert (paths.claims / task["id"] / "1.json").exists()
    assert (paths.claims / task["id"] / "2.json").exists()


def test_subscription_url_contains_only_topics_and_cursor(wire):
    url = wire.subscription_url(
        "https://ntfy.sh", ["wt_z", "wt_a"], since="msg-1"
    )
    assert url == "https://ntfy.sh/wt_a,wt_z/json?poll=1&since=msg-1"


def test_stream_subscription_url_omits_poll(wire):
    url = wire.subscription_url(
        "https://ntfy.sh", ["wt_a"], since="msg-1", poll=False
    )
    assert url == "https://ntfy.sh/wt_a/json?since=msg-1"


def make_foreground_task(wire, paths, tmp_path, *, grace=False):
    task = wire.create_task(
        paths,
        summary="Re-review",
        prompt="Review now",
        cwd=tmp_path,
        target={"kind": "foreground"},
        allow_unconfirmed_get=True,
    )
    if not grace:
        task.pop("arm_at")
        wire.save_task(paths, task)
    return task


def event_time(wire, task, offset=0):
    return wire.parse_time(task["arm_at"]).timestamp() + offset


def response_for(*events):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            return iter(json.dumps(event).encode() + b"\n" for event in events)

    return Response()


def test_wait_returns_prompt_without_launching_agent(
    wire, paths, tmp_path, monkeypatch
):
    task = make_foreground_task(wire, paths, tmp_path)
    topic = task["transport"]["topic"]
    events = (
        {"event": "open", "id": "open-1", "topic": topic},
        {"event": "keepalive", "id": "keep-1", "topic": topic},
        {"event": "message", "id": "wrong", "topic": "wt_someone_else"},
        {"event": "message", "id": "msg-1", "topic": topic},
    )
    monkeypatch.setattr(
        wire.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("foreground wait launched an agent"),
    )
    requested = []

    payload = wire.wait_for_task(
        paths,
        task["id"],
        opener=lambda url, timeout: requested.append(url) or response_for(*events),
        sleeper=lambda _: None,
    )

    assert "poll=1" not in requested[0]
    assert "since=all" in requested[0]
    assert payload == {
        "task_id": task["id"],
        "state": "triggered",
        "summary": "Re-review",
        "prompt": "Review now",
        "cwd": str(tmp_path),
        "message_id": "msg-1",
    }
    saved = wire.load_task(paths, task["id"])
    assert saved["state"] == "triggered"
    claim = json.loads((paths.claims / task["id"] / "1.json").read_text())
    assert claim["consumer"] == "foreground"
    assert not (paths.runs / task["id"]).exists()


def test_wait_ignores_every_message_before_grace_boundary(
    wire, paths, tmp_path, monkeypatch
):
    task = make_foreground_task(wire, paths, tmp_path, grace=True)
    monkeypatch.setattr(wire, "utc_now", lambda: wire.parse_time(task["arm_at"]))
    topic = task["transport"]["topic"]
    events = (
        {
            "event": "message",
            "id": "early-1",
            "topic": topic,
            "time": event_time(wire, task, -30),
        },
        {
            "event": "message",
            "id": "early-2",
            "topic": topic,
            "time": event_time(wire, task, -1),
        },
        {
            "event": "message",
            "id": "eligible",
            "topic": topic,
            "time": event_time(wire, task),
        },
    )

    payload = wire.wait_for_task(
        paths,
        task["id"],
        opener=lambda url, timeout: response_for(*events),
        sleeper=lambda _: None,
    )

    assert payload["message_id"] == "eligible"
    assert len(list((paths.claims / task["id"]).glob("*.json"))) == 1


def test_wait_rejects_cached_early_message_after_local_grace_elapsed(
    wire, paths, tmp_path, monkeypatch
):
    task = make_foreground_task(wire, paths, tmp_path, grace=True)
    topic = task["transport"]["topic"]
    monkeypatch.setattr(
        wire,
        "utc_now",
        lambda: wire.parse_time(task["arm_at"]) + timedelta(seconds=30),
    )
    events = (
        {
            "event": "message",
            "id": "cached-preview",
            "topic": topic,
            "time": event_time(wire, task, -60),
        },
        {
            "event": "message",
            "id": "actual-click",
            "topic": topic,
            "time": event_time(wire, task, 30),
        },
    )

    payload = wire.wait_for_task(
        paths,
        task["id"],
        opener=lambda url, timeout: response_for(*events),
        sleeper=lambda _: None,
    )

    assert payload["message_id"] == "actual-click"


def test_wait_accepts_integer_ntfy_time_at_persisted_arm_boundary(
    wire, paths, tmp_path, monkeypatch
):
    created = datetime(2026, 8, 13, 8, 0, 0, 750000, tzinfo=timezone.utc)
    monkeypatch.setattr(wire, "utc_now", lambda: created)
    task = make_foreground_task(wire, paths, tmp_path, grace=True)
    topic = task["transport"]["topic"]
    boundary = int(wire.parse_time(task["arm_at"]).timestamp())
    monkeypatch.setattr(wire, "utc_now", lambda: wire.parse_time(task["arm_at"]))
    events = (
        {"event": "message", "id": "boundary", "topic": topic, "time": boundary},
        {
            "event": "message",
            "id": "one-second-late",
            "topic": topic,
            "time": boundary + 1,
        },
    )

    payload = wire.wait_for_task(
        paths,
        task["id"],
        opener=lambda url, timeout: response_for(*events),
        sleeper=lambda _: None,
    )

    assert payload["message_id"] == "boundary"


def test_wait_reconnects_from_latest_event_id(wire, paths, tmp_path):
    task = make_foreground_task(wire, paths, tmp_path)
    topic = task["transport"]["topic"]
    requested = []
    responses = iter(
        (
            response_for(
                {"event": "message", "id": "cursor-1", "topic": "wt_other"},
                {"event": "keepalive", "id": "keep-2", "topic": topic},
            ),
            response_for({"event": "message", "id": "msg-2", "topic": topic}),
        )
    )

    result = wire.wait_for_task(
        paths,
        task["id"],
        opener=lambda url, timeout: requested.append(url) or next(responses),
        sleeper=lambda _: None,
    )

    assert result["message_id"] == "msg-2"
    assert "since=all" in requested[0]
    assert "since=all" in requested[1]


def test_wait_reconnects_after_incomplete_http_read(wire, paths, tmp_path):
    task = make_foreground_task(wire, paths, tmp_path)
    topic = task["transport"]["topic"]
    attempts = 0

    class InterruptedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            raise IncompleteRead(b"partial")

    def opener(url, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return InterruptedResponse()
        return response_for({"event": "message", "id": "msg-1", "topic": topic})

    result = wire.wait_for_task(
        paths,
        task["id"],
        opener=opener,
        sleeper=lambda _: None,
    )

    assert result["state"] == "triggered"
    assert attempts == 2


def test_wait_reconnects_after_transient_network_error(wire, paths, tmp_path):
    task = make_foreground_task(wire, paths, tmp_path)
    topic = task["transport"]["topic"]
    attempts = 0
    delays = []

    def opener(url, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("offline")
        return response_for({"event": "message", "id": "msg-1", "topic": topic})

    result = wire.wait_for_task(
        paths,
        task["id"],
        opener=opener,
        sleeper=delays.append,
    )

    assert result["state"] == "triggered"
    assert attempts == 2
    assert delays == [1.0]


def test_wait_rejects_cancelled_expired_and_consumed_tasks(wire, paths, tmp_path):
    cancelled = make_foreground_task(wire, paths, tmp_path)
    wire.cancel_task(paths, cancelled["id"])
    with pytest.raises(wire.StateError, match="cancelled"):
        wire.wait_for_task(paths, cancelled["id"])

    expired = make_foreground_task(wire, paths, tmp_path)
    expired["expires_at"] = wire.iso(datetime.now(timezone.utc) - timedelta(seconds=1))
    wire.save_task(paths, expired)
    with pytest.raises(wire.StateError, match="expired"):
        wire.wait_for_task(paths, expired["id"])
    assert wire.load_task(paths, expired["id"])["state"] == "expired"

    consumed = make_foreground_task(wire, paths, tmp_path)
    wire.claim_foreground_task(paths, consumed["id"], message_id="msg-1")
    with pytest.raises(wire.StateError, match="triggered"):
        wire.wait_for_task(paths, consumed["id"])


def test_foreground_claim_recovers_after_task_save_crash(
    wire, paths, tmp_path, monkeypatch
):
    task = make_foreground_task(wire, paths, tmp_path)
    real_save = wire.save_task
    crashed = False

    def crash_after_claim(observed_paths, observed_task):
        nonlocal crashed
        claim_dir = observed_paths.claims / observed_task["id"]
        if not crashed and claim_dir.exists() and list(claim_dir.glob("*.json")):
            crashed = True
            raise OSError("simulated crash after durable claim")
        real_save(observed_paths, observed_task)

    monkeypatch.setattr(wire, "save_task", crash_after_claim)
    with pytest.raises(OSError, match="simulated crash"):
        wire.claim_foreground_task(paths, task["id"], message_id="msg-1")

    assert wire.load_task(paths, task["id"])["state"] == "armed"
    recovered = wire.claim_foreground_task(paths, task["id"], message_id="msg-replay")

    assert recovered["state"] == "triggered"
    assert recovered["message_id"] == "msg-1"
    assert wire.load_task(paths, task["id"])["state"] == "triggered"
    assert len(list((paths.claims / task["id"]).glob("*.json"))) == 1


def test_two_foreground_consumers_create_one_claim(wire, paths, tmp_path):
    task = make_foreground_task(wire, paths, tmp_path)
    barrier = threading.Barrier(2)
    outcomes = []

    def consume(message_id):
        barrier.wait()
        try:
            result = wire.claim_foreground_task(
                paths, task["id"], message_id=message_id
            )
        except wire.StateError as exc:
            outcomes.append(("error", str(exc)))
        else:
            outcomes.append(("triggered", result["message_id"]))

    threads = [
        threading.Thread(target=consume, args=("msg-1",)),
        threading.Thread(target=consume, args=("msg-2",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(kind for kind, _ in outcomes) == ["error", "triggered"]
    assert len(list((paths.claims / task["id"]).glob("*.json"))) == 1


def test_detached_listener_ignores_foreground_tasks(wire, paths, tmp_path):
    make_foreground_task(wire, paths, tmp_path)
    assert wire.active_topic_groups(paths) == {}


def test_message_claim_is_durable_before_cursor_and_dispatch(
    wire, paths, tmp_path, monkeypatch
):
    task = make_task(wire, paths, tmp_path)
    monkeypatch.setattr(wire, "utc_now", lambda: wire.parse_time(task["arm_at"]))
    observations = []

    def dispatch(observed_paths, task_id, generation):
        saved = wire.load_task(observed_paths, task_id)
        listener_state = json.loads((observed_paths.state / "listener-state.json").read_text())
        observations.append((saved["state"], listener_state["cursors"]["https://ntfy.sh"]))
        return {"classification": "completed", "generation": generation}

    result = wire.handle_message(
        paths,
        "https://ntfy.sh",
        {
            "event": "message",
            "id": "msg-1",
            "topic": task["transport"]["topic"],
            "time": event_time(wire, task),
        },
        dispatcher=dispatch,
    )
    assert result["classification"] == "completed"
    assert observations == [("claimed", "msg-1")]


def test_detached_listener_ignores_early_messages_then_dispatches(
    wire, paths, tmp_path, monkeypatch
):
    task = make_task(wire, paths, tmp_path)
    topic = task["transport"]["topic"]
    dispatched = []

    early = wire.handle_message(
        paths,
        "https://ntfy.sh",
        {
            "event": "message",
            "id": "early",
            "topic": topic,
            "time": event_time(wire, task, -1),
        },
        dispatcher=lambda *args: dispatched.append(args),
    )

    assert early is None
    assert wire.load_task(paths, task["id"])["state"] == "armed"
    assert wire.load_listener_state(paths)["cursors"]["https://ntfy.sh"] == "early"
    assert dispatched == []

    monkeypatch.setattr(wire, "utc_now", lambda: wire.parse_time(task["arm_at"]))

    accepted = wire.handle_message(
        paths,
        "https://ntfy.sh",
        {
            "event": "message",
            "id": "eligible",
            "topic": topic,
            "time": event_time(wire, task),
        },
        dispatcher=lambda *args: dispatched.append(args) or {"ok": True},
    )

    assert accepted == {"ok": True}
    assert len(dispatched) == 1


def test_detached_listener_accepts_legacy_task_without_event_time(
    wire, paths, tmp_path
):
    task = make_task(wire, paths, tmp_path)
    task.pop("arm_at")
    wire.save_task(paths, task)

    result = wire.handle_message(
        paths,
        "https://ntfy.sh",
        {
            "event": "message",
            "id": "legacy",
            "topic": task["transport"]["topic"],
        },
        dispatcher=lambda *args: {"legacy": True},
    )

    assert result == {"legacy": True}


def test_detached_listener_accepts_integer_ntfy_time_at_persisted_arm_boundary(
    wire, paths, tmp_path, monkeypatch
):
    created = datetime(2026, 8, 13, 8, 0, 0, 750000, tzinfo=timezone.utc)
    monkeypatch.setattr(wire, "utc_now", lambda: created)
    task = make_task(wire, paths, tmp_path)
    boundary = int(wire.parse_time(task["arm_at"]).timestamp())
    monkeypatch.setattr(wire, "utc_now", lambda: wire.parse_time(task["arm_at"]))

    result = wire.handle_message(
        paths,
        "https://ntfy.sh",
        {
            "event": "message",
            "id": "boundary",
            "topic": task["transport"]["topic"],
            "time": boundary,
        },
        dispatcher=lambda *args: {"accepted": True},
    )

    assert result == {"accepted": True}


def test_open_and_keepalive_messages_do_not_claim(wire, paths, tmp_path):
    task = make_task(wire, paths, tmp_path)
    for event in ("open", "keepalive"):
        assert wire.handle_message(
            paths,
            "https://ntfy.sh",
            {"event": event, "id": "m", "topic": task["transport"]["topic"]},
        ) is None
    assert wire.load_task(paths, task["id"])["state"] == "armed"


def test_poll_server_replays_from_saved_cursor(wire, paths, tmp_path, monkeypatch):
    task = make_task(wire, paths, tmp_path)
    monkeypatch.setattr(wire, "utc_now", lambda: wire.parse_time(task["arm_at"]))
    wire.checkpoint_cursor(paths, "https://ntfy.sh", "old-id")
    requested = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            message = {
                "event": "message",
                "id": "new-id",
                "topic": task["transport"]["topic"],
                "time": event_time(wire, task),
            }
            return iter([json.dumps(message).encode() + b"\n"])

    def opener(url, timeout):
        requested.append((url, timeout))
        return Response()

    seen = []
    wire.poll_server(
        paths,
        "https://ntfy.sh",
        [task["transport"]["topic"]],
        opener=opener,
        dispatcher=lambda *_: seen.append("dispatch") or {"classification": "completed"},
    )
    assert "since=old-id" in requested[0][0]
    assert seen == ["dispatch"]


def test_background_start_is_idempotent(wire, paths, monkeypatch):
    launched = []

    class Process:
        pid = 4321

    monkeypatch.setattr(
        wire.subprocess,
        "Popen",
        lambda *a, **k: launched.append((a, k)) or Process(),
    )
    monkeypatch.setattr(wire, "process_fingerprint", lambda pid: f"fp-{pid}")
    monkeypatch.setattr(wire, "process_alive", lambda pid, fingerprint=None: pid == 4321)
    assert wire.start_background(paths) is True
    assert wire.start_background(paths) is False
    assert len(launched) == 1


def test_background_start_replaces_stale_record(wire, paths, monkeypatch):
    wire.atomic_write_json(
        paths.runtime / "listener.json",
        {"pid": 99, "fingerprint": "old"},
    )

    class Process:
        pid = 100

    monkeypatch.setattr(wire.subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(wire, "process_fingerprint", lambda pid: f"fp-{pid}")
    monkeypatch.setattr(wire, "process_alive", lambda pid, fingerprint=None: False)
    assert wire.start_background(paths) is True
    record = json.loads((paths.runtime / "listener.json").read_text())
    assert record == {"fingerprint": "fp-100", "pid": 100}


def run_wire(tmp_path, *args, expect=0):
    env = os.environ.copy()
    env.update(
        {
            "WIRE_TRIGGER_STATE_HOME": str(tmp_path / "state"),
            "WIRE_TRIGGER_CONFIG_HOME": str(tmp_path / "config"),
            "WIRE_TRIGGER_RUNTIME_HOME": str(tmp_path / "runtime"),
        }
    )
    result = subprocess.run(
        [sys.executable, str(WIRE_PATH), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == expect, result.stderr
    return result


def test_cli_create_status_show_and_cancel_redact_topic(tmp_path):
    result = run_wire(
        tmp_path,
        "create",
        "--summary",
        "Re-review PR 7",
        "--prompt",
        "Review it now",
        "--cwd",
        str(tmp_path),
        "--fresh",
        "--tool",
        "codex",
        "--allow-unconfirmed-get",
        "--no-start",
        "--json",
    )
    created = json.loads(result.stdout)
    assert created["link"].startswith("https://ntfy.sh/wt_")
    task_id = created["task"]["id"]

    status_result = json.loads(run_wire(tmp_path, "status", "--json").stdout)
    assert status_result["counts"] == {"armed": 1}
    assert "wt_" not in json.dumps(status_result)

    hidden = json.loads(run_wire(tmp_path, "show", task_id, "--json").stdout)
    assert "topic" not in hidden["transport"]
    revealed = json.loads(
        run_wire(tmp_path, "show", task_id, "--reveal-link", "--json").stdout
    )
    assert revealed["link"] == created["link"]
    cancelled = json.loads(run_wire(tmp_path, "cancel", task_id, "--json").stdout)
    assert cancelled["state"] == "cancelled"


def test_cli_create_defaults_to_foreground_without_listener(tmp_path):
    created = json.loads(
        run_wire(
            tmp_path,
            "create",
            "--summary",
            "Re-review PR 7",
            "--prompt",
            "Review it now",
            "--cwd",
            str(tmp_path),
            "--allow-unconfirmed-get",
            "--json",
        ).stdout
    )
    assert created["task"]["target"] == {"kind": "foreground"}
    assert not (tmp_path / "runtime/listener.json").exists()


def test_cli_detach_requires_tool(tmp_path):
    result = run_wire(
        tmp_path,
        "create",
        "--summary",
        "Review",
        "--prompt",
        "Review now",
        "--cwd",
        str(tmp_path),
        "--detach",
        "--allow-unconfirmed-get",
        "--json",
        expect=1,
    )
    assert "--tool" in json.loads(result.stdout)["error"]


def test_cli_default_session_refuses_to_guess(tmp_path):
    env = os.environ.copy()
    env.pop("CLAUDE_SESSION_ID", None)
    env.update(
        {
            "WIRE_TRIGGER_STATE_HOME": str(tmp_path / "state"),
            "WIRE_TRIGGER_CONFIG_HOME": str(tmp_path / "config"),
            "WIRE_TRIGGER_RUNTIME_HOME": str(tmp_path / "runtime"),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            str(WIRE_PATH),
            "create",
            "--summary",
            "Review",
            "--prompt",
            "Review now",
            "--cwd",
            str(tmp_path),
            "--detach",
            "--tool",
            "claude",
            "--allow-unconfirmed-get",
            "--allow-session-permissions",
            "--no-start",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 3
    assert "exact" in json.loads(result.stdout)["error"]


def test_cli_help_exposes_complete_command_set(tmp_path):
    result = run_wire(tmp_path, "--help")
    commands = (
        "create",
        "wait",
        "listen",
        "start",
        "stop",
        "status",
        "show",
        "attach",
        "cancel",
        "retry",
    )
    for command in commands:
        assert command in result.stdout
    assert "--detach" in run_wire(tmp_path, "create", "--help").stdout
    assert "--allow-session-permissions" in run_wire(
        tmp_path, "attach", "--help"
    ).stdout


def test_main_reports_interrupted_wait(wire, monkeypatch, capsys):
    monkeypatch.setattr(
        wire,
        "wait_for_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert wire.main(["wait", "trg_test", "--json"]) == 130
    result = json.loads(capsys.readouterr().out)
    assert result == {"code": 130, "error": "wait interrupted"}


def test_skill_documents_foreground_default_and_explicit_detach():
    text = SKILL_PATH.read_text(encoding="utf-8")
    for required in (
        "name: wire-trigger",
        "same active turn",
        "wire.py wait",
        "commentary",
        "--detach",
        "fresh",
        "--executor",
        "link-preview",
        "12 hours",
        "XDG_STATE_HOME",
        "ready-to-paste",
        "standalone",
        "two minutes",
        "after it was created",
    ):
        assert required in text
    assert "Default: attach the exact current session" not in text
