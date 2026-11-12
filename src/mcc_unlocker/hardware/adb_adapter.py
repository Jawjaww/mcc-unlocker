"""Subprocess-based ADB host adapter (USB first)."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result
from .interfaces import AdbTarget, ProcessResult, ProcessRunner


@dataclass
class SubprocessRunner:
    async def run(self, args: Sequence[str], *, timeout: float = 60.0) -> ProcessResult:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return ProcessResult(returncode=124, stdout="", stderr="timeout")
        return ProcessResult(
            returncode=process.returncode or 0,
            stdout=stdout_b.decode("utf-8", "replace"),
            stderr=stderr_b.decode("utf-8", "replace"),
        )


@dataclass
class AdbAdapter:
    adb_path: Path | str = "adb"
    runner: ProcessRunner = field(default_factory=SubprocessRunner)

    @property
    def _adb(self) -> str:
        return str(self.adb_path)

    async def version(self) -> Result[str]:
        try:
            result = await self.runner.run([self._adb, "version"], timeout=10)
        except FileNotFoundError as exc:
            return Err(ErrorCode.ERR_ENV_ADB_MISSING, details={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return Err(ErrorCode.ERR_ADB_NOT_AVAILABLE, details={"error": str(exc)})
        if result.returncode != 0:
            return Err(
                ErrorCode.ERR_ADB_NOT_AVAILABLE,
                details={"stderr": result.stderr.strip(), "code": result.returncode},
            )
        line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        return Ok(line)

    async def list_targets(self) -> Result[Sequence[AdbTarget]]:
        try:
            result = await self.runner.run([self._adb, "devices", "-l"], timeout=15)
        except Exception as exc:  # noqa: BLE001
            return Err(ErrorCode.ERR_ADB_NOT_AVAILABLE, details={"error": str(exc)})
        if result.returncode != 0:
            return Err(
                ErrorCode.ERR_ADB_NOT_AVAILABLE,
                details={"stderr": result.stderr.strip(), "code": result.returncode},
            )
        return Ok(tuple(_parse_devices(result.stdout)))

    async def shell(self, serial: str, command: str) -> Result[str]:
        result = await self._run_device(serial, ["shell", command], timeout=30)
        if isinstance(result, Err):
            return result
        return Ok(result.value.stdout)

    async def push(self, serial: str, local_path: Path | str, remote_path: str) -> Result[str]:
        source = Path(local_path)
        if not source.is_file():
            return Err(
                ErrorCode.ERR_ADB_COMMAND_FAILED,
                details={"reason": "local file missing", "path": str(source)},
            )
        result = await self._run_device(serial, ["push", str(source), remote_path], timeout=180)
        if isinstance(result, Err):
            return result
        return Ok(result.value.stdout.strip())

    async def pull(self, serial: str, remote_path: str, local_path: Path | str) -> Result[str]:
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = await self._run_device(serial, ["pull", remote_path, str(destination)], timeout=180)
        if isinstance(result, Err):
            return result
        if not destination.is_file():
            return Err(
                ErrorCode.ERR_ADB_COMMAND_FAILED,
                details={"reason": "pull produced no file", "remote": remote_path},
            )
        return Ok(result.value.stdout.strip())

    async def _run_device(self, serial: str, args: Sequence[str], *, timeout: float) -> Result[ProcessResult]:
        try:
            proc = await self.runner.run([self._adb, "-s", serial, *args], timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            return Err(ErrorCode.ERR_ADB_COMMAND_FAILED, details={"error": str(exc)})
        if proc.returncode == 124:
            return Err(ErrorCode.ERR_ADB_TIMEOUT, details={"args": list(args)})
        combined = f"{proc.stderr}\n{proc.stdout}".lower()
        if "unauthorized" in combined:
            return Err(ErrorCode.ERR_ADB_UNAUTHORIZED, details={"args": list(args)})
        if proc.returncode != 0:
            return Err(
                ErrorCode.ERR_ADB_COMMAND_FAILED,
                details={
                    "args": list(args),
                    "code": proc.returncode,
                    "stderr": proc.stderr.strip()[-1000:],
                },
            )
        return Ok(proc)


def _parse_devices(output: str) -> list[AdbTarget]:
    targets: list[AdbTarget] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        transport = "tcp" if re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", serial) else "usb"
        host = port = None
        if transport == "tcp":
            host, _, port_str = serial.partition(":")
            port = int(port_str) if port_str.isdigit() else 5555
        targets.append(AdbTarget(serial=serial, transport=transport, host=host, port=port, state=state))
    return targets


__all__ = ["AdbAdapter", "SubprocessRunner", "_parse_devices"]
