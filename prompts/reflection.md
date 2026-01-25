# Reflection
## Steps
- pavlok端末に`vibe`を送る
- slackで振り返り質問を送信する
  - 返信あり
    - 返信内容を要約し、`behavior_log`に記録する
    - slackに`repentance`を実行する旨を通知
    - `repentance`を実行し、未実行の懲罰を消化する
    - `behavior_log`テーブルから今日1日のログを取得する
  - 返信なし
    - `add_slack_ignore_events`で無視を記録する
    - 15分後に再度`reflection`を同様のinput_valueで実施するように`scripts/add_schedules.py`へ登録する
- slackに`behavior_log`,`repentance`戻り値(刑の実行回数)をもとに日次のレポートを作成し監視対象者がより良くなるように促してください
- pavlok端末に`vibe`を送る

## Context
- schedule_id: {{schedule_id}}
- state: {{state}}
- input_value: {{input_value}}
- last_result: {{last_result}}
- last_error: {{last_error}}
