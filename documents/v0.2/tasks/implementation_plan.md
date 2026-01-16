# v0.2 実装方針・タスク
更新日: 2026-01-12

## 実装方針
- 設計書 `documents/v0.2/design/v0.2_design.md` を単一の仕様源として実装を進める
- スクリプト単位でテストを作成し、各スクリプトのI/OとDB更新を担保する
- 外部APIはモック化し、LIMIT系の共通仕様は `scripts/pavlok.py` に集約する
- 日付はJSTで解釈・保存・判定を統一し、バッチ起動もJST基準で行う
- 各項目はテスト作成 → 実装 → リファクタの順で進め、統合もテスト先行で組む

## 実装タスク（TDD順）
- [ ] 環境/設定（最初に実施）
  - [ ] `.env`に新規設定値（LIMIT系/タイムアウト等）を先行追加
  - [ ] `env-sample`更新と`README.md`運用手順の整備
- [ ] DBレイヤ更新
  - [ ] テスト: テスト用DB初期化/モデル疎通（最低限のCRUD）
  - [ ] `schedules`を`prompt_name/state`へ移行（モデル/DDL）
  - [ ] `daily_punishments`/`slack_ignore_events`/`pavlok_counts`テーブル追加
  - [ ] `behavior_logs`の`related_date/created_at`追加
  - [ ] マイグレーション作成と適用
- [ ] `scripts/pavlok.py`
  - [ ] テスト: `tests/scripts/test_pavlok.py`（LIMIT境界値）
  - [ ] 実装: `LIMIT_DAY_PAVLOK_COUNTS`と`LIMIT_PAVLOK_ZAP_VALUE`制御を追加
- [ ] `scripts/slack.py`
  - [ ] テスト: `tests/scripts/test_slack.py`（timeout時JSON）
  - [ ] 実装: 標準出力JSON化（timeoutは`is_answer=false`）
- [ ] `scripts/add_slack_ignore_events.py`
  - [ ] テスト: `tests/scripts/test_add_slack_ignore_events.py`（残数合計）
  - [ ] 実装: スクリプト追加（残数合計のJSON出力）
- [ ] `scripts/repentance.py`
  - [ ] テスト: `tests/scripts/test_repentance.py`（pavlok経由とstate更新）
  - [ ] 実装: スクリプト追加（必ず`scripts/pavlok.py`経由で刺激）
- [ ] `scripts/add_schedules.py` / `scripts/behavior_log.py`
  - [ ] テスト: スクリプトI/OとDB更新
  - [ ] 実装: 入出力をv0.2仕様に更新
- [ ] `schedule_executor.py` / `main.py`
  - [ ] テスト: `tests/test_schedule_executor.py`（pending/failedと初回morning条件）
  - [ ] テスト: `tests/test_main.py`（executor起動のみ）
  - [ ] 実装: `schedule_executor.py`（排他/リトライ）
  - [ ] 実装: `main.py`（エントリポイント）
- [ ] プロンプト整備
  - [ ] `prompts/morning.md` / `prompts/remind_ask.md` / `prompts/reflection.md`を作成
  - [ ] 共通変数`input_value/schedule_id/state/last_result/last_error`を反映
