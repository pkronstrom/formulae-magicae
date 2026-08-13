#!/usr/bin/env python3
"""Create and consume one-shot agent triggers.

This file is deliberately standalone: it uses only Python's standard library and
does not import hawk.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import platform as platform_module
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, urlencode
from urllib.request import urlopen

SCHEMA_VERSION = 1
DEFAULT_SERVER = "https://ntfy.sh"
DEFAULT_EXPIRY_DAYS = 7
DEFAULT_GRACE_SECONDS = 120


class WireError(RuntimeError):
    """Operational wire-trigger error."""


class UnsafeTriggerError(WireError):
    """Raised when a direct trigger risk was not acknowledged."""


class SessionUnavailableError(WireError):
    """Raised when the exact current persisted session cannot be identified."""


class StateError(WireError):
    """Raised when an operation is invalid for the task's current state."""


@dataclass(frozen=True)
class Paths:
    state: Path
    config: Path
    runtime: Path

    @property
    def tasks(self) -> Path:
        return self.state / "tasks"

    @property
    def claims(self) -> Path:
        return self.state / "claims"

    @property
    def runs(self) -> Path:
        return self.state / "runs"


def _absolute_env(env: Mapping[str, str], name: str) -> Path | None:
    value = env.get(name, "")
    if not value:
        return None
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else None


