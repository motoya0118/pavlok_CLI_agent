## ユーザーシナリオ
### init
1. ユーザーがslackで`/base_commit`を実行するとコミットメントを新規作成(編集・追加)できるUIがレスポンスされる
2. ユーザーはslackでコミットメント(毎日何時に、何をやるのか)を記載して送信ボタンを押下する
3. ユーザー応答を受けbackend処理はコミットメントをDBに登録する
4. schedulesテーブルに今後`plan`eventが実行されない場合、現在時刻で`plan`eventが実行されるように登録する
5. `base_commit`処理が終わった旨をslackに投稿する

### plan
1. `panishment`機構(1分間隔の定期バッチ)がschedulesテーブルの`plan`event予定時刻になったら`plan`スクリプトを実行する
2. `plan`スクリプトはslackに`block kit`形式で24時間(翌日のplanまで)予定を送信する
3. ユーザーはslackで各タスクを`やる、やらない`、`何時にやる`を指定して送信する(plan_api)
4. `plan_api`はユーザー応答を受け取りDB(schedule Table)を更新する
   - 実行対象になった`plan`eventレコードのstateをdoneに更新
   - 受け取った`やる`とコミットメントされたタスクを指定時間にremindされるようにscheduleテーブルにINSERT(planタスクは`plan`で登録すること)
   - 受け取った`やらない`コミットメントのタスクは行動ログに記録する
5. 先ほど送信したslackのスレッドに返信する形で`plan`登録完了の旨を送信する
6. 最後に`echo {plan_prompt} | codex exec`を呼び出し`plan_update`skillを使用して登録されたplanに対して激励の一言,YESコメント,NOコメント(schedule.comment)を各レコードに登録する

### remind
1. `panishment`機構(1分間隔の定期バッチ)がschedulesテーブルの`plan`event予定時刻になったら`remind`スクリプトを実行する
2. `remind`スクリプトはslackに`block kit`形式で[激励の一言,タスクを今すぐやるか、やらないか確認メッセージ, (YES,NO)ボタン]を投稿する
3. ユーザーは[YES,NO]ボタンを押下する(remind_api)
4. ユーザーの返答によって処理が分岐する
  - YESの場合:
    - 行動ログテーブルにINSERT
    - 事前に登録されたYESコメントを先ほど投稿したslackスレッドに返信する
  - NOの場合:
    - 行動ログテーブルにINSERT
    - `pavlov`アルゴリズムに従って刺激種類,強度を設定し`pavlok`APIをコールする
    - 事前に登録されたNOコメントを先ほど投稿したslackスレッドに返信する

### stop
1. ユーザーはslackにて`/stop`と投稿することで`panishment`機構を停止できる
2. 履歴は行動ログに記載される

### restart
1. ユーザーはslackにて`/restart`と投稿することで`panishment`機構を再開できる
2. 履歴は行動ログに記載される

## システム大枠
### `command_watcher`
- `/base_commit`, `/stop`, `/restart`のslackコマンドを受け付けた際に指定の処理を実行する役割

### `panishment`機構
- 1分間隔でscheduleテーブルを監視する機構
- 実行するスクリプトはサブプロセスとして非同期で実行しメイン処理自体は監視にすぐ戻れるよう考慮する
- `pending`処理と`processing`監視を同一サイクルで実行する
- ignore監視は最新の`processing(plan)`レコードを対象に、`現在時間 - 実行時間`が設定値の倍数を超え、その回数のpanishment記録がなければ`pavloc`アルゴリズム(ignoreモード)に従った刺激種類/強度を計算してpavlok APIをコールする

### `pavloc`アルゴリズム
#### ignoreモード
  - ignore_time = (`現在時間 - 実行時間`) // {設定値(ignore_interval)} をベースの計算式とする
  - トリガーになったschedule.idのignore_timeレコードがpanishmentテーブルに存在しないことを確認する
  - アルゴリズムは以下の通り
    - ignore_time == 1
      - vibe: 100
    - ignore_time > 1
      - zap: (35 + (10 x (ignore_time - 2)))
      - 100を超える場合は100に丸めてAPIコールすること
    - 100を実行した場合、または`IGNORE_MAX_RETRY`超過時は対象のscheduleレコードのstateを`canceled`に更新し実行終了とする
      - このケースでは行動ログに記録すること
#### NOモード
- 行動ログの`remind`eventを最新から`YES`が出るまで遡り`NO`の連続回数(NO_count)を算出する
- トリガーになったschedule.idの罰実行レコードがpanishmentテーブルに存在しないことを確認する
- アルゴリズムは以下の通り
  - zap: (35 + (10 x (ignore_time - 1)))
  - 100を超える場合は100に丸めてAPIコールすること

### Agent
- `echo {prompt} | codex exec`をAgentと定義する

#### plan_prompt
Agentが存在しないとシステム的な無機質応答になってしまうのでAGENTS.mdで定義したキャラクター風にメッセージを味付けする役割
行動ログも参照しユーザーのモチベーションを上げる
