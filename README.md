# FLAIR セキュア分析コンテナ環境

FLAIR (`flaircast`) を使った**完全オフライン・ローカル分析**環境です。  
ファイルドロップ → 前処理 → 予測 → CSV/JSON/グラフ出力 → 監査ログ記録 を一貫して行います。  
**ブラウザ UI**（Phase 2）と **CLI**（Phase 1）の両方で利用できます。

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

---

## Web UI の使い方（Phase 2）

### 起動

```bash
make install   # 初回のみ
make ui        # http://127.0.0.1:5000 で起動
```

ブラウザで `http://127.0.0.1:5000` を開いてください（ローカルのみアクセス可）。

### 画面構成

| タブ | 説明 |
|---|---|
| 📂 **ファイル投入** | CSV ファイルをドラッグ＆ドロップまたはクリック選択でアップロード |
| ⚙️ **設定** | 列名・予測期間・周波数・乱数シードなどを入力し分析を実行 |
| ⏳ **実行状況** | 分析の進行状況をリアルタイムにポーリングで確認 |
| 📊 **結果** | 予測グラフ・数値テーブル・レポートをブラウザ内で閲覧、CSV ダウンロード |
| 🗂 **ジョブ履歴** | 過去の実行ジョブ一覧と再表示 |

### 手順

1. **📂 ファイル投入** — CSV を選択してアップロード
2. **⚙️ 設定** タブへ移動し、以下を入力して **分析開始**：
   - `日時列名`（例: `timestamp`）
   - `値列名`（例: `value`）
   - `周波数`（`h` = 毎時、`D` = 日次、`W` = 週次 など。空欄で自動推定）
   - `予測ホライズン`（何ステップ先まで予測するか）
   - `乱数シード`（再現性を持たせる場合に指定）
3. **⏳ 実行状況** タブで完了を待つ（自動ポーリング）
4. **📊 結果** タブで予測グラフ・テーブルを確認し、必要に応じて CSV ダウンロード

> **注意**: UI もオフライン動作です。外部リソース（CDN 等）は一切読み込みません。

---

## ディレクトリ構成

```
flair-secure-analysis/
├── worker/             # 分析ワーカー（Python）
│   ├── main.py         # CLI エントリポイント
│   ├── validator.py    # 入力ファイル検証
│   ├── preprocessor.py # 前処理
│   ├── analyzer.py     # FLAIR 予測
│   ├── reporter.py     # CSV/JSON/グラフ出力
│   └── audit_logger.py # 監査ログ
├── ui/                 # Web UI（Flask）
│   ├── app.py          # Flask サーバー
│   ├── templates/      # HTML テンプレート
│   └── static/         # CSS / JS（外部 CDN なし）
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
├── input/              # 入力ファイルのコピー（隔離）
├── forecast.csv        # 予測結果（timestamp, point, lower_10, upper_90）
├── report.json         # 入力要約・設定・バージョン・SHA-256・注意喚起
└── forecast_chart.png  # 予測グラフ（実績 + 信頼区間）
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
