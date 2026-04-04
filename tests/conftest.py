"""テスト用共通フィクスチャ。"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture()
def tmp_dir():
    """一時ディレクトリを提供する。"""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture()
def sample_csv(tmp_dir: Path) -> Path:
    """正常系サンプル CSV を生成する（日次データ 100 点）。"""
    path = tmp_dir / "sample.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "value"])
        for i in range(100):
            ts = f"2024-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00"
            val = 10 + 5 * np.sin(2 * np.pi * i / 7) + np.random.default_rng(i).normal()
            writer.writerow([ts, round(val, 4)])
    return path


@pytest.fixture()
def sample_series() -> np.ndarray:
    """テスト用単変量時系列（正弦波 + ノイズ、200 点）。"""
    rng = np.random.default_rng(0)
    t = np.arange(200)
    return 10 + 5 * np.sin(2 * np.pi * t / 24) + rng.normal(scale=0.5, size=200)
