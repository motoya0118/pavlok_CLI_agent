# Remind Ask
- `behavior_log`テーブルから今日1日のログを取得する
- pavlok端末に`vibe`を送る
- `scripts/slack.py --mode ask`で質問を送信し、返信有無を確認する
  - 返信があった場合
    - 返信内容を解析し、必要なら`pavlok`刺激を実行し`behavior_logs`に記録する(強度は`behavior_log`に応じて判断してください)
  - 返信がない場合
    - `add_slack_ignore_events`を実行して無視を記録する
    - 15分後に再度`remind_ask`を同様のinput_valueで実施するように`scripts/add_schedules.py`へ登録する
- slackに`対象者のコーチとして適切な内容`を返信する
- pavlok端末に`vibe`を送る

## Context
- schedule_id: {{schedule_id}}
- state: {{state}}
- input_value: {{input_value}}
- last_result: {{last_result}}
- last_error: {{last_error}}
