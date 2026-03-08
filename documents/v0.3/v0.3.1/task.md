# v0.3.1 実装タスクチェックリスト（レポート機能）

## 0. スコープと固定ルール

- [ ] 対象スコープを確認する（本タスクは「2. レポート機能」のみ）
- [ ] 月次/週次判定は `event_type=report` 実行時に行う
- [ ] 当月に先月分月次が未配信なら、配信完了まで monthly を返す（weekly は抑止）
- [ ] 同一ユーザーの `pending report` は新規作成せず UPDATE（後勝ち）
- [ ] `配信済み` は `report_deliveries.posted_at IS NOT NULL` で判定する
- [ ] 集計0件時の `success_rate` は `0.0` を採用する

## 1. DB / Migration

- [x] `event_type_enum` に `report` を追加する
完了条件: `schedules.event_type` で `report` を保存可能

- [x] `action_result_enum` に `REPORT_READ` を追加する
完了条件: `action_logs.result` で `REPORT_READ` を保存可能

- [x] `schedules` 制約 `ck_schedules_event_commitment_id` を更新する
完了条件: `REMIND` は `commitment_id NOT NULL`、`PLAN/REPORT` は `commitment_id NULL`

- [x] `schedules.input_value` (text, nullable) を追加する
完了条件: `event_type=report` の UI入力JSONを保存可能

- [x] `report_deliveries` テーブルを作成する
完了条件: 以下カラムと制約が存在する
`id`, `schedule_id`, `user_id`, `report_type`, `period_start`, `period_end`, `posted_at`, `read_at`, `thread_ts`, `markdown_table`, `llm_comment`, `created_at`, `updated_at`, `UNIQUE(user_id, report_type, period_start, period_end)`, `UNIQUE(schedule_id)`

- [x] `configurations` に既存ユーザー分のデフォルト値を UPSERT する
完了条件: `REPORT_WEEKDAY='sat'`, `REPORT_TIME='07:00'` が不足ユーザーに補完される

- [x] `/config` の定義へ `REPORT_WEEKDAY` / `REPORT_TIME` を追加する
完了条件: `REPORT_WEEKDAY` は `sun..sat`、`REPORT_TIME` は `HH:MM` バリデーションで保存される

- [x] migration 検証を実施する
完了条件: `schedules` 件数一致、既存 `plan/remind` データ制約OK、`report_deliveries` ユニーク制約OK

## 2. Model / Repository 層

- [x] モデルに `ReportDelivery` を追加する
完了条件: ORM から CRUD 可能

- [x] `EventType.REPORT` / `ActionResult.REPORT_READ` をモデル定義に反映する
完了条件: API/worker から enum 参照で利用可能

- [x] `event_type=report` 向け `schedules.input_value` JSON 契約を実装する
完了条件: `ui_date`, `ui_time`, `updated_at` を保存・読取できる

## 3. Plan/UI フロー

- [x] plan開始時にレポート入力UI表示条件を判定する
完了条件: `REPORT_WEEKDAY` 一致または「先月月次未配信」の場合のみ表示

- [x] レポート入力UIの初期値を `/config` から反映する
完了条件: `REPORT_WEEKDAY`/`REPORT_TIME` がレポート入力欄のデフォルト値として表示される

- [x] レポート入力UIは既存 plan UI 仕様（`[今日, 明日]` + 時刻）を再利用する
完了条件: 新規UI仕様を増やさず既存の操作感を維持

- [x] レポート入力 submit 時に `pending report` を UPSERT する
完了条件: 同一ユーザーに `pending report` があれば UPDATE、なければ INSERT

- [x] `/plan` submit の既存一括キャンセル処理を調整する
完了条件: 既存の wash 処理で `pending/processing report` を誤って `canceled` にしない

- [x] report スケジュール保存時に `run_at` と `input_value` を同期する
完了条件: `run_at` は入力日時、`input_value` は `ui_date/ui_time/updated_at` を保持

- [x] レポート入力項目が非表示の `/plan` submit では report を変更しない
完了条件: 既存 `pending report` が維持される

## 4. Report Worker（生成・投稿）

- [x] worker の処理対象に `event_type=report` を追加する
完了条件: `state=pending AND run_at<=now` の report が実行される

- [x] report投稿成功時の状態遷移を実装する
完了条件: report は投稿成功後 `processing` を維持し、`読みました` 押下まで待機する

- [x] report実行時の種別判定（monthly/weekly）を実装する
完了条件: 「先月月次未配信なら monthly、配信済みなら weekly」を満たす

- [x] 集計期間算出を実装する
完了条件: monthly は先月1日〜末日、weekly は前回 weekly 翌日〜前日（初回は当月1日）

- [x] 成功/失敗/成功率集計を実装する（`schedules` + `action_logs` JOIN）
完了条件: `thread_ts IS NOT NULL` の `remind` のみを母数にし、`YES` が1件以上なら成功として集計される

- [x] Markdown 表整形を実装する
完了条件: 成功数・失敗数・成功率の表を固定フォーマットで生成

- [x] 既存 Codex 機構を再利用してコメント生成する
完了条件: `prompts/report_comment.md` を使い `report_deliveries.llm_comment` に保存

- [x] Slack 投稿（メンション付き）を実装する
完了条件: 実行チャンネルへ「Markdown表 + LLMコメント」を新規投稿

- [x] 投稿成功後のみ `report_deliveries` を INSERT する
完了条件: 投稿失敗時は INSERT しない

- [x] ignore監視対象に `event_type=report` を追加する
完了条件: report も既存の ignore 判定・Pavlok・AUTO_IGNORE に乗り、監視対象は `plan/remind/report` の最新processing1件共通ルールを維持する

## 5. Read/Ignore フロー

- [x] report投稿に `読みました` ボタンを追加する
完了条件: `action_id=report_read` で既存 remind と同等の ignore 機構で扱える

- [x] `読みました` は先勝ちで処理する
完了条件: 初回押下のみ有効、2回目以降はACKのみ返して無視

- [x] 初回押下時に `read_at` 更新 + `action_logs.result=REPORT_READ` 記録
完了条件: report_deliveries/action_logs の双方で監査可能

- [x] 初回押下時に `schedule.state=done` へ遷移する
完了条件: report schedule が完了状態になる

- [x] 種別別のスレッド返信文を実装する
完了条件: weekly=`来週も頑張りましょう`、monthly=`来月も頑張りましょう`

## 6. テスト（必須）

- [x] 月初以外でも先月月次未配信なら monthly になる
- [x] monthly active 中は weekly が生成・投稿されない
- [x] report再入力時に重複INSERTされず既存 `pending report` が更新される
- [x] UIで「明日」を選んでも、実行日の判定で正しい monthly/weekly が選ばれる
- [x] 既存 plan/remind/ignore の回帰がない
- [x] 集計対象0件でも表生成とコメント生成が失敗しない
- [x] 投稿失敗時は `report_deliveries` が作成されない
- [x] `読みました` の2回目押下が無視される

## 7. 最終確認（Definition of Done）

- [x] migration をクリーンDB・既存DBの両方で適用確認済み
- [x] unit/integration テストがすべて成功
- [ ] Slack 実機で report 投稿から `読みました` まで一連動作を確認済み
- [x] `documents/v0.3/v0.3.1/仕様書.md` と実装差分がない
