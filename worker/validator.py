"""入力ファイル検証モジュール。

受け入れ条件:
- 拡張子 allowlist: .csv のみ（Phase 1）
- 最大ファイルサイズ: 500 MB
- 最大行数: 1,000,000
- 最大列数: 100
- パストラバーサル対策: ファイル名を内部で再採番
- 列構造: 日時列・値列の存在確認
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

ALLOWED_EXTENSIONS = {".csv"}
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
MAX_ROWS = 1_000_000
MAX_COLUMNS = 100

# ファイル名の安全化: 英数字・ハイフン・アンダースコア・ドットのみ許可
_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._\-]")


class ValidationError(ValueError):
    """入力検証エラー。"""


def sanitize_filename(original: str) -> str:
    """パストラバーサルを防ぐためファイル名を安全な形式に変換する。"""
    name = Path(original).name  # ディレクトリ部分を除去
    name = _SAFE_FILENAME_RE.sub("_", name)
    return name or "input.csv"


def compute_sha256(path: Path) -> str:
    """ファイルの SHA-256 ハッシュを計算する。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_file(
    path: Path,
    *,
    datetime_col: str | None = None,
    value_col: str | None = None,
) -> dict:
    """ファイルを検証し、検証結果サマリーを返す。

    Returns:
        dict: {
            "sha256": str,
            "size_bytes": int,
            "row_count": int,
            "columns": list[str],
        }

    Raises:
        ValidationError: 検証失敗時。
    """
    if not path.exists():
        raise ValidationError(f"ファイルが存在しません: {path}")

    # 拡張子チェック
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"許可されていない拡張子です: {suffix!r}。許可: {sorted(ALLOWED_EXTENSIONS)}"
        )

    # ファイルサイズチェック
    size = path.stat().st_size
    if size == 0:
        raise ValidationError("ファイルが空です")
    if size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            f"ファイルサイズ上限を超えています: {size:,} bytes (上限 {MAX_FILE_SIZE_BYTES:,} bytes)"
        )

    # SHA-256 計算
    sha256 = compute_sha256(path)

    # CSV 構造チェック
    row_count = 0
    columns: list[str] = []

    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)

        try:
            header = next(reader)
        except StopIteration:
            raise ValidationError("CSV にヘッダー行がありません") from None

        columns = [c.strip() for c in header]

        if len(columns) == 0:
            raise ValidationError("CSV の列数が 0 です")
        if len(columns) > MAX_COLUMNS:
            raise ValidationError(
                f"列数が上限を超えています: {len(columns)} (上限 {MAX_COLUMNS})"
            )

        for _row in reader:
            row_count += 1
            if row_count > MAX_ROWS:
                raise ValidationError(
                    f"行数が上限を超えています (上限 {MAX_ROWS:,} 行)"
                )

    # 列名の存在チェック
    if datetime_col and datetime_col not in columns:
        raise ValidationError(
            f"日時列 {datetime_col!r} が見つかりません。利用可能な列: {columns}"
        )
    if value_col and value_col not in columns:
        raise ValidationError(
            f"値列 {value_col!r} が見つかりません。利用可能な列: {columns}"
        )

    return {
        "sha256": sha256,
        "size_bytes": size,
        "row_count": row_count,
        "columns": columns,
    }
