"""analyzer モジュールのテスト。"""

from __future__ import annotations

import numpy as np

from worker.analyzer import ForecastResult, run_forecast


class TestRunForecast:
    def test_basic(self, sample_series: np.ndarray):
        result = run_forecast(sample_series, "H", horizon=12, seed=42, n_samples=50)
        assert isinstance(result, ForecastResult)
        assert result.point.shape == (12,)
        assert result.lower.shape == (12,)
        assert result.upper.shape == (12,)
        assert result.horizon == 12
        assert result.seed == 42

    def test_reproducibility(self, sample_series: np.ndarray):
        r1 = run_forecast(sample_series, "H", horizon=12, seed=0, n_samples=50)
        r2 = run_forecast(sample_series, "H", horizon=12, seed=0, n_samples=50)
        np.testing.assert_array_equal(r1.point, r2.point)

    def test_different_seeds_give_different_results(self, sample_series: np.ndarray):
        r1 = run_forecast(sample_series, "H", horizon=12, seed=0, n_samples=50)
        r2 = run_forecast(sample_series, "H", horizon=12, seed=99, n_samples=50)
        # 多くの場合は異なるはず（稀に一致する可能性を考慮して緩めのチェック）
        assert not np.allclose(r1.point, r2.point) or not np.allclose(r1.samples, r2.samples)

    def test_lower_leq_point_leq_upper(self, sample_series: np.ndarray):
        result = run_forecast(sample_series, "H", horizon=24, seed=42, n_samples=100)
        assert np.all(result.lower <= result.point + 1e-6)
        assert np.all(result.point <= result.upper + 1e-6)

    def test_version_recorded(self, sample_series: np.ndarray):
        result = run_forecast(sample_series, "D", horizon=7, seed=1, n_samples=20)
        assert result.flaircast_version != ""

    def test_daily_freq(self, sample_series: np.ndarray):
        result = run_forecast(sample_series, "D", horizon=7, seed=42, n_samples=30)
        assert result.freq == "D"

    def test_warnings_for_low_variance(self):
        """変動が小さい（平坦な）系列は警告が出ること。"""
        flat_series = np.ones(100) * 5.0
        result = run_forecast(flat_series, "D", horizon=7, seed=42, n_samples=20)
        assert any("変動" in w or "周期" in w for w in result.warnings)
