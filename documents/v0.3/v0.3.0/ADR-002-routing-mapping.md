# ADR-002: ルーティングキーとマッピング方式

## Status
Proposed

## Context
v0.3では「1名1サーバー、Slack 1ワークスペース」の原則を維持する。
Gatewayでユーザーを識別し、適切なバックエンドにルーティングする方式を決定する。

## Decision

### ルーティングキーの選定

| キー | 採用 | 理由 |
|------|------|------|
| `team_id` | ❌ | 1ワークスペース前提なら不要 |
| `user_id` | ✅ | 採用。Slackユーザーを一意に特定 |
| `workspace_id` | ❌ | team_idと同等 |

**決定**: `user_id` をルーティングキーとして採用する。

### マッピング方式

**静的マッピング**を採用する。

```javascript
const USER_MAP = {
  "U03JBULT484": "https://oni-coach-userA.example.com/slack"
};
```

**理由**:
- 1ユーザー前提のため、動的マッピングの複雑性は不要
- Cloudflare Workerのコード内で直接管理可能
- 環境変数での管理も可能（将来的な拡張用）

### 1名1サーバー原則の担保方法

#### アーキテクチャ図

```
┌─────────────────────────────────────────────────────────┐
│                   Slack Workspace                        │
│                   (1つのみ使用)                          │
└─────────────────────┬───────────────────────────────────┘
                      │ Webhook
                      ▼
┌─────────────────────────────────────────────────────────┐
│              Cloudflare Worker (Gateway)                 │
│  - user_idでルーティング                                 │
│  - USER_MAPに存在しないuser_idは拒否                     │
└─────────────────────┬───────────────────────────────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
┌─────────────────┐       ┌─────────────────┐
│   User A Server │       │   User B Server │
│  (FastAPI)      │       │  (FastAPI)      │
│  - SQLite DB    │       │  - SQLite DB    │
│  - Worker       │       │  - Worker       │
└─────────────────┘       └─────────────────┘
```

#### 保護メカニズム

1. **Gatewayレベルでの保護**
   - `USER_MAP`に存在するuser_idのみ転送
   - 存在しない場合は `403 Forbidden`

2. **FastAPIレベルでの保護**
   - `AUTHORIZED_USERS`環境変数でホワイトリスト管理
   - 署名検証でなりすまし防止

3. **物理的分離**
   - 各ユーザーは独立したサーバー（異なるURL）
   - DBも独立（SQLiteファイル分離）

### 設定例

#### Gateway (Cloudflare Worker)

```javascript
// 環境変数として設定可能にする
// Wrangler.toml: { vars: { USER_MAP_JSON: '{"U03JBULT484": "..."}' } }

const USER_MAP = JSON.parse(env.USER_MAP_JSON || '{}');

async function getBackend(userId) {
  const backend = USER_MAP[userId];
  if (!backend) {
    return null; // 403を返す
  }
  return backend;
}
```

#### FastAPI側

```python
# .env
AUTHORIZED_USERS=U03JBULT484

# middleware
def verify_user(payload: dict):
    user_id = payload.get("user", {}).get("id")
    authorized = os.getenv("AUTHORIZED_USERS", "").split(",")
    if user_id not in authorized:
        raise HTTPException(403, "Unauthorized user")
```

## Consequences

### Positive
- シンプルな実装
- 明確なユーザー境界
- 他ユーザーへの影響なし（物理分離）

### Negative
- ユーザー追加時にGatewayの設定変更が必要
- 複数ユーザーでスケールしない（意図的）

### Risks
- Gatewayの設定ミスで全ユーザーが影響を受ける
  - 対策: 環境変数で管理、テスト環境で検証

## Implementation Notes

1. Cloudflare Workerの`USER_MAP`を環境変数化
2. 各FastAPIサーバーで`AUTHORIZED_USERS`設定
3. デプロイ時の設定チェックリスト作成

## Related
- ADR-001: Gateway責務境界
- ADR-003: 常時起動前提の防御設計