def resolve_paths(
    env: Mapping[str, str] | None = None,
    *,
    platform: str | None = None,
) -> Paths:
    """Resolve state, config, and runtime paths without touching the filesystem."""
    values = os.environ if env is None else env
    system = (platform or platform_module.system()).lower()

    state_override = _absolute_env(values, "WIRE_TRIGGER_STATE_HOME")
    config_override = _absolute_env(values, "WIRE_TRIGGER_CONFIG_HOME")
    runtime_override = _absolute_env(values, "WIRE_TRIGGER_RUNTIME_HOME")

    if system.startswith("win"):
        local = _absolute_env(values, "LOCALAPPDATA") or (Path.home() / "AppData/Local")
        state = state_override or _absolute_env(values, "XDG_STATE_HOME")
        config = config_override or _absolute_env(values, "XDG_CONFIG_HOME")
        state = (state / "wire-trigger") if state else local / "wire-trigger/state"
        config = (config / "wire-trigger") if config else local / "wire-trigger/config"
        runtime = runtime_override or Path(tempfile.gettempdir()) / "wire-trigger"
    else:
        state_base = _absolute_env(values, "XDG_STATE_HOME") or Path.home() / ".local/state"
        config_base = _absolute_env(values, "XDG_CONFIG_HOME") or Path.home() / ".config"
        state = state_override or state_base / "wire-trigger"
        config = config_override or config_base / "wire-trigger"
        runtime = runtime_override or Path(tempfile.gettempdir()) / "wire-trigger"
    return Paths(state=state, config=config, runtime=runtime)


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        mode = path.stat().st_mode & 0o777
        if mode & 0o077:
            try:
                path.chmod(0o700)
            except OSError as exc:
                raise WireError(f"insecure directory permissions: {path}") from exc


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    ensure_private_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    """Create immutable JSON without replacing a prior durable claim."""
    ensure_private_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise StateError(f"durable record already exists: {path}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            path.chmod(0o600)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def make_topic() -> str:
    return "wt_" + secrets.token_urlsafe(32)


SESSION_ENV = {
    "codex": "CODEX_THREAD_ID",
    "claude": "CLAUDE_SESSION_ID",
    "agy": "AGY_CONVERSATION_ID",
    "antigravity": "AGY_CONVERSATION_ID",
    "opencode": "OPENCODE_SESSION_ID",
}


def detect_current_session(tool: str, env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    canonical = "agy" if tool == "antigravity" else tool
    variable = SESSION_ENV.get(canonical)
    value = values.get(variable, "").strip() if variable else ""
    if not value:
        raise SessionUnavailableError(
            f"cannot identify the exact current {canonical} session; pass its ID explicitly"
        )
    return value


def normalize_target(target: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(target)
    kind = str(result.get("kind", ""))
    tool = str(result.get("tool", ""))
    if kind == "foreground":
        if tool or result.get("executable") or result.get("session_id"):
            raise WireError("foreground target cannot select an agent executable or session")
        return {"kind": "foreground"}
    if tool == "antigravity":
        tool = "agy"
        result["tool"] = tool
    if kind not in {"session", "fresh", "executor"}:
        raise WireError(f"unsupported target kind: {kind or '<empty>'}")
    if not tool:
        raise WireError(f"{kind} target requires an explicit tool/executor")
    if tool not in {"codex", "claude", "agy", "opencode"}:
        raise WireError(f"unsupported executor: {tool}")
    if kind == "session" and not str(result.get("session_id", "")).strip():
        raise WireError("session target requires an exact session ID")
    if kind == "executor":
        result["kind"] = "fresh"
        result["explicit_executor"] = True
    return result


def build_agent_command(task: Mapping[str, Any]) -> list[str]:
    target = normalize_target(task["target"])
    if target["kind"] == "foreground":
        raise WireError("foreground target returns to the waiting agent")
    tool = target["tool"]
    executable = str(target.get("executable") or tool)
    prompt = str(task["prompt"])
    if target["kind"] == "session":
        session_id = str(target["session_id"])
        prefixes = {
            "codex": [executable, "exec", "resume", session_id],
            "claude": [executable, "--resume", session_id, "-p"],
            "agy": [executable, "--print", "--conversation", session_id],
            "opencode": [executable, "run", "--session", session_id],
        }
    else:
        prefixes = {
            "codex": [executable, "exec", "-s", "read-only"],
            "claude": [executable, "-p", "--permission-mode", "plan"],
            "agy": [executable, "--print", "--mode", "plan"],
            "opencode": [executable, "run"],
        }
    return [*prefixes[tool], prompt]


def task_path(paths: Paths, task_id: str) -> Path:
    return paths.tasks / f"{task_id}.json"


def load_task(paths: Paths, task_id: str) -> dict[str, Any]:
    path = task_path(paths, task_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WireError(f"no such trigger: {task_id}") from exc
    if value.get("schema_version") != SCHEMA_VERSION:
        raise WireError(f"unsupported task schema: {value.get('schema_version')}")
    return value


def save_task(paths: Paths, task: Mapping[str, Any]) -> None:
    atomic_write_json(task_path(paths, str(task["id"])), task)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def event_is_eligible(
    task: Mapping[str, Any], message: Mapping[str, Any]
) -> bool:
    arm_at = task.get("arm_at")
    if not arm_at:
        return True
    boundary = parse_time(str(arm_at))
    # The publisher and listener may have different clocks. Never let a server
    # clock that is ahead shorten the local grace period.
    if utc_now() < boundary:
        return False
    published = message.get("time")
    if isinstance(published, bool) or not isinstance(published, (int, float)):
        return False
    try:
        event_at = datetime.fromtimestamp(published, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return False
    return event_at >= boundary


def try_file_lock(handle: Any) -> bool:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def release_file_lock(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def task_lock(paths: Paths, task_id: str, timeout: float = 5.0):
    lock_root = paths.runtime / "task-locks"
    ensure_private_dir(lock_root)
    lock = lock_root / f"{task_id}.lock"
    try:
        handle = lock.open("a+b")
    except IsADirectoryError as exc:
        raise StateError(
            f"legacy task lock needs manual removal: {lock}"
        ) from exc
    if os.name != "nt":
        lock.chmod(0o600)
    else:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while not acquired:
            acquired = try_file_lock(handle)
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise StateError(f"task is busy: {task_id}")
            time.sleep(0.01)
        yield
    finally:
        if acquired:
            release_file_lock(handle)
        handle.close()


def _claim_locked(
    paths: Paths,
    task: dict[str, Any],
    *,
    message_id: str | None,
    consumer: str = "detached",
    state: str = "claimed",
) -> dict[str, Any]:
    claim_dir = paths.claims / task["id"]
    ensure_private_dir(claim_dir)
    generations = [int(path.stem) for path in claim_dir.glob("*.json") if path.stem.isdigit()]
    generation = max(generations, default=0) + 1
    attempt_id = f"a{generation}-{secrets.token_urlsafe(6)}"
    claim = {
        "task_id": task["id"],
        "generation": generation,
        "attempt_id": attempt_id,
        "message_id": message_id,
        "consumer": consumer,
        "claimed_at": iso(utc_now()),
        "target": dict(task["target"]),
        "revision": int(task["revision"]) + 1,
    }
    write_json_exclusive(claim_dir / f"{generation}.json", claim)
    task["state"] = state
    task["revision"] = claim["revision"]
    task["claim_generation"] = generation
    task["attempts"] = int(task.get("attempts", 0)) + 1
    task["latest_run"] = attempt_id
    save_task(paths, task)
    return claim


def claim_task(
    paths: Paths,
    task_id: str,
    *,
    message_id: str | None = None,
) -> dict[str, Any] | None:
    with task_lock(paths, task_id):
        task = load_task(paths, task_id)
        if task["state"] != "armed":
            return None
        claim_dir = paths.claims / task_id
        existing = sorted(
            (path for path in claim_dir.glob("*.json") if path.stem.isdigit()),
            key=lambda path: int(path.stem),
        ) if claim_dir.exists() else []
        if existing:
            orphan = json.loads(existing[-1].read_text(encoding="utf-8"))
            task["state"] = "uncertain"
            task["claim_generation"] = int(orphan["generation"])
            task["attempts"] = max(int(task.get("attempts", 0)), len(existing))
            task["latest_run"] = orphan["attempt_id"]
            task["revision"] = max(int(task["revision"]) + 1, int(orphan["revision"]))
            save_task(paths, task)
            return None
        if parse_time(task["expires_at"]) <= utc_now():
            task["state"] = "expired"
            task["revision"] += 1
            save_task(paths, task)
            return None
        return _claim_locked(paths, task, message_id=message_id)


def claim_foreground_task(
    paths: Paths,
    task_id: str,
    *,
    message_id: str | None = None,
) -> dict[str, Any]:
    with task_lock(paths, task_id):
        task = load_task(paths, task_id)
        if task.get("target", {}).get("kind") != "foreground":
            raise StateError("task is not a foreground trigger")
        if task["state"] != "armed":
            raise StateError(f"cannot wait for a {task['state']} trigger")
        claim_dir = paths.claims / task_id
        existing = sorted(
            (path for path in claim_dir.glob("*.json") if path.stem.isdigit()),
            key=lambda path: int(path.stem),
        ) if claim_dir.exists() else []
        if existing:
            claim = json.loads(existing[-1].read_text(encoding="utf-8"))
            if claim.get("consumer") != "foreground":
                raise StateError("foreground trigger was already consumed")
            task["state"] = "triggered"
            task["revision"] = max(int(task["revision"]) + 1, int(claim["revision"]))
            task["claim_generation"] = int(claim["generation"])
            task["attempts"] = max(int(task.get("attempts", 0)), len(existing))
            task["latest_run"] = claim["attempt_id"]
            save_task(paths, task)
            return {
                "task_id": task_id,
                "state": "triggered",
                "summary": task["summary"],
                "prompt": task["prompt"],
                "cwd": task["cwd"],
                "message_id": claim.get("message_id"),
            }
        if parse_time(task["expires_at"]) <= utc_now():
            task["state"] = "expired"
            task["revision"] += 1
            save_task(paths, task)
            raise StateError("cannot wait for an expired trigger")
        _claim_locked(
            paths,
            task,
            message_id=message_id,
            consumer="foreground",
            state="triggered",
        )
        return {
            "task_id": task_id,
            "state": "triggered",
            "summary": task["summary"],
            "prompt": task["prompt"],
            "cwd": task["cwd"],
            "message_id": message_id,
        }


def attach_task(
    paths: Paths,
    task_id: str,
    target: Mapping[str, Any],
    *,
    allow_session_permissions: bool = False,
) -> dict[str, Any]:
    normalized_target = normalize_target(target)
    if normalized_target.get("kind") == "session" and not allow_session_permissions:
        raise UnsafeTriggerError("session permissions require explicit acknowledgement")
    with task_lock(paths, task_id):
        task = load_task(paths, task_id)
        if task["state"] != "armed":
            raise StateError(f"cannot attach a {task['state']} trigger")
        task["target"] = normalized_target
        task["revision"] += 1
        save_task(paths, task)
        return task


def cancel_task(paths: Paths, task_id: str) -> dict[str, Any]:
    with task_lock(paths, task_id):
        task = load_task(paths, task_id)
        if task["state"] != "armed":
            raise StateError(f"cannot cancel a {task['state']} trigger")
        task["state"] = "cancelled"
        task["revision"] += 1
        save_task(paths, task)
        return task


def _private_text(path: Path, content: str) -> None:
    ensure_private_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def dispatch_claim(paths: Paths, task_id: str, generation: int) -> dict[str, Any]:
    task = load_task(paths, task_id)
    claim_path = paths.claims / task_id / f"{generation}.json"
    try:
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateError(f"missing claim generation {generation}") from exc
    if task.get("claim_generation") != generation or task["state"] != "claimed":
        raise StateError(f"claim generation {generation} is not dispatchable")

    attempt_id = claim["attempt_id"]
    run_dir = paths.runs / task_id / attempt_id
    ensure_private_dir(run_dir)
    started = utc_now()
    argv = build_agent_command(task)
    run: dict[str, Any] = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "generation": generation,
        "target": claim["target"],
        "started_at": iso(started),
        "argv": argv[1:-1],
    }
    process: subprocess.Popen[str] | None = None
    stdout = ""
    stderr = ""
    try:
        process = subprocess.Popen(
            argv,
            cwd=task["cwd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with task_lock(paths, task_id):
            current = load_task(paths, task_id)
            if current.get("claim_generation") != generation:
                process.terminate()
                raise StateError("claim generation changed before launch")
            current["state"] = "running"
            current["revision"] += 1
            save_task(paths, current)
        stdout, stderr = process.communicate()
        lowered = stderr.lower()
        if process.returncode == 0:
            classification = "completed"
        elif "busy" in lowered or "locked" in lowered:
            classification = "busy"
        else:
            classification = "failed"
        run["exit_code"] = process.returncode
    except FileNotFoundError as exc:
        stderr = str(exc)
        classification = "failed"
        run["exit_code"] = 127
    except Exception as exc:
        stderr = (stderr + "\n" + str(exc)).strip()
        classification = "uncertain" if process is not None else "failed"
        run["exit_code"] = None

    _private_text(run_dir / "stdout.log", stdout)
    _private_text(run_dir / "stderr.log", stderr)
    run["classification"] = classification
    run["finished_at"] = iso(utc_now())
    atomic_write_json(run_dir / "run.json", run)
    with task_lock(paths, task_id):
        current = load_task(paths, task_id)
        if current.get("claim_generation") == generation:
            current["state"] = classification
            current["revision"] += 1
            save_task(paths, current)
    return run


def retry_task(paths: Paths, task_id: str) -> dict[str, Any]:
    with task_lock(paths, task_id):
        task = load_task(paths, task_id)
        if task["state"] not in {"busy", "failed", "uncertain"}:
            raise StateError(f"cannot retry a {task['state']} trigger")
        claim = _claim_locked(paths, task, message_id=None)
    return dispatch_claim(paths, task_id, int(claim["generation"]))


def listener_state_path(paths: Paths) -> Path:
    return paths.state / "listener-state.json"


def load_listener_state(paths: Paths) -> dict[str, Any]:
    try:
        value = json.loads(listener_state_path(paths).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"cursors": {}}
    if not isinstance(value.get("cursors"), dict):
        return {"cursors": {}}
    return value


def checkpoint_cursor(paths: Paths, server: str, message_id: str) -> None:
    state = load_listener_state(paths)
    state["cursors"][server.rstrip("/")] = message_id
    atomic_write_json(listener_state_path(paths), state)


def subscription_url(
    server: str,
    topics: list[str],
    *,
    since: str | None = None,
    poll: bool = True,
) -> str:
    if not topics:
        raise WireError("cannot subscribe without topics")
    topic_path = ",".join(sorted(quote(topic, safe="_-") for topic in topics))
    query: dict[str, str] = {}
    if poll:
        query["poll"] = "1"
    if since:
        query["since"] = since
    return f"{server.rstrip('/')}/{topic_path}/json?{urlencode(query)}"


def _task_for_topic(paths: Paths, server: str, topic: str) -> dict[str, Any] | None:
    if not paths.tasks.exists():
        return None
    for path in paths.tasks.glob("*.json"):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        transport = task.get("transport", {})
        if (
            task.get("state") == "armed"
            and task.get("target", {}).get("kind") != "foreground"
            and transport.get("server", "").rstrip("/") == server.rstrip("/")
            and transport.get("topic") == topic
        ):
            return task
    return None


def handle_message(
    paths: Paths,
    server: str,
    message: Mapping[str, Any],
    *,
    dispatcher=dispatch_claim,
) -> dict[str, Any] | None:
    if message.get("event") != "message":
        return None
    message_id = str(message.get("id", ""))
    task = _task_for_topic(paths, server, str(message.get("topic", "")))
    claim = None
    if task and event_is_eligible(task, message):
        claim = claim_task(paths, task["id"], message_id=message_id)
    if message_id:
        checkpoint_cursor(paths, server, message_id)
    if not claim:
        return None
    return dispatcher(paths, task["id"], int(claim["generation"]))


def poll_server(
    paths: Paths,
    server: str,
    topics: list[str],
    *,
    opener=urlopen,
    dispatcher=dispatch_claim,
    timeout: float = 15.0,
) -> int:
    cursor = load_listener_state(paths)["cursors"].get(server.rstrip("/"))
    url = subscription_url(server, topics, since=cursor)
    handled = 0
    with opener(url, timeout=timeout) as response:
        for raw in response:
            if not raw.strip():
                continue
            message = json.loads(raw.decode("utf-8"))
            result = handle_message(paths, server, message, dispatcher=dispatcher)
            handled += int(result is not None)
    return handled


def _load_waitable_task(paths: Paths, task_id: str) -> dict[str, Any]:
    task = load_task(paths, task_id)
    if task.get("target", {}).get("kind") != "foreground":
        raise StateError("task is not a foreground trigger")
    if task["state"] != "armed":
        raise StateError(f"cannot wait for a {task['state']} trigger")
    if parse_time(task["expires_at"]) > utc_now():
        return task
    with task_lock(paths, task_id):
        current = load_task(paths, task_id)
        if current["state"] == "armed" and parse_time(current["expires_at"]) <= utc_now():
            current["state"] = "expired"
            current["revision"] += 1
            save_task(paths, current)
    raise StateError("cannot wait for an expired trigger")


def wait_for_task(
    paths: Paths,
    task_id: str,
    *,
    opener=urlopen,
    sleeper=time.sleep,
    timeout: float = 65.0,
) -> dict[str, Any]:
    task = _load_waitable_task(paths, task_id)
    server = task["transport"]["server"].rstrip("/")
    topic = task["transport"]["topic"]
    cursor: str | None = "all"
    backoff = 1.0
    while True:
        task = _load_waitable_task(paths, task_id)
        remaining = (parse_time(task["expires_at"]) - utc_now()).total_seconds()
        request_timeout = max(1.0, min(timeout, remaining))
        url = subscription_url(server, [topic], since=cursor, poll=False)
        try:
            with opener(url, timeout=request_timeout) as response:
                for raw in response:
                    if not raw.strip():
                        continue
                    try:
                        message = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if message.get("event") != "message":
                        _load_waitable_task(paths, task_id)
                        continue
                    if str(message.get("topic", "")) != topic:
                        continue
                    task = _load_waitable_task(paths, task_id)
                    if not event_is_eligible(task, message):
                        continue
                    message_id = str(message.get("id", ""))
                    return claim_foreground_task(
                        paths,
                        task_id,
                        message_id=message_id or None,
                    )
        except (OSError, TimeoutError, http.client.IncompleteRead):
            pass
        task = _load_waitable_task(paths, task_id)
        remaining = (parse_time(task["expires_at"]) - utc_now()).total_seconds()
        sleeper(min(backoff, max(0.0, remaining)))
        backoff = min(backoff * 2, 30.0)


def active_topic_groups(paths: Paths) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    if not paths.tasks.exists():
        return groups
    for path in paths.tasks.glob("*.json"):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if task.get("state") in {"claimed", "running"}:
            with task_lock(paths, task["id"]):
                current = load_task(paths, task["id"])
                if current["state"] in {"claimed", "running"}:
                    current["state"] = "uncertain"
                    current["revision"] += 1
                    save_task(paths, current)
            continue
        if task.get("state") != "armed":
            continue
        if task.get("target", {}).get("kind") == "foreground":
            continue
        if parse_time(task["expires_at"]) <= utc_now():
            with task_lock(paths, task["id"]):
                current = load_task(paths, task["id"])
                if current["state"] == "armed" and parse_time(current["expires_at"]) <= utc_now():
                    current["state"] = "expired"
                    current["revision"] += 1
                    save_task(paths, current)
            continue
        transport = task["transport"]
        groups.setdefault(transport["server"].rstrip("/"), []).append(transport["topic"])
    return groups


def listen_forever(paths: Paths, *, interval: float = 2.0) -> None:
    backoff = interval
    while True:
        groups = active_topic_groups(paths)
        if not groups:
            return
        failed = False
        for server, topics in groups.items():
            try:
                poll_server(paths, server, topics)
            except (OSError, TimeoutError, json.JSONDecodeError):
                failed = True
        if failed:
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
        else:
            backoff = interval
            time.sleep(interval)


def process_fingerprint(pid: int) -> str | None:
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.exists():
        try:
            fields = proc_stat.read_text(encoding="utf-8").split()
            return fields[21]
        except (OSError, IndexError):
            return None
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def process_alive(pid: int, fingerprint: str | None = None) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return fingerprint is None or process_fingerprint(pid) == fingerprint


def runtime_record_path(paths: Paths) -> Path:
    return paths.runtime / "listener.json"


def _load_runtime_record(paths: Paths) -> dict[str, Any] | None:
    try:
        return json.loads(runtime_record_path(paths).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def start_background(paths: Paths) -> bool:
    ensure_private_dir(paths.runtime)
    with task_lock(paths, "__listener_start__"):
        current = _load_runtime_record(paths)
        if current and process_alive(int(current["pid"]), current.get("fingerprint")):
            return False
        if current:
            runtime_record_path(paths).unlink(missing_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "WIRE_TRIGGER_STATE_HOME": str(paths.state),
                "WIRE_TRIGGER_CONFIG_HOME": str(paths.config),
                "WIRE_TRIGGER_RUNTIME_HOME": str(paths.runtime),
            }
        )
        kwargs: dict[str, Any] = {
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "listen"], **kwargs
        )
        atomic_write_json(
            runtime_record_path(paths),
            {"pid": process.pid, "fingerprint": process_fingerprint(process.pid)},
        )
        return True


def stop_background(paths: Paths) -> bool:
    with task_lock(paths, "__listener_start__"):
        current = _load_runtime_record(paths)
        if not current:
            return False
        pid = int(current["pid"])
        if not process_alive(pid, current.get("fingerprint")):
            runtime_record_path(paths).unlink(missing_ok=True)
            return False
        os.kill(pid, signal.SIGTERM)
        runtime_record_path(paths).unlink(missing_ok=True)
        return True


def task_link(task: Mapping[str, Any]) -> str:
    transport = task["transport"]
    return f"{transport['server'].rstrip('/')}/{transport['topic']}/trigger"


def public_task(task: Mapping[str, Any], *, reveal_link: bool = False) -> dict[str, Any]:
    result = dict(task)
    result["transport"] = {
        "kind": task["transport"]["kind"],
        "server": task["transport"]["server"],
    }
    if reveal_link:
        result["link"] = task_link(task)
    return result


def list_tasks(paths: Paths) -> list[dict[str, Any]]:
    tasks = []
    if paths.tasks.exists():
        for path in sorted(paths.tasks.glob("*.json")):
            try:
                tasks.append(load_task(paths, path.stem))
            except WireError:
                continue
    return tasks


def status_data(paths: Paths) -> dict[str, Any]:
    record = _load_runtime_record(paths)
    listener = bool(
        record and process_alive(int(record["pid"]), record.get("fingerprint"))
    )
    tasks = list_tasks(paths)
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task["state"]] = counts.get(task["state"], 0) + 1
    return {
        "listener_running": listener,
        "counts": counts,
        "tasks": [
            {
                "id": task["id"],
                "state": task["state"],
                "summary": task["summary"],
                "target": task["target"],
            }
            for task in tasks
        ],
    }


def _add_json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wire.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create and arm a one-shot trigger")
    create.add_argument("--summary", required=True)
    create.add_argument("--prompt", required=True)
    create.add_argument("--cwd", default=os.getcwd())
    create.add_argument("--tool", choices=["codex", "claude", "agy", "opencode"])
    create.add_argument("--detach", action="store_true")
    mode = create.add_mutually_exclusive_group()
    mode.add_argument("--session-id")
    mode.add_argument("--fresh", action="store_true")
    mode.add_argument("--executor", choices=["codex", "claude", "agy", "opencode"])
    create.add_argument("--executable")
    create.add_argument("--expires", type=int, default=DEFAULT_EXPIRY_DAYS, metavar="DAYS")
    create.add_argument("--server", default=DEFAULT_SERVER)
    create.add_argument("--allow-unconfirmed-get", action="store_true")
    create.add_argument("--allow-session-permissions", action="store_true")
    create.add_argument("--no-start", action="store_true")
    _add_json_option(create)

    wait = sub.add_parser("wait", help="wait for one foreground trigger")
    wait.add_argument("id")
    _add_json_option(wait)

    listen = sub.add_parser("listen", help="run the listener in the foreground")
    listen.add_argument("--interval", type=float, default=2.0)
    _add_json_option(listen)
    for name, help_text in (
        ("start", "start the background listener"),
        ("stop", "stop the background listener"),
        ("status", "show listener and task status"),
    ):
        child = sub.add_parser(name, help=help_text)
        _add_json_option(child)

    show = sub.add_parser("show", help="show one task")
    show.add_argument("id")
    show.add_argument("--reveal-link", action="store_true")
    _add_json_option(show)

    attach = sub.add_parser("attach", help="rewire an armed task")
    attach.add_argument("id")
    attach.add_argument("--tool", required=True, choices=["codex", "claude", "agy", "opencode"])
    attach_mode = attach.add_mutually_exclusive_group(required=True)
    attach_mode.add_argument("--session-id")
    attach_mode.add_argument("--fresh", action="store_true")
    attach.add_argument("--executable")
    attach.add_argument("--allow-session-permissions", action="store_true")
    _add_json_option(attach)

    for name in ("cancel", "retry"):
        child = sub.add_parser(name, help=f"{name} a task")
        child.add_argument("id")
        _add_json_option(child)
    return parser


def _emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
    elif isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def _target_from_create(args: argparse.Namespace) -> dict[str, Any]:
    if args.executor:
        target: dict[str, Any] = {
            "kind": "executor",
            "tool": args.executor,
        }
    elif args.fresh:
        if not args.tool:
            raise WireError("--fresh requires --tool")
        target = {"kind": "fresh", "tool": args.tool}
    elif args.detach:
        if not args.tool:
            raise WireError("--detach requires --tool")
        session_id = args.session_id or detect_current_session(args.tool)
        target = {"kind": "session", "tool": args.tool, "session_id": session_id}
    else:
        if args.tool or args.session_id or args.executable:
            raise WireError(
                "--tool, --session-id, and --executable require detached mode"
            )
        target = {"kind": "foreground"}
    if args.executable:
        target["executable"] = args.executable
    return target


def run_command(args: argparse.Namespace, paths: Paths) -> Any:
    command = args.command
    if command == "create":
        target = _target_from_create(args)
        task = create_task(
            paths,
            summary=args.summary,
            prompt=args.prompt,
            cwd=args.cwd,
            target=target,
            allow_unconfirmed_get=args.allow_unconfirmed_get,
            allow_session_permissions=args.allow_session_permissions,
            expiry_days=args.expires,
            server=args.server,
            start_listener=target["kind"] != "foreground" and not args.no_start,
        )
        return {"task": task, "link": task_link(task)}
    if command == "wait":
        return wait_for_task(paths, args.id)
    if command == "listen":
        listen_forever(paths, interval=args.interval)
        return {"stopped": True}
    if command == "start":
        return {"started": start_background(paths)}
    if command == "stop":
        return {"stopped": stop_background(paths)}
    if command == "status":
        return status_data(paths)
    if command == "show":
        return public_task(load_task(paths, args.id), reveal_link=args.reveal_link)
    if command == "attach":
        target: dict[str, Any] = {
            "kind": "fresh" if args.fresh else "session",
            "tool": args.tool,
        }
        if args.session_id:
            target["session_id"] = args.session_id
        if args.executable:
            target["executable"] = args.executable
        return public_task(
            attach_task(
                paths,
                args.id,
                target,
                allow_session_permissions=args.allow_session_permissions,
            )
        )
    if command == "cancel":
        return public_task(cancel_task(paths, args.id))
    if command == "retry":
        return retry_task(paths, args.id)
    raise WireError(f"unsupported command: {command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_command(args, resolve_paths())
    except KeyboardInterrupt:
        code = 130
        error = "wait interrupted"
    except SessionUnavailableError as exc:
        code = 3
        error = str(exc)
    except UnsafeTriggerError as exc:
        code = 4
        error = str(exc)
    except WireError as exc:
        code = 1
        error = str(exc)
    else:
        _emit(result, as_json=bool(getattr(args, "json", False)))
        return 0
    if getattr(args, "json", False):
        _emit({"error": error, "code": code}, as_json=True)
    else:
        print(f"wire-trigger: {error}", file=sys.stderr)
    return code


def create_task(
    paths: Paths,
    *,
    summary: str,
    prompt: str,
    cwd: str | Path,
    target: Mapping[str, Any],
    allow_unconfirmed_get: bool = False,
    allow_session_permissions: bool = False,
    expiry_days: int = DEFAULT_EXPIRY_DAYS,
    server: str = DEFAULT_SERVER,
    start_listener: bool = False,
) -> dict[str, Any]:
    normalized_target = normalize_target(target)
    if not allow_unconfirmed_get:
        raise UnsafeTriggerError("unconfirmed GET trigger requires explicit acknowledgement")
    if normalized_target.get("kind") == "session" and not allow_session_permissions:
        raise UnsafeTriggerError("session permissions require explicit acknowledgement")
    workdir = Path(cwd).expanduser().resolve()
    if not workdir.is_dir():
        raise WireError(f"working directory does not exist: {workdir}")
    if not summary.strip() or not prompt.strip():
        raise WireError("summary and prompt must not be empty")

    ensure_private_dir(paths.state)
    ensure_private_dir(paths.tasks)
    ensure_private_dir(paths.claims)
    ensure_private_dir(paths.runs)
    now = utc_now()
    arm_at = now + timedelta(seconds=DEFAULT_GRACE_SECONDS)
    # ntfy publishes integer Unix seconds, so persist a boundary it can represent.
    if arm_at.microsecond:
        arm_at = arm_at.replace(microsecond=0) + timedelta(seconds=1)
    task_id = "trg_" + secrets.token_urlsafe(9)
    topic = make_topic()
    task: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": task_id,
        "state": "armed",
        "summary": summary.strip(),
        "prompt": prompt.strip(),
        "cwd": str(workdir),
        "created_at": iso(now),
        "arm_at": iso(arm_at),
        "expires_at": iso(now + timedelta(days=expiry_days)),
        "created_by": str(normalized_target.get("tool", "unknown")),
        "target": normalized_target,
        "transport": {
            "kind": "ntfy",
            "server": server.rstrip("/"),
            "topic": topic,
        },
        "revision": 1,
        "claim_generation": None,
        "attempts": 0,
        "latest_run": None,
    }
    save_task(paths, task)
    if start_listener:
        start_background(paths)
    return task


if __name__ == "__main__":
    raise SystemExit(main())
