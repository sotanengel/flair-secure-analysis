"""監査ログ記録モジュール。

ジョブの開始・終了・エラーを JSONL 形式で logs/audit.jsonl に追記する。
ログ本文に入力データの内容（生データ）は含めない。
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class AuditLogger:
    """ジョブ単位の監査ログを JSONL ファイルへ記録する。"""

    def __init__(self, log_dir: Path, job_id: str) -> None:
        self.log_dir = log_dir
        self.job_id = job_id
        self.log_path = log_dir / "audit.jsonl"
        log_dir.mkdir(parents=True, exist_ok=True)

    def _write(self, record: dict[str, Any]) -> None:
        record["job_id"] = self.job_id
        record["logged_at"] = _utcnow()
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log_start(
        self,
        *,
        input_filename: str,
        input_sha256: str,
        config: dict[str, Any],
        image_digest: str | None = None,
        library_versions: dict[str, str] | None = None,
    ) -> None:
        """ジョブ開始を記録する。"""
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
        self._write(
            {
                "event": "job_start",
                "user": user,
                "started_at": _utcnow(),
                "input_filename": input_filename,
                "input_sha256": input_sha256,
                "config": config,
                "image_digest": image_digest,
                "library_versions": library_versions or {},
            }
        )

    def log_success(
        self,
        *,
        output_files: list[str],
        warnings: list[str] | None = None,
    ) -> None:
        """ジョブ成功を記録する。"""
        self._write(
            {
                "event": "job_success",
                "finished_at": _utcnow(),
                "output_files": output_files,
                "warnings": warnings or [],
            }
        )

    def log_failure(
        self,
        *,
        error_type: str,
        error_summary: str,
        exc: BaseException | None = None,
    ) -> None:
        """ジョブ失敗を記録する（スタックトレースは含めるが生データは含めない）。"""
        tb = traceback.format_exc() if exc is not None else None
        self._write(
            {
                "event": "job_failure",
                "finished_at": _utcnow(),
                "error_type": error_type,
                "error_summary": error_summary,
                "traceback": tb,
            }
        )

    def log_quarantine(self, *, input_filename: str, reason: str) -> None:
        """不正ファイルを検疫記録する。"""
        self._write(
            {
                "event": "quarantine",
                "input_filename": input_filename,
                "reason": reason,
            }
        )
