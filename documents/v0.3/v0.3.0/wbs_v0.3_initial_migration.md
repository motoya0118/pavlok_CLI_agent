# Oni System v0.3 - Initial Tasks

Created: 2026-02-14

## Overview
This document converts the WBS (Work Breakdown Structure) for v0.3 into actionable GitHub Issues for project management.

## Labels
- `priority: critical` - 重要度（高）
- `priority: high` - 重要度（中）
- `priority: medium` - 重要度（低）
- `kind: bug` - バグ修正
- `kind: feature` - 機能実装
- `kind: test` - テスト追加
- `kind: docs` - ドキュメント
- `kind: refactoring` - リファクタリング
- `status: backlog` - 未着手
- `status: in-progress` - 進行中
- `status: done` - 完了
- `role: backend` - Backend担当
- `role: frontend` - Frontend担当
- `role: devops` - DevOps担当
- `role: qa` - QA担当

## Team Structure
- Backend: @ユーザー名
- Frontend: @ユーザー名（TBD）
- DevOps: @ユーザー名
- QA: @ユーザー名

---

## Phase 2.1: チーム体制決定

### Issue #1
**Title**: チーム体制決定と役割明確化

**Description**:
- チーム体制を決定（Backend, Frontend, DevOps, QAの各ロール）
- 各ロールの責任範囲を明確化
- 期待値の定義（Slack BlockKitフォーマット等）をドキュメント化

**Acceptance Criteria**:
- [ ] チームメンバ全員が承認
- [ ] WBSがGitHub Issuesに反映され、各担当が自分のタスクを確認できる状態

**Tasks**:
1. [role: backend, kind: feature, priority: high] チーム体制ドキュメント作成
2. [role: backend, kind: feature, priority: high] 各ロールの責任範囲を明確化したドキュメント作成
3. [role: all, kind: docs, priority: high] Slack BlockKitフォーマットの期待値ドキュメント作成

---

## Phase 2.2: タスク管理ツール導入

### Issue #2
**Title**: タスク管理ツール導入（GitHub Projects or ZenTao）

**Description**:
- GitHub ProjectsまたはZenTaoを使用して、タスク管理システムを導入
- WBSの各タスクをIssuesとして登録して、進捗状況を管理

**Acceptance Criteria**:
- [ ] チームメンバ全員が承認
- [ ] 適切なツール導入が完了し、WBSがGitHubで利用可能な状態

**Tasks**:
1. [role: devops, kind: feature, priority: high] GitHub Projects/ZenTaoの選定と導入
2. [role: devops, kind: feature, priority: high] WBSの各タスクをIssuesとして登録
3. [role: devops, kind: feature, priority: medium] ラベルとマイルストーンの定義
4. [role: all, kind: docs, priority: high] タスク管理ガイドライン作成

---

## Phase 2.3: 期待値定義とドキュメント作成

### Issue #3
**Title**: Slack BlockKitフォーマットの期待値定義とドキュメント作成

**Description**:
- v0.3のSlack BlockKitフォーマットを定義
- 期待値（Modal、Blocksの構造）を詳細にドキュメント化
- APIハンドラが返すべきレスポンス構造を明確化

**Acceptance Criteria**:
- [ ] ドキュメントが`docs/v0.3/`に作成され、各チームメンバが参照可能な状態

**Tasks**:
1. [role: backend, kind: docs, priority: high, depends_on: [2]] Slack BlockKitフォーマット仕様書作成
2. [role: backend, kind: docs, priority: high, depends_on: [2]] APIハンドラの期待値ドキュメント作成
3. [role: backend, kind: feature, priority: high, depends_on: [1, 2]] APIハンドラ実装開始（TODO解消）
4. [role: qa, kind: test, priority: high] E2E統合テスト作成と実行

---

## Phase 2.4: 最初のスプリント

### Issue #4
**Title**: APIハンドラ実装 - 最初のスプリント

**Description**:
- `backend/api/command.py`の`process_base_commit`等のTODOを解消
- Slack Modalを返却するBlockKit構築を実装

**Acceptance Criteria**:
- [ ] Modalレスポンスが正しく返却される
- [ ] 最初のスプリントが完了（base_commit機能）

**Tasks**:
1. [role: backend, kind: feature, priority: high, depends_on: [3]] `process_base_commit`実装 - Modal返却
2. [role: backend, kind: feature, priority: high, depends_on: [3]] Slack BlockKitコンポーネント実装
3. [role: qa, kind: test, priority: high, depends_on: [1, 2]] 最初のスプリントのE2Eテスト作成

---

## Notes

### タスク管理の流れ
1. Issue作成 → 担当→担当者割り当て→着手
2. 進捗中→担当者実装→ Pull Request提出→ レビュー→マージ
3. 完了→Issueをクローズ、マイルストーン更新

### PM活動
- Issuesでラベル管理（priority, kind, status, role）
- プロジェクトマイルストーンと連携
- 各担当者が自分のタスクを簡単に確認・更新可能
