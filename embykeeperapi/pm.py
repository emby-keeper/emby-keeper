import asyncio
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
from subprocess import PIPE, STDOUT, Popen
from threading import Lock, Thread
from typing import Optional

import httpx
import psutil
from fastapi import APIRouter, Depends, HTTPException

from .auth import require_auth
from .events import broadcast_from_sync
from .settings import panel_settings


class ProcessManager:
    def __init__(self):
        self.proc: Optional[Popen] = None
        self.host: str = "127.0.0.1"
        self.port: int = 8001
        self.exit_code: Optional[int] = None
        self.last_error: str = ""
        self._recent_output = deque(maxlen=120)
        self._output_lock = Lock()
        self._expected_stop = False

    def _shared_output_path(self) -> Path:
        target_key = f"{self.host}:{self.port}".encode("utf-8")
        target_digest = hashlib.sha1(target_key).hexdigest()[:16]
        return Path.home() / ".embykeeper" / "panel" / f"pm-output-{target_digest}.json"

    def _memory_output_snapshot(self) -> list:
        with self._output_lock:
            return list(self._recent_output)

    def _persist_output_snapshot(self, pid: Optional[int] = None):
        payload = {
            "pid": pid,
            "lines": self._memory_output_snapshot(),
        }
        path = self._shared_output_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _load_persisted_output_snapshot(self, active_pid: Optional[int]) -> list:
        path = self._shared_output_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []

        if not isinstance(payload, dict):
            return []

        stored_pid = payload.get("pid")
        if active_pid is not None and stored_pid not in {None, active_pid}:
            return []

        lines = payload.get("lines")
        if not isinstance(lines, list):
            return []

        return [line.rstrip() for line in lines if isinstance(line, str) and line.rstrip()]

    def _broadcast_status(self):
        broadcast_from_sync("status", "status", self.status())

    def is_running(self) -> bool:
        return self._get_active_pid() is not None

    def _is_spawned_process_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def owns_backend(self) -> bool:
        return self.proc is not None

    def managed_pid(self) -> Optional[int]:
        if self._is_spawned_process_running() and self.proc:
            return self.proc.pid
        return None

    def _host_matches(self, candidate: str) -> bool:
        normalized = candidate.strip()
        if self.host in {"127.0.0.1", "localhost"}:
            return normalized in {"127.0.0.1", "0.0.0.0", "::", "::1", "localhost"}
        if self.host in {"0.0.0.0", "::"}:
            return True
        return normalized == self.host

    def _is_backend_process(self, pid: Optional[int]) -> bool:
        if not pid:
            return False
        try:
            process = psutil.Process(pid)
            cmdline = process.cmdline()
        except (psutil.Error, OSError):
            return False

        if not cmdline:
            return False

        command = " ".join(cmdline)
        executable_names = {Path(part).name for part in cmdline}
        return (
            "embykeeper" in command
            and "--api" in cmdline
            and (
                "python" in executable_names
                or "python3" in executable_names
                or any(name.startswith("python") for name in executable_names)
            )
        )

    def _find_listener_pid(self) -> Optional[int]:
        try:
            connections = psutil.net_connections(kind="tcp")
        except (psutil.AccessDenied, psutil.Error):
            return None

        for connection in connections:
            if connection.status != psutil.CONN_LISTEN:
                continue
            if not connection.laddr:
                continue
            if connection.laddr.port != self.port:
                continue
            if not self._host_matches(connection.laddr.ip):
                continue
            if connection.pid:
                return connection.pid
        return None

    def _find_external_backend_pid(self) -> Optional[int]:
        listener_pid = self._find_listener_pid()
        if not listener_pid:
            return None
        if self._is_spawned_process_running() and self.proc and listener_pid == self.proc.pid:
            return listener_pid
        return listener_pid if self._is_backend_process(listener_pid) else None

    def _get_active_pid(self) -> Optional[int]:
        if self._is_spawned_process_running() and self.proc:
            return self.proc.pid
        return self._find_external_backend_pid()

    def _wait_for_pid_exit(self, pid: int, timeout: float = 10.0) -> Optional[int]:
        try:
            process = psutil.Process(pid)
            return process.wait(timeout=timeout)
        except psutil.TimeoutExpired:
            return None
        except psutil.NoSuchProcess:
            return 0
        except (psutil.Error, OSError):
            return None

    def is_managed_pid_running(self, pid: int) -> bool:
        return self.proc is not None and self.proc.pid == pid and self.proc.poll() is None

    def request_stop(self, pid: Optional[int] = None) -> Optional[int]:
        active_pid = pid or self._get_active_pid()
        if not active_pid:
            return None
        self._expected_stop = True
        self.last_error = ""
        self._broadcast_status()
        try:
            os.kill(active_pid, signal.SIGINT)
        except ProcessLookupError:
            self._expected_stop = False
            if self.proc and self.proc.pid == active_pid:
                self.proc = None
            self._broadcast_status()
            return None
        return active_pid

    def force_stop(self, pid: Optional[int] = None, sig: int = signal.SIGTERM) -> Optional[int]:
        active_pid = pid or self._get_active_pid()
        if not active_pid:
            return self.exit_code
        try:
            os.kill(active_pid, sig)
        except ProcessLookupError:
            pass

        exit_code = self._wait_for_pid_exit(active_pid, timeout=5)
        self.exit_code = exit_code
        if self.proc and self.proc.pid == active_pid:
            try:
                self.proc.wait(timeout=0.1)
            except Exception:
                pass
            if self.proc.poll() is not None:
                self.proc = None
        self._expected_stop = False
        self._broadcast_status()
        return exit_code

    def _append_output(self, line: str):
        cleaned = line.rstrip()
        if not cleaned:
            return
        with self._output_lock:
            self._recent_output.append(cleaned)
        self._persist_output_snapshot(self.managed_pid())
        self._broadcast_status()

    def _clear_output(self):
        with self._output_lock:
            self._recent_output.clear()
        self._persist_output_snapshot(None)

    def _output_snapshot(self, active_pid: Optional[int] = None):
        output = self._memory_output_snapshot()
        if output:
            return output
        return self._load_persisted_output_snapshot(active_pid)

    def _display_output_snapshot(self, active_pid: Optional[int]) -> list:
        output = self._output_snapshot(active_pid)
        if output or not active_pid:
            return output

            return []

    def _watch_process_output(self, proc: Popen):
        try:
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    if line == "":
                        break
                    self._append_output(line)
        finally:
            returncode = proc.wait()
            if self.proc is proc:
                self.exit_code = returncode
                self.proc = None
                self._persist_output_snapshot(None)
                self._broadcast_status()
            if self._expected_stop:
                self._expected_stop = False
                return
            if returncode == 0:
                self.last_error = self.last_error or "Embykeeper 已停止运行"
            else:
                self.last_error = self.last_error or f"Embykeeper 已退出，退出码 {returncode}"
            self._broadcast_status()

    def start(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or self.host
        self.port = port or self.port

        active_pid = self._get_active_pid()
        if active_pid:
            self.exit_code = None
            self.last_error = ""
            self._expected_stop = False
            self._append_output("Embykeeper 已在运行")
            self._broadcast_status()
            return

        listener_pid = self._find_listener_pid()
        if listener_pid:
            self.last_error = f"{self.host}:{self.port} 已被其他程序占用 (pid {listener_pid})"
            self._append_output(self.last_error)
            self._broadcast_status()
            return

        if self._is_spawned_process_running():
            return

        self.exit_code = None
        self.last_error = ""
        self._expected_stop = False
        self._clear_output()
        python = sys.executable or os.environ.get("PYTHON", "python")
        env = os.environ.copy()
        # Do not pass panel auth to backend; backend API should be open behind proxy
        env.pop("EK_WEBPASS", None)

        panel_settings.reload()
        backend_basedir = panel_settings.resolved_backend_basedir()
        backend_config = panel_settings.resolved_backend_config_file()
        backend_basedir.mkdir(parents=True, exist_ok=True)

        args = [
            python,
            "-m",
            "embykeeper",
            str(backend_config),
            "--basedir",
            str(backend_basedir),
            "--api",
            "--api-host",
            self.host,
            "--api-port",
            str(self.port),
        ]
        # Start detached enough to receive signals
        self._append_output(f"$ {' '.join(args)}")
        self.proc = Popen(args, env=env, stdout=PIPE, stderr=STDOUT, text=True, bufsize=1)
        self._persist_output_snapshot(self.proc.pid)
        self._broadcast_status()
        Thread(target=self._watch_process_output, args=(self.proc,), daemon=True).start()

    async def wait_until_ready(self, timeout: float = 15.0, interval: float = 0.25) -> bool:
        target = f"http://{self.host}:{self.port}/"
        deadline = asyncio.get_running_loop().time() + timeout

        async with httpx.AsyncClient(timeout=1.0, trust_env=False) as client:
            while asyncio.get_running_loop().time() < deadline:
                if self._get_active_pid() is None:
                    return False
                try:
                    resp = await client.get(target)
                    if resp.status_code < 500:
                        return True
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(interval)

        self.last_error = self.last_error or "Embykeeper 启动超时，请稍后重试"
        self._broadcast_status()
        return False

    def stop(self):
        active_pid = self.request_stop()
        if not active_pid:
            return
        exit_code = self._wait_for_pid_exit(active_pid, timeout=10)
        if exit_code is None:
            self.force_stop(active_pid)
            return

        self.exit_code = exit_code
        if self.proc and self.proc.pid == active_pid:
            try:
                self.proc.wait(timeout=0.1)
            except Exception:
                pass
            self.proc = None
        self._expected_stop = False
        self._broadcast_status()

    def status(self):
        active_pid = self._get_active_pid()
        panel_settings.reload()
        return {
            "running": active_pid is not None,
            "pid": active_pid,
            "host": self.host,
            "port": self.port,
            "target": f"http://{self.host}:{self.port}",
            "exit_code": self.exit_code,
            "last_error": self.last_error,
            "recent_output": self._display_output_snapshot(active_pid),
            "backend_basedir": str(panel_settings.resolved_backend_basedir()),
            "backend_config_file": str(panel_settings.resolved_backend_config_file()),
        }

    def restart(self):
        host, port = self.host, self.port
        self.stop()
        self.start(host, port)


pm = ProcessManager()
router = APIRouter()


@router.post("/pm/start")
async def pm_start(host: Optional[str] = None, port: Optional[int] = None, _: bool = Depends(require_auth)):
    try:
        pm.start(host, port)
        ready = await pm.wait_until_ready()
        status = pm.status()
        if not ready:
            raise HTTPException(status_code=500, detail=status.get("last_error") or "Embykeeper 启动失败")
        return {"success": True, **status}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"启动 Embykeeper 失败: {e}")


@router.post("/pm/stop")
async def pm_stop(_: bool = Depends(require_auth)):
    try:
        pm.stop()
        return {"success": True, **pm.status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止 Embykeeper 失败: {e}")


@router.post("/pm/restart")
async def pm_restart(_: bool = Depends(require_auth)):
    try:
        pm.restart()
        ready = await pm.wait_until_ready()
        status = pm.status()
        if not ready:
            raise HTTPException(status_code=500, detail=status.get("last_error") or "Embykeeper 重启失败")
        return {"success": True, **status}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"重启 Embykeeper 失败: {e}")


@router.get("/pm/status")
async def pm_status(_: bool = Depends(require_auth)):
    try:
        return pm.status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取 Embykeeper 状态失败: {e}")
