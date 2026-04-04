"""preprocessor モジュールのテスト。"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from worker.preprocessor import PreprocessError, PreprocessResult, preprocess


def make_csv(tmp_dir: Path, rows: list[tuple], header=("timestamp", "value")) -> Path:
    p = tmp_dir / "test.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return p


class TestPreprocess:
    def test_basic(self, sample_csv: Path):
        result = preprocess(sample_csv, datetime_col="timestamp", value_col="value", freq="D")
        assert isinstance(result, PreprocessResult)
        assert len(result.y) == 100
        assert result.freq == "D"
        assert isinstance(result.y, np.ndarray)

    def test_freq_inferred_when_none(self, sample_csv: Path):
        result = preprocess(sample_csv, datetime_col="timestamp", value_col="value")
        assert result.freq in {"H", "D", "W", "ME", "QE", "YE", "T"}
        # 自動推定の警告が出ること
        assert any("自動推定" in w for w in result.warnings)

    def test_missing_values_ffill(self, tmp_dir: Path):
        rows = [
            ("2024-01-01", 10),
            ("2024-01-02", ""),  # 欠損
            ("2024-01-03", 30),
        ]
        p = make_csv(tmp_dir, rows)
        result = preprocess(p, datetime_col="timestamp", value_col="value", freq="D")
        assert len(result.y) == 3
        # forward fill: 2024-01-02 は 10 になる
        assert result.y[1] == 10.0
        assert any("欠損" in w for w in result.warnings)

    def test_missing_values_stop(self, tmp_dir: Path):
        rows = [("2024-01-01", 10), ("2024-01-02", ""), ("2024-01-03", 30)]
        p = make_csv(tmp_dir, rows)
        with pytest.raises(PreprocessError, match="欠損値"):
            preprocess(
                p, datetime_col="timestamp", value_col="value", freq="D", missing_policy="stop"
            )

    def test_duplicate_timestamps(self, tmp_dir: Path):
        rows = [
            ("2024-01-01", 10),
            ("2024-01-01", 20),  # 重複
            ("2024-01-02", 30),
        ]
        p = make_csv(tmp_dir, rows)
        result = preprocess(p, datetime_col="timestamp", value_col="value", freq="D")
        assert len(result.y) == 2
        assert any("重複" in w for w in result.warnings)

    def test_zero_rate_warning(self, tmp_dir: Path):
        # 50点のデータ、日付は複数月にまたがるよう生成
        rows = []
        for i in range(50):
            month = (i // 28) + 1
            day = (i % 28) + 1
            ts = f"2024-{month:02d}-{day:02d}"
            rows.append((ts, 0 if i < 35 else 1))
        p = make_csv(tmp_dir, rows)
        result = preprocess(p, datetime_col="timestamp", value_col="value", freq="D")
        assert any("ゼロ" in w for w in result.warnings)

    def test_short_series_warning(self, tmp_dir: Path):
        rows = [(f"2024-01-{i + 1:02d}", i) for i in range(10)]
        p = make_csv(tmp_dir, rows)
        result = preprocess(p, datetime_col="timestamp", value_col="value", freq="D")
        assert any("少ない" in w or "少なすぎ" in w for w in result.warnings)

    def test_invalid_datetime_col(self, sample_csv: Path):
        with pytest.raises(PreprocessError, match="日時列"):
            preprocess(sample_csv, datetime_col="bad_col", value_col="value")

    def test_invalid_value_col(self, sample_csv: Path):
        with pytest.raises(PreprocessError, match="値列"):
            preprocess(sample_csv, datetime_col="timestamp", value_col="bad_col")
