"""FLAIR 予測実行モジュール。

flaircast を使って単変量時系列の将来予測を行う。
- 乱数シード固定
- 点推定（平均）と区間推定（10/90 パーセンタイル）
- 適合性チェックと警告生成
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass, field

import numpy as np

DEFAULT_HORIZON = 24
DEFAULT_SEED = 42
DEFAULT_N_SAMPLES = 200
PERIODICITY_CV_THRESHOLD = 0.3  # 周期性なし疑い閾値（CV < この値 → 変動少ない）


@dataclass
class ForecastResult:
    """予測結果。"""

    point: np.ndarray  # 点推定 (horizon,)
    lower: np.ndarray  # 下限 10パーセンタイル (horizon,)
    upper: np.ndarray  # 上限 90パーセンタイル (horizon,)
    samples: np.ndarray  # 全サンプル (n_samples, horizon)
    horizon: int
    freq: str
    seed: int
    n_samples: int
    flaircast_version: str
    warnings: list[str] = field(default_factory=list)


class AnalyzerError(RuntimeError):
    """分析実行エラー。"""


def _check_periodicity(y: np.ndarray, freq: str) -> list[str]:
    """系列が FLAIR に適しているか簡易チェックする。"""
    warnings = []
    if len(y) == 0:
        return warnings

    cv = float(np.std(y) / np.mean(np.abs(y))) if np.mean(np.abs(y)) > 0 else 0.0
    if cv < PERIODICITY_CV_THRESHOLD:
        warnings.append(
            f"値の変動が小さい系列です (CV={cv:.3f})。"
            "FLAIR は周期性のある系列で強みが出ます。非周期・平坦な系列には不向きな場合があります。"
        )

    if freq in ("ME", "QE", "YE") and len(y) < 24:
        warnings.append(
            f"周波数 '{freq}' に対してデータ点数が少なすぎます ({len(y)} 点)。"
            "予測精度が低下する可能性があります。"
        )

    return warnings


def run_forecast(
    y: np.ndarray,
    freq: str,
    *,
    horizon: int = DEFAULT_HORIZON,
    seed: int = DEFAULT_SEED,
    n_samples: int = DEFAULT_N_SAMPLES,
) -> ForecastResult:
    """FLAIR で予測を実行する。

    Args:
        y: 単変量時系列（float64 numpy array）
        freq: pandas 周波数エイリアス ('H', 'D', 'W', 'ME', ...)
        horizon: 予測ホライズン（ステップ数）
        seed: 乱数シード
        n_samples: サンプル数

    Returns:
        ForecastResult

    Raises:
        AnalyzerError: 予測失敗時。
    """
    try:
        import flaircast
    except ImportError as e:
        raise AnalyzerError("flaircast パッケージがインストールされていません") from e

    try:
        version = importlib.metadata.version("flaircast")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    # 適合性事前チェック
    warnings = _check_periodicity(y, freq)

    try:
        samples = flaircast.forecast(
            y,
            horizon=horizon,
            freq=freq,
            n_samples=n_samples,
            seed=seed,
        )
    except Exception as e:
        raise AnalyzerError(f"FLAIR 予測に失敗しました: {e}") from e

    samples = np.asarray(samples, dtype=np.float64)

    if samples.ndim != 2 or samples.shape[1] != horizon:
        raise AnalyzerError(
            f"予期しない予測出力形状: {samples.shape}。期待: (n_samples, {horizon})"
        )

    point = samples.mean(axis=0)
    lower = np.percentile(samples, 10, axis=0)
    upper = np.percentile(samples, 90, axis=0)

    return ForecastResult(
        point=point,
        lower=lower,
        upper=upper,
        samples=samples,
        horizon=horizon,
        freq=freq,
        seed=seed,
        n_samples=n_samples,
        flaircast_version=version,
        warnings=warnings,
    )
