"""結果出力モジュール。

予測結果を CSV / JSON として output/{job_id}/ 配下へ保存する。
入力要約・設定値・FLAIR バージョン・入力ファイル SHA-256・注意喚起を含める。
"""

from __future__ import annotations

import csv
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from worker.analyzer import ForecastResult
from worker.preprocessor import PreprocessResult


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _array_to_list(arr: np.ndarray) -> list[float]:
    return [round(float(v), 6) for v in arr]


def save_results(
    output_dir: Path,
    *,
    job_id: str,
    input_filename: str,
    input_sha256: str,
    input_stats: dict[str, Any],
    preprocess_result: PreprocessResult,
    forecast_result: ForecastResult,
    config: dict[str, Any],
    image_digest: str | None = None,
) -> list[str]:
    """予測結果を output_dir へ保存する。

    Returns:
        保存されたファイルパスのリスト（文字列）
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    # --- 予測未来インデックスの生成 ---
    last_ts = preprocess_result.index[-1]
    future_index = pd.date_range(
        start=last_ts,
        periods=forecast_result.horizon + 1,
        freq=preprocess_result.freq,
    )[1:]  # last_ts を除く

    # --- forecast.csv ---
    forecast_csv = output_dir / "forecast.csv"
    with forecast_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "point", "lower_10", "upper_90"])
        for ts, pt, lo, hi in zip(
            future_index,
            forecast_result.point,
            forecast_result.lower,
            forecast_result.upper,
        ):
            writer.writerow([
                ts.isoformat(),
                round(float(pt), 6),
                round(float(lo), 6),
                round(float(hi), 6),
            ])
    saved.append(str(forecast_csv))

    # --- report.json ---
    all_warnings = (
        preprocess_result.warnings
        + forecast_result.warnings
        + _generate_quality_warnings(preprocess_result, forecast_result)
    )

    library_versions = {
        "flaircast": forecast_result.flaircast_version,
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "python": sys.version,
        "platform": platform.platform(),
    }

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "job_id": job_id,
        "generated_at": _utcnow_iso(),
        "input": {
            "filename": input_filename,
            "sha256": input_sha256,
            "stats": input_stats,
        },
        "config": config,
        "preprocessing": {
            "freq": preprocess_result.freq,
            "series_length": len(preprocess_result.y),
            "stats": preprocess_result.stats,
        },
        "forecast": {
            "horizon": forecast_result.horizon,
            "freq": forecast_result.freq,
            "seed": forecast_result.seed,
            "n_samples": forecast_result.n_samples,
            "point": _array_to_list(forecast_result.point),
            "lower_10": _array_to_list(forecast_result.lower),
            "upper_90": _array_to_list(forecast_result.upper),
            "timestamps": [ts.isoformat() for ts in future_index],
        },
        "reproducibility": {
            "seed": forecast_result.seed,
            "flaircast_version": forecast_result.flaircast_version,
            "input_sha256": input_sha256,
            "image_digest": image_digest,
        },
        "library_versions": library_versions,
        "warnings": all_warnings,
        "image_digest": image_digest,
    }

    report_json = output_dir / "report.json"
    with report_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    saved.append(str(report_json))

    return saved


def _generate_quality_warnings(
    pre: PreprocessResult,
    fc: ForecastResult,
) -> list[str]:
    """FLAIR 適用適合性の追加警告を生成する。"""
    warnings = []
    n = len(pre.y)

    # データ長不足
    if n < 30:
        warnings.append(
            f"[注意] データ点数が非常に少なすぎます ({n} 点)。予測精度が著しく低下する可能性があります。"
        )

    # 周波数不一致の可能性
    if fc.freq in ("D", "H") and n < 14:
        warnings.append(
            f"[注意] 周波数 '{fc.freq}' に対して十分なデータ点数がありません。"
            "少なくとも2周期分のデータが必要です。"
        )

    # ゼロ過多（断続需要）
    if pre.stats.get("zero_rate", 0) > 0.5:
        warnings.append(
            "[注意] ゼロ値の割合が50%以上です。断続需要系列への FLAIR 適用は推奨されません。"
        )

    return warnings
