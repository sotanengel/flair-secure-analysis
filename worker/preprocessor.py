"""前処理モジュール。

CSVファイルから単変量時系列データを抽出し、FLAIR が利用できる numpy array に変換する。

処理内容:
- 日時列・値列のパース
- 欠損値・重複タイムスタンプの検知と処理
- 周波数の明示指定または推定補助
- 適合性の事前チェック（データ長・ゼロ率）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

# 推定できる周波数エイリアス（pandas 2.2+ 対応）
SUPPORTED_FREQS = {"min", "h", "D", "W", "ME", "QE", "YE"}

# FLAIR への freq マッピング（pandas エイリアス → flaircast エイリアス）
# flaircast は旧来の大文字エイリアスも小文字も受け付けるが念のためマッピング
_FLAIR_FREQ_MAP: dict[str, str] = {
    "min": "T",
    "h": "H",
    "ME": "M",
    "QE": "Q",
    "YE": "Y",
}

# Phase 1 では欠損補完ポリシーとして forward-fill を採用
MissingPolicy = Literal["ffill", "stop"]

MIN_SERIES_LENGTH = 30  # 推奨最小データ点数
ZERO_RATE_WARN_THRESHOLD = 0.3  # ゼロ比率がこれを超えると警告


@dataclass
class PreprocessResult:
    """前処理結果。"""

    y: np.ndarray  # 単変量時系列（float64）
    freq: str  # pandas 周波数エイリアス
    index: pd.DatetimeIndex  # タイムスタンプインデックス
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


class PreprocessError(ValueError):
    """前処理エラー。"""


def _infer_freq(index: pd.DatetimeIndex) -> str:
    """タイムスタンプから周波数を推定する。推定不可なら 'D' を返す。pandas 2.2+ 対応。"""
    if len(index) < 3:
        return "D"
    inferred = pd.infer_freq(index)
    if inferred is None:
        return "D"
    low = inferred.lower()
    # 時系列 → 小文字 h
    if low.startswith("h"):
        return "h"
    # 分 → min
    if low.startswith("t") or low.startswith("min"):
        return "min"
    # 日・週
    if inferred.startswith("D"):
        return "D"
    if inferred.startswith("W"):
        return "W"
    # 月・四半期・年（pandas 2.2+ では ME/QE/YE）
    if inferred.startswith("ME") or inferred.startswith("M"):
        return "ME"
    if inferred.startswith("QE") or inferred.startswith("Q"):
        return "QE"
    if inferred.startswith("YE") or inferred.startswith("A"):
        return "YE"
    return "D"


def preprocess(
    path: Path,
    *,
    datetime_col: str,
    value_col: str,
    freq: str | None = None,
    missing_policy: MissingPolicy = "ffill",
) -> PreprocessResult:
    """CSV ファイルを読み込み、前処理済み単変量系列を返す。

    Args:
        path: CSV ファイルパス
        datetime_col: 日時列名
        value_col: 値列名
        freq: 周波数 ('H', 'D', 'W', 'ME' など)。None で自動推定。
        missing_policy: 欠損値ポリシー ('ffill' か 'stop')

    Returns:
        PreprocessResult

    Raises:
        PreprocessError: 前処理が続行不可能な場合。
    """
    warnings: list[str] = []

    # --- 読み込み ---
    try:
        df = pd.read_csv(path, encoding="utf-8")
    except Exception as e:
        raise PreprocessError(f"CSV の読み込みに失敗しました: {e}") from e

    if datetime_col not in df.columns:
        raise PreprocessError(f"日時列 {datetime_col!r} が見つかりません")
    if value_col not in df.columns:
        raise PreprocessError(f"値列 {value_col!r} が見つかりません")

    # --- 日時パース ---
    try:
        df[datetime_col] = pd.to_datetime(df[datetime_col])
    except Exception as e:
        raise PreprocessError(f"日時列 {datetime_col!r} のパースに失敗しました: {e}") from e

    df = df[[datetime_col, value_col]].copy()
    df = df.rename(columns={datetime_col: "_dt", value_col: "_val"})
    df = df.sort_values("_dt").reset_index(drop=True)

    # --- 重複タイムスタンプ除去 ---
    dup_count = df.duplicated(subset=["_dt"]).sum()
    if dup_count > 0:
        warnings.append(f"重複タイムスタンプを {dup_count} 件検出しました。最初の値を使用します。")
        df = df.drop_duplicates(subset=["_dt"], keep="first").reset_index(drop=True)

    index = pd.DatetimeIndex(df["_dt"])

    # --- 値列の数値変換 ---
    values = pd.to_numeric(df["_val"], errors="coerce")
    nan_count = values.isna().sum()

    if nan_count == len(values):
        raise PreprocessError(f"値列 {value_col!r} が全て数値変換不可でした")

    if nan_count > 0:
        if missing_policy == "stop":
            raise PreprocessError(
                f"欠損値が {nan_count} 件あります。missing_policy='stop' のため中断します。"
            )
        warnings.append(f"欠損値 {nan_count} 件を前方補完 (ffill) します。")
        values = values.ffill().bfill()

    y = values.to_numpy(dtype=np.float64)

    # --- 周波数 ---
    if freq is None:
        freq = _infer_freq(index)
        warnings.append(f"周波数を自動推定しました: '{freq}'")

    # 旧来の大文字エイリアスを pandas 2.2+ 対応に正規化
    _uppercase_to_new = {"H": "h", "T": "min", "M": "ME", "Q": "QE", "A": "YE", "Y": "YE"}
    freq = _uppercase_to_new.get(freq, freq)

    # --- 適合性チェック ---
    n = len(y)
    if n < MIN_SERIES_LENGTH:
        warnings.append(
            f"データ点数が少なすぎます ({n} 点)。FLAIR は最低 {MIN_SERIES_LENGTH} 点を推奨します。"
        )

    zero_rate = float(np.sum(y == 0) / n)
    if zero_rate > ZERO_RATE_WARN_THRESHOLD:
        warnings.append(
            f"ゼロ値の割合が高い ({zero_rate:.1%})。"
            "断続需要系列には FLAIR は不向きな場合があります。"
        )

    stats = {
        "n": n,
        "mean": float(np.mean(y)),
        "std": float(np.std(y)),
        "min": float(np.min(y)),
        "max": float(np.max(y)),
        "zero_rate": zero_rate,
        "missing_filled": int(nan_count),
        "duplicates_removed": int(dup_count),
    }

    return PreprocessResult(y=y, freq=freq, index=index, warnings=warnings, stats=stats)
