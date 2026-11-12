"""Durable operation journal for sensitive actions.

The journal records intent, target, backup, reached phase and verification. It
is evidence of what the application *attempted*; it is never proof of the
robot's current state. An interrupted operation is surfaced at startup and must
not be resumed automatically.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result
from .filesystem import ensure_dir

TERMINAL_OK = frozenset({"succeeded", "failed", "cancelled"})
REVIEW_STATUSES = frozenset({"started", "in_progress", "indeterminate"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class OperationJournal:
    def __init__(self, path: Path | str, *, session_id: str | None = None) -> None:
        self.path = Path(path)
        self.session_id = session_id or uuid.uuid4().hex
        self._lock = threading.Lock()

    def _append(self, record: Mapping[str, Any]) -> Result[dict[str, Any]]:
        entry = dict(record)
        entry.setdefault("timestamp", _now())
        entry.setdefault("session_id", self.session_id)
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        try:
            ensure_dir(self.path.parent)
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.chmod(self.path, 0o600)
                except OSError:
                    pass
        except OSError as exc:
            return Err(
                ErrorCode.ERR_JOURNAL_UNAVAILABLE,
                details={"path": str(self.path), "error": str(exc)},
            )
        return Ok(entry)

    def record_start(
        self,
        *,
        operation_id: str,
        operation: str,
        target: str,
        backup_path: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        if self.last_status(operation_id) is not None:
            return Err(
                ErrorCode.ERR_JOURNAL_UNAVAILABLE,
                details={"reason": "operation already started", "operation_id": operation_id},
            )
        return self._append(
            {
                "operation_id": operation_id,
                "operation": operation,
                "target": target,
                "backup_path": backup_path,
                "phase": "start",
                "status": "started",
                "details": dict(details or {}),
            }
        )

    def record_phase(
        self,
        *,
        operation_id: str,
        phase: str,
        details: Mapping[str, Any] | None = None,
        status: str = "in_progress",
    ) -> Result[dict[str, Any]]:
        last = self.last_status(operation_id)
        if last is None or last.get("status") in TERMINAL_OK | {"indeterminate"}:
            return Err(
                ErrorCode.ERR_JOURNAL_UNAVAILABLE,
                details={"reason": "operation not active", "operation_id": operation_id},
            )
        return self._append(
            {
                "operation_id": operation_id,
                "phase": phase,
                "status": status,
                "details": dict(details or {}),
            }
        )

    def record_finish(
        self,
        *,
        operation_id: str,
        status: str,
        verification: Mapping[str, Any] | None = None,
        details: Mapping[str, Any] | None = None,
        indeterminate: bool = False,
    ) -> Result[dict[str, Any]]:
        if indeterminate:
            status = "indeterminate"
        if status not in TERMINAL_OK | {"indeterminate"}:
            return Err(
                ErrorCode.ERR_JOURNAL_UNAVAILABLE,
                details={"reason": "invalid terminal status", "status": status},
            )
        last = self.last_status(operation_id)
        if last is None:
            return Err(
                ErrorCode.ERR_JOURNAL_UNAVAILABLE,
                details={"reason": "operation not started", "operation_id": operation_id},
            )
        if last.get("status") in TERMINAL_OK | {"indeterminate"}:
            return Err(
                ErrorCode.ERR_JOURNAL_UNAVAILABLE,
                details={"reason": "operation already finished", "operation_id": operation_id},
            )
        return self._append(
            {
                "operation_id": operation_id,
                "phase": "finish",
                "status": status,
                "verification": dict(verification or {}),
                "details": dict(details or {}),
            }
        )

    def load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        records: list[dict[str, Any]] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
        except OSError:
            return []
        return records

    def last_status(self, operation_id: str) -> dict[str, Any] | None:
        last = None
        for record in self.load():
            if record.get("operation_id") == operation_id:
                last = record
        return last

    def interrupted_operations(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in self.load():
            operation_id = record.get("operation_id")
            if isinstance(operation_id, str):
                grouped.setdefault(operation_id, []).append(record)
        interrupted: list[dict[str, Any]] = []
        for operation_id, records in grouped.items():
            last = records[-1]
            status = str(last.get("status", ""))
            if status in REVIEW_STATUSES:
                interrupted.append(
                    {
                        "operation_id": operation_id,
                        "status": status,
                        "phase": last.get("phase"),
                        "last_record": last,
                        "records": records,
                    }
                )
        interrupted.sort(key=lambda item: str(item["last_record"].get("timestamp", "")))
        return interrupted

    def mark_indeterminate(
        self,
        *,
        operation_id: str,
        reason: str,
        details: Mapping[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        return self.record_finish(
            operation_id=operation_id,
            status="indeterminate",
            details={"reason": reason, **dict(details or {})},
            indeterminate=True,
        )


def scan_interrupted_journals(roots: Iterable[Path | str]) -> list[dict[str, Any]]:
    """Find interrupted operations without resuming anything.

    Reads every ``journal.jsonl`` under the given roots. Returns descriptors with
    the journal path so the UI/CLI can explain what happened and ask for a new,
    safe inspection.
    """
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        base = Path(root)
        if not base.exists():
            continue
        try:
            candidates = list(base.rglob("journal.jsonl"))
        except OSError:
            continue
        for path in candidates:
            try:
                key = str(path.resolve())
            except OSError:
                key = str(path)
            if key in seen:
                continue
            seen.add(key)
            journal = OperationJournal(path)
            for item in journal.interrupted_operations():
                descriptor = dict(item)
                descriptor["journal_path"] = str(path)
                found.append(descriptor)
    return found


__all__ = [
    "OperationJournal",
    "REVIEW_STATUSES",
    "TERMINAL_OK",
    "scan_interrupted_journals",
]
