"""結果出力モジュール。

予測結果を CSV / JSON / PNG グラフとして output/{job_id}/ 配下へ保存する。
入力要約・設定値・FLAIR バージョン・入力ファイル SHA-256・注意喚起を含める。
"""

from __future__ import annotations

import csv
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from worker.analyzer import ForecastResult
from worker.preprocessor import PreprocessResult


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


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
        for ts, pt, lo, hi in zip(  # noqa: B905
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

    # --- history.json（前処理済み実データ。ブラウザ側インタラクティブグラフ用）---
    history_json = output_dir / "history.json"
    history_data = [
        {"timestamp": ts.isoformat(), "value": round(float(v), 6)}
        for ts, v in zip(preprocess_result.index, preprocess_result.y)  # noqa: B905
    ]
    with history_json.open("w", encoding="utf-8") as f:
        json.dump({"rows": history_data}, f, ensure_ascii=False)
    saved.append(str(history_json))

    # --- forecast_chart.png ---
    chart_path = _save_chart(
        output_dir=output_dir,
        historical_index=preprocess_result.index,
        historical_y=preprocess_result.y,
        future_index=future_index,
        point=forecast_result.point,
        lower=forecast_result.lower,
        upper=forecast_result.upper,
        title=f"FLAIR 予測結果 — {input_filename}",
    )
    if chart_path:
        saved.append(str(chart_path))

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
        msg = f"[注意] データ点数が非常に少なすぎます ({n} 点)。"
        warnings.append(msg + "予測精度が著しく低下する可能性があります。")

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


def _save_chart(
    *,
    output_dir: Path,
    historical_index: pd.DatetimeIndex,
    historical_y: np.ndarray,
    future_index: pd.DatetimeIndex,
    point: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    title: str,
) -> Path | None:
    """予測結果の折れ線グラフを PNG で保存する。失敗時は None を返す。"""
    try:
        import matplotlib
        matplotlib.use("Agg")  # GUI なし（サーバー環境）
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 5))

        # 直近 120 点だけ表示（グラフが見やすいように）
        display_n = min(120, len(historical_y))
        hist_idx = historical_index[-display_n:]
        hist_y = historical_y[-display_n:]

        ax.plot(hist_idx, hist_y, color="#4A90D9", linewidth=1.2, label="Historical")
        ax.plot(future_index, point, color="#E05A2B", linewidth=1.5, label="Forecast (median)")
        ax.fill_between(
            future_index, lower, upper,
            color="#E05A2B", alpha=0.2, label="Forecast interval (10-90%)"
        )

        # 実績と予測の境界線
        ax.axvline(x=historical_index[-1], color="gray", linestyle="--", linewidth=0.8)

        chart_title = f"FLAIR Forecast — {title}"
        ax.set_title(chart_title, fontsize=11, pad=10)
        ax.set_xlabel("Datetime")
        ax.set_ylabel("Value")
        ax.legend(loc="upper left", fontsize=9)
        ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(mdates.AutoDateLocator()))
        fig.autofmt_xdate()
        plt.tight_layout()

        chart_path = output_dir / "forecast_chart.png"
        fig.savefig(str(chart_path), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return chart_path
    except Exception:
        return None
