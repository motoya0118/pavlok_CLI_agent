# 破壊的変更（DB DROP）タイミング

## 1. 概要
v0.3への移行におけるDB破壊的変更のタイミングと実行条件を定義する。

## 2. 実行条件

### 2.1 事前条件（すべて満たすこと）

| 条件 | 確認方法 |
|------|---------|
| v0.3コード完了 | 全テストPASS |
| 手動テスト完了 | チェックリスト全項目OK |
| バックアップ取得 | `cp app.db app.db.backup` |
| メンテナンスウィンドウ確保 | ユーザーへの通知完了 |
| .env設定完了 | 新規環境変数の設定 |

### 2.2 チェックリスト

```bash
# 事前チェック
[ ] pytest scripts/tests/ → PASS
[ ] v0.3_design.mdのTODO解消
[ ] app.db.backupの存在確認
[ ] INTERNAL_SECRET設定確認
[ ] AUTHORIZED_USERS設定確認
```

## 3. バックアップ方針

### 3.1 バックアップ取得

```bash
# 実行コマンド
cd /path/to/app
cp app.db app.db.backup.$(date +%Y%m%d_%H%M%S)

# 世代管理（3世代保持）
ls -t app.db.backup.* | tail -n +4 | xargs rm -f
```

### 3.2 復元手順

```bash
# 復元コマンド
cp app.db.backup.YYYYMMDD_HHMMSS app.db
```

## 4. 切替ウィンドウ定義

### 4.1 推奨時間帯

```
開始: 深夜 2:00 JST
終了: 深夜 3:00 JST
理由:
  - plan/remindイベントの実行時間外
  - ユーザーへの影響最小
```

### 4.2 切替手順

```bash
# Step 1: v0.2停止
systemctl stop oni-coach-v0.2

# Step 2: バックアップ
cp app.db app.db.backup.$(date +%Y%m%d_%H%M%S)

# Step 3: DB削除・再作成
rm app.db
python scripts/init_db.py

# Step 4: v0.3デプロイ
git checkout main
git pull
pip install -r requirements.txt
systemctl start oni-coach-v0.3

# Step 5: 動作確認
curl http://localhost:8000/health
python -c "from db import engine; print(engine.execute('SELECT COUNT(*) FROM configurations').scalar())"

# Step 6: Slackテスト
# （手動）Slackから /base_commit 実行
```

## 5. Migration SQL

### 5.1 実行SQL

```sql
-- 既存テーブル削除
DROP TABLE IF EXISTS schedules;
DROP TABLE IF EXISTS behavior_logs;
DROP TABLE IF EXISTS slack_ignore_events;
DROP TABLE IF EXISTS daily_punishments;
DROP TABLE IF EXISTS pavlok_counts;

-- 新規テーブル作成（init_db.pyで実行）
-- CREATE TABLE commitments (...);
-- CREATE TABLE schedules (...);
-- CREATE TABLE action_logs (...);
-- CREATE TABLE punishments (...);
-- CREATE TABLE configurations (...);
-- CREATE TABLE config_audit_log (...);
```

### 5.2 init_db.pyの責務

```python
# scripts/init_db.py

def init_db():
    """DB初期化とデフォルト設定の投入"""

    # 1. テーブル作成
    Base.metadata.create_all(engine)

    # 2. デフォルト設定投入
    for key, definition in CONFIG_DEFINITIONS.items():
        config = Configuration(
            key=key,
            value=json.dumps(definition["default"]),
            value_type=definition["type"],
            description=definition["description"],
            default_value=json.dumps(definition["default"]),
            min_value=definition.get("min"),
            max_value=definition.get("max"),
            valid_values=json.dumps(definition.get("valid_values", [])),
            version=1
        )
        session.add(config)

    session.commit()
```

## 6. ロールバック計画

### 6.1 即時ロールバック（5分以内）

```bash
# v0.3停止
systemctl stop oni-coach-v0.3

# DB復元
cp app.db.backup.YYYYMMDD_HHMMSS app.db

# v0.2起動
systemctl start oni-coach-v0.2

# 確認
curl http://localhost:8000/health
```

### 6.2 ロールバック判定基準

| 状況 | 判定 |
|------|------|
| init_db.py失敗 | 即時ロールバック |
| v0.3起動失敗 | 即時ロールバック |
| Slack接続不可 | 即時ロールバック |
| Pavlok接続不可 | 調査の上判断 |

## 7. 注意事項

### 7.1 データ移行不可

```
v0.2 → v0.3 のデータ移行は行わない

理由:
  - スキーマが大幅に変更
  - データ量が少ない
  - クリーンスタートを推奨
```

### 7.2 コミットメントの再登録

```
切替後、ユーザーが以下を再登録する必要あり:
  - /base_commit でコミットメント設定
  - /config で設定値調整（必要に応じて）
```

## 8. 関連ドキュメント

- v0.3_design.md: 9. Migration計画
- deletion-policy.md: 削除方針
- branch-strategy.md: ブランチ戦略
