# Morning
## Steps
- `behavior_log`テーブルから3日間のログを取得する
- pavlok端末に`vibe`を送る
- `behavior_log`をもとに今日のリマインド/振り返り/翌朝計画の候補をSlackで提示する(Template項の`提案`をベースにメッセージを構成すること)
  - 返信が返ってきた場合: 
    - 返信内容をもとにスケジュールを調整し、`scripts/add_schedules.py`で登録する
    - どういう計画で登録したかslackに返信する(Template項の`確定`をベースにメッセージを構成すること)
  - 返信が返ってこなかった場合:
    - `scripts/add_slack_ignore_events.py`で登録する
    - 15分後に再度`morning`を実施するように`scripts/add_schedules.py`へ登録する
- 必要なら`behavior_logs`にログを残すため`--mode write`で`behavior_log`を呼ぶ
- pavlok端末に`vibe`を送る

## Context
- schedule_id: {{schedule_id}}
- state: {{state}}
- input_value: {{input_value}}
- last_result: {{last_result}}
- last_error: {{last_error}}

## Template
### 提案
```
<!channel> 👋

📅 *今日の予定提案だよ！*
*xx分以内に返信してね⚡️*

🔔 *remind_ask予定(リマインド)*
・⏰ <hh:mm> {悪習慣を働きそうな時間に悪習慣チェック}


🔁 *reflection予定(振り返り)*
・📝 <hh:mm> {寝る前に振り返り}

🛠️ *morning予定(計画作成)*
・🧭 <hh:mm> {朝起きたら計画作成}

---

💡 *今日のアドバイス*
✨ {`behavior_log`をもとに今日の過ごし方をアドバイスしてください}
```

### 確定
```
<!channel> 👋

📅 *今日の予定確定版だよ！*

🔔 *remind_ask予定(リマインド)*
・⏰ <hh:mm> {悪習慣を働きそうな時間に悪習慣チェック}


🔁 *reflection予定(振り返り)*
・📝 <hh:mm> {寝る前に振り返り}

🛠️ *morning予定(計画作成)*
・🧭 <hh:mm> {朝起きたら計画作成}

{元気になる励ましの言葉で締めて}
```