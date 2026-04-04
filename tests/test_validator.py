"""validator モジュールのテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from worker.validator import (
    ValidationError,
    compute_sha256,
    sanitize_filename,
    validate_file,
)


class TestSanitizeFilename:
    def test_normal(self):
        assert sanitize_filename("data.csv") == "data.csv"

    def test_path_traversal(self):
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert ".." not in result

    def test_special_chars(self):
        result = sanitize_filename("my file (1).csv")
        assert " " not in result
        assert "(" not in result


class TestComputeSha256:
    def test_returns_64_hex_chars(self, tmp_dir: Path):
        p = tmp_dir / "test.txt"
        p.write_text("hello")
        result = compute_sha256(p)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self, tmp_dir: Path):
        p = tmp_dir / "test.txt"
        p.write_text("hello world")
        assert compute_sha256(p) == compute_sha256(p)


class TestValidateFile:
    def test_valid_csv(self, sample_csv: Path):
        result = validate_file(sample_csv, datetime_col="timestamp", value_col="value")
        assert result["row_count"] == 100
        assert "timestamp" in result["columns"]
        assert "value" in result["columns"]
        assert len(result["sha256"]) == 64
        assert result["size_bytes"] > 0

    def test_missing_file(self, tmp_dir: Path):
        with pytest.raises(ValidationError, match="存在しません"):
            validate_file(tmp_dir / "nonexistent.csv")

    def test_invalid_extension(self, tmp_dir: Path):
        p = tmp_dir / "data.txt"
        p.write_text("a,b\n1,2")
        with pytest.raises(ValidationError, match="拡張子"):
            validate_file(p)

    def test_empty_file(self, tmp_dir: Path):
        p = tmp_dir / "empty.csv"
        p.write_bytes(b"")
        with pytest.raises(ValidationError, match="空"):
            validate_file(p)

    def test_missing_datetime_col(self, sample_csv: Path):
        with pytest.raises(ValidationError, match="日時列"):
            validate_file(sample_csv, datetime_col="nonexistent", value_col="value")

    def test_missing_value_col(self, sample_csv: Path):
        with pytest.raises(ValidationError, match="値列"):
            validate_file(sample_csv, datetime_col="timestamp", value_col="nonexistent")

    def test_no_col_spec_succeeds(self, sample_csv: Path):
        result = validate_file(sample_csv)
        assert "columns" in result

    def test_no_header(self, tmp_dir: Path):
        p = tmp_dir / "empty_header.csv"
        p.write_bytes(b"")
        with pytest.raises(ValidationError):
            validate_file(p)
