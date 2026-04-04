"""FLAIR セキュア分析ワーカー エントリポイント。

使い方:
    python -m worker.main --input <csv_file> --datetime-col <col> --value-col <col> [options]

オプション:
    --input         入力 CSV ファイルパス（必須）
    --datetime-col  日時列名（デフォルト: timestamp）
    --value-col     値列名（デフォルト: value）
    --freq          周波数 H/D/W/ME/QE/YE（省略時: 自動推定）
    --horizon       予測ホライズン（デフォルト: 24）
    --seed          乱数シード（デフォルト: 42）
    --n-samples     サンプル数（デフォルト: 200）
    --output-dir    出力先ディレクトリ（デフォルト: /work/output）
    --log-dir       ログディレクトリ（デフォルト: /work/logs）
    --missing       欠損値ポリシー ffill|stop（デフォルト: ffill）
    --image-digest  コンテナイメージ digest（監査用、省略可）
"""

from __future__ import annotations

import argparse
import shutil
import sys
import uuid
from pathlib import Path

from worker.analyzer import AnalyzerError, run_forecast
from worker.audit_logger import AuditLogger
from worker.preprocessor import PreprocessError, preprocess
from worker.reporter import save_results
from worker.validator import ValidationError, sanitize_filename, validate_file


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FLAIR セキュア分析ワーカー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", required=True, help="入力 CSV ファイルパス")
    parser.add_argument("--datetime-col", default="timestamp", help="日時列名")
    parser.add_argument("--value-col", default="value", help="値列名")
    parser.add_argument("--freq", default=None, help="周波数 (H/D/W/ME など)")
    parser.add_argument("--horizon", type=int, default=24, help="予測ホライズン")
    parser.add_argument("--seed", type=int, default=42, help="乱数シード")
    parser.add_argument("--n-samples", type=int, default=200, help="サンプル数")
    parser.add_argument("--output-dir", default="/work/output", help="出力先ディレクトリ")
    parser.add_argument("--log-dir", default="/work/logs", help="ログディレクトリ")
    parser.add_argument(
        "--missing",
        choices=["ffill", "stop"],
        default="ffill",
        help="欠損値ポリシー",
    )
    parser.add_argument("--image-digest", default=None, help="コンテナ image digest（監査用）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """メインエントリポイント。終了コードを返す（0=成功、1=失敗）。"""
    args = _parse_args(argv)

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir)
    log_dir = Path(args.log_dir)

    # ジョブ ID 生成
    job_id = str(uuid.uuid4())
    print(f"[worker] job_id={job_id}")

    # 監査ロガー初期化
    logger = AuditLogger(log_dir, job_id)

    config = {
        "datetime_col": args.datetime_col,
        "value_col": args.value_col,
        "freq": args.freq,
        "horizon": args.horizon,
        "seed": args.seed,
        "n_samples": args.n_samples,
        "missing_policy": args.missing,
    }

    # --- Step 1: 入力ファイル検証 ---
    print(f"[worker] 入力ファイル検証中: {input_path}")
    try:
        file_info = validate_file(
            input_path,
            datetime_col=args.datetime_col,
            value_col=args.value_col,
        )
    except ValidationError as e:
        logger.log_quarantine(input_filename=input_path.name, reason=str(e))
        print(f"[worker] ERROR: 入力検証失敗 - {e}", file=sys.stderr)
        return 1

    sha256 = file_info["sha256"]
    print(f"[worker] SHA-256: {sha256}")
    print(f"[worker] 行数: {file_info['row_count']:,}, 列: {file_info['columns']}")

    # --- Step 2: 入力ファイルをジョブディレクトリへ隔離コピー ---
    safe_name = sanitize_filename(input_path.name)
    job_input_dir = output_dir / job_id / "input"
    job_input_dir.mkdir(parents=True, exist_ok=True)
    job_input_path = job_input_dir / safe_name
    shutil.copy2(input_path, job_input_path)

    job_output_dir = output_dir / job_id

    # --- ジョブ開始ログ ---
    logger.log_start(
        input_filename=input_path.name,
        input_sha256=sha256,
        config=config,
        image_digest=args.image_digest,
    )

    # --- Step 3: 前処理 ---
    print("[worker] 前処理中...")
    try:
        pre_result = preprocess(
            job_input_path,
            datetime_col=args.datetime_col,
            value_col=args.value_col,
            freq=args.freq,
            missing_policy=args.missing,  # type: ignore[arg-type]
        )
    except PreprocessError as e:
        logger.log_failure(error_type="PreprocessError", error_summary=str(e), exc=e)
        print(f"[worker] ERROR: 前処理失敗 - {e}", file=sys.stderr)
        return 1

    for w in pre_result.warnings:
        print(f"[worker] WARN: {w}")

    # --- Step 4: FLAIR 予測 ---
    print(f"[worker] FLAIR 予測実行中 (horizon={args.horizon}, freq={pre_result.freq})...")
    try:
        fc_result = run_forecast(
            pre_result.y,
            pre_result.freq,
            horizon=args.horizon,
            seed=args.seed,
            n_samples=args.n_samples,
        )
    except AnalyzerError as e:
        logger.log_failure(error_type="AnalyzerError", error_summary=str(e), exc=e)
        print(f"[worker] ERROR: 予測失敗 - {e}", file=sys.stderr)
        return 1

    for w in fc_result.warnings:
        print(f"[worker] WARN: {w}")

    # --- Step 5: 結果出力 ---
    print("[worker] 結果出力中...")
    try:
        saved_files = save_results(
            job_output_dir,
            job_id=job_id,
            input_filename=input_path.name,
            input_sha256=sha256,
            input_stats=file_info,
            preprocess_result=pre_result,
            forecast_result=fc_result,
            config=config,
            image_digest=args.image_digest,
        )
    except Exception as e:
        logger.log_failure(error_type="ReporterError", error_summary=str(e), exc=e)
        print(f"[worker] ERROR: 出力失敗 - {e}", file=sys.stderr)
        return 1

    all_warnings = pre_result.warnings + fc_result.warnings
    logger.log_success(output_files=[str(p) for p in saved_files], warnings=all_warnings)

    print(f"[worker] 完了! 出力先: {job_output_dir}")
    for f in saved_files:
        print(f"  - {f}")

    if all_warnings:
        print("\n[worker] 注意喚起:")
        for w in all_warnings:
            print(f"  ⚠  {w}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
