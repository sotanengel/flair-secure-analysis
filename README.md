# FLAIR セキュア分析コンテナ環境 (Phase 1)

FLAIR (`flaircast`) を使った**完全オフライン・ローカル分析**環境です。  
ファイルドロップ → 前処理 → 予測 → CSV/JSON 出力 → 監査ログ記録 を一貫して行います。

## セキュリティ設計

| 項目 | 設定 |
|---|---|
| ネットワーク | `--network none`（完全遮断） |
| 権限 | rootless, `cap_drop: ALL`, `no-new-privileges` |
| ファイルシステム | read-only rootfs, 書き込みは `output/` `logs/` `tmpfs` のみ |
| 入力 | CSV allowlist, 500MB/100万行上限, パストラバーサル対策 |
| 監査 | JSONL 監査ログ（生データ非記録） |

## クイックスタート

```bash
# 依存インストール
make install

# smoke-test（サンプルデータで動作確認）
make smoke

# 自分のデータで分析
cp your_data.csv work/input/
make run INPUT=work/input/your_data.csv DATETIME_COL=timestamp VALUE_COL=value

# コンテナビルド（Docker/Podman 必要）
make build
```

## ディレクトリ構成

```
flair-secure-analysis/
├── worker/             # 分析ワーカー（Python）
│   ├── main.py         # CLI エントリポイント
│   ├── validator.py    # 入力ファイル検証
│   ├── preprocessor.py # 前処理
│   ├── analyzer.py     # FLAIR 予測
│   ├── reporter.py     # CSV/JSON 出力
│   └── audit_logger.py # 監査ログ
├── tests/              # pytest テスト
├── scripts/            # build / run / smoke-test スクリプト
├── work/
│   ├── input/          # 入力ファイル置き場（要手動投入）
│   ├── output/         # 予測結果出力
│   └── logs/           # 監査ログ (audit.jsonl)
├── Containerfile       # コンテナイメージ定義
├── compose.yaml        # Docker Compose（network=none）
└── Makefile
```

## 入力形式

- 形式: CSV（Phase 1）
- 列構成: 日時列 + 値列（列名は `--datetime-col` `--value-col` で指定）
- サイズ: 最大 500 MB / 100 万行

```csv
timestamp,value
2024-01-01T00:00:00,123.4
2024-01-01T01:00:00,125.1
...
```

## CLI オプション

```
python -m worker.main \
  --input <csv_path>        # 必須
  --datetime-col timestamp  # 日時列名（デフォルト: timestamp）
  --value-col value         # 値列名（デフォルト: value）
  --freq H                  # 周波数 H/D/W/ME/QE/YE（省略時: 自動推定）
  --horizon 24              # 予測ホライズン（デフォルト: 24）
  --seed 42                 # 乱数シード（デフォルト: 42）
  --n-samples 200           # サンプル数（デフォルト: 200）
  --missing ffill           # 欠損値ポリシー ffill|stop
  --output-dir work/output
  --log-dir work/logs
```

## 出力

```
work/output/{job_id}/
├── input/            # 入力ファイルのコピー（隔離）
├── forecast.csv      # 予測結果（timestamp, point, lower_10, upper_90）
└── report.json       # 入力要約・設定・バージョン・SHA-256・注意喚起
```

## テスト

```bash
make test   # pytest
make lint   # ruff
```

## FLAIR の適用注意事項

- **単変量時系列専用**（外生変数なし）
- **周期性のある系列**で強みが出る
- 非周期・断続需要・データ不足の場合は警告を出力
- 詳細: https://github.com/TakatoHonda/FLAIR

## ライセンス

本プロジェクトのコード: MIT  
FLAIR (flaircast): MIT
