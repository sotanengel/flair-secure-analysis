"""reporter モジュールのテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from worker.analyzer import ForecastResult
from worker.preprocessor import PreprocessResult
from worker.reporter import save_results


def _make_preprocess_result(n: int = 50) -> PreprocessResult:
    y = np.sin(np.arange(n, dtype=float))
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    return PreprocessResult(
        y=y,
        freq="D",
        index=pd.DatetimeIndex(index),
        warnings=["テスト警告"],
        stats={
            "n": n,
            "mean": float(y.mean()),
            "std": float(y.std()),
            "min": float(y.min()),
            "max": float(y.max()),
            "zero_rate": 0.0,
            "missing_filled": 0,
            "duplicates_removed": 0,
        },
    )


def _make_forecast_result(horizon: int = 7) -> ForecastResult:
    samples = np.random.default_rng(0).normal(size=(50, horizon))
    return ForecastResult(
        point=samples.mean(axis=0),
        lower=np.percentile(samples, 10, axis=0),
        upper=np.percentile(samples, 90, axis=0),
        samples=samples,
        horizon=horizon,
        freq="D",
        seed=42,
        n_samples=50,
        flaircast_version="0.2.0",
        warnings=[],
    )


class TestSaveResults:
    def test_creates_files(self, tmp_dir: Path):
        pre = _make_preprocess_result()
        fc = _make_forecast_result()
        files = save_results(
            tmp_dir,
            job_id="test-job-1",
            input_filename="test.csv",
            input_sha256="abc123",
            input_stats={"row_count": 50, "columns": ["timestamp", "value"]},
            preprocess_result=pre,
            forecast_result=fc,
            config={"horizon": 7, "seed": 42},
        )
        # forecast.csv + report.json + forecast_chart.png (グラフが生成された場合)
        assert len(files) >= 2
        for f in files:
            assert Path(f).exists()

    def test_forecast_csv_columns(self, tmp_dir: Path):
        import csv

        pre = _make_preprocess_result()
        fc = _make_forecast_result(horizon=5)
        save_results(
            tmp_dir,
            job_id="job-csv",
            input_filename="x.csv",
            input_sha256="sha",
            input_stats={},
            preprocess_result=pre,
            forecast_result=fc,
            config={},
        )
        with (tmp_dir / "forecast.csv").open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 5
        assert "timestamp" in rows[0]
        assert "point" in rows[0]
        assert "lower_10" in rows[0]
        assert "upper_90" in rows[0]

    def test_report_json_has_required_fields(self, tmp_dir: Path):
        pre = _make_preprocess_result()
        fc = _make_forecast_result()
        save_results(
            tmp_dir,
            job_id="job-json",
            input_filename="x.csv",
            input_sha256="deadbeef",
            input_stats={},
            preprocess_result=pre,
            forecast_result=fc,
            config={"seed": 42},
        )
        with (tmp_dir / "report.json").open() as f:
            report = json.load(f)

        assert report["job_id"] == "job-json"
        assert report["input"]["sha256"] == "deadbeef"
        assert report["reproducibility"]["flaircast_version"] == "0.2.0"
        assert report["reproducibility"]["seed"] == 42
        assert "warnings" in report
        assert "library_versions" in report
