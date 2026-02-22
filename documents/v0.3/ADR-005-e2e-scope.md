# ADR-005: E2E範囲の定義

## Status
Proposed

## Context
v0.3ではSlack連携、Pavlok実機連携が含まれる。
全てを自動化しようとすると複雑化するため、自動化する範囲と人が確認する範囲を明確にする。

## Decision

### E2Eテストの方針

**原則**: 最小限主義（ガードレール原則3）
- Slack見た目・Pavlok実機は手動で良い
- 自動化過剰はNG

### 自動化する範囲

| カテゴリ | テスト項目 | 手段 |
|---------|-----------|------|
| **API** | | |
| | `/slack/command` の署名検証 | Unit Test |
| | `/slack/interactive` の署名検証 | Unit Test |
| | `/internal/*` の保護確認 | Unit Test |
| | 設定値CRUD操作 | Unit Test + Integration Test |
| **DB** | | |
| | schedules INSERT/UPDATE | Unit Test |
| | commitments CRUD | Unit Test |
| | action_logs INSERT | Unit Test |
| | punishments INSERT | Unit Test |
| | configurations CRUD | Unit Test |
| **Worker** | | |
| | pending→processing遷移 | Unit Test |
| | ignore検知ロジック | Unit Test |
| | NOモードロジック | Unit Test |
| | 設定キャッシュ動作 | Unit Test |
| **Slack API** | | |
| | BlockKit JSON生成 | Snapshot Test |
| | message post format | Mock Test |

### 人が確認する範囲

| カテゴリ | 確認項目 | 理由 |
|---------|---------|------|
| **Slack UI** | | |
| | モーダルの見た目 | 目視確認が必要 |
| | BlockKitのレンダリング | 実機で確認 |
| | エラーメッセージの文言 | UX観点 |
| | 激励メッセージの内容 | 文脈依存 |
| **Pavlok実機** | | |
| | 実際に刺激が来るか | 物理デバイス |
| | 強度の体感 | 主観評価 |
| | タイミング | 実時間確認 |
| **Agent** | | |
| | 生成メッセージの品質 | 自然言語評価 |
| | plan_updateの出力 | 目視確認 |

### 成功条件

#### 自動テストの成功条件

```
pytest scripts/tests/
  - 全Unit Test: PASS
  - カバレッジ: 80%以上
  - 実行時間: 30秒以内
```

#### 手動テストの成功条件

| シナリオ | 手順 | 期待結果 |
|---------|------|---------|
| plan登録 | `/base_commit` → モーダル入力 → 送信 | 完了メッセージ表示 |
| plan入力 | planモーダル表示 → 入力 → 送信 | remindスケジュール登録 |
| remind応答(YES) | YESボタン押下 | 完了メッセージ、Pavlok動作なし |
| remind応答(NO) | NOボタン押下 | 罰メッセージ、Pavlok動作あり |
| ignore検知 | 15分放置 | vibe通知、Slackに催促 |
| 設定変更 | `/config` → 値変更 → 保存 | 設定反映確認 |

### 「やらないこと」の明示

| 項目 | 理由 |
|------|------|
| Slack実機への投稿テスト | APIコスト、レート制限 |
| Pavlok API実コール | 回数制限、物理デバイス依存 |
| Agent実行 | 実行時間、コスト |
| ブラウザ自動化 (Playwright等) | 複雑性が高い |
| 24時間稼働テスト | 時間コスト |

### テスト環境

```
┌─────────────────────────────────────────┐
│              Test Environment            │
├─────────────────────────────────────────┤
│  - SQLite (in-memory)                   │
│  - Slack API: Mock                      │
│  - Pavlok API: Mock                     │
│  - Gateway: Skip (直接FastAPIをテスト)   │
│  - Agent: Skip                          │
└─────────────────────────────────────────┘
```

### テストファイル構成

```
scripts/
├── tests/
│   ├── conftest.py           # pytest fixtures
│   ├── test_api/
│   │   ├── test_command.py   # /slack/command
│   │   ├── test_interactive.py # /slack/interactive
│   │   └── test_internal.py  # /internal/*
│   ├── test_db/
│   │   ├── test_schedules.py
│   │   ├── test_commitments.py
│   │   ├── test_action_logs.py
│   │   └── test_configurations.py
│   ├── test_worker/
│   │   ├── test_ignore_mode.py
│   │   ├── test_no_mode.py
│   │   └── test_config_cache.py
│   └── test_slack/
│       ├── test_blockkit.py  # JSON生成テスト
│       └── snapshots/        # BlockKit snapshots
└── ...
```

### CI/CDでの実行

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov
      - run: pytest scripts/tests/ --cov=scripts --cov-report=xml
      - uses: codecov/codecov-action@v4
```

## Consequences

### Positive
- テスト範囲の明確化
- CI/CDでの自動化
- 開発効率向上

### Negative
- 手動テストの工数が残る
- UIテストの自動化が限定的

### Risks
- 手動テストの見落とし
  - 対策: チェックリスト化

## Implementation Notes

1. pytest環境構築
2. conftest.py作成（fixtures）
3. Mockクラス作成（Slack, Pavlok）
4. テストケース実装
5. CI/CD設定

## Related
- v0.3_design.md: 12. 実装タスクリスト - Phase 6: Testing & Deploy
