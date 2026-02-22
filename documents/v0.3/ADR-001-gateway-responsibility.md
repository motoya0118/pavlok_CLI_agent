# ADR-001: Gateway責務境界

## Status
Proposed

## Context
v0.3ではCloudflare Workerをgatewayとして配置し、SlackからのWebhookを受けてFastAPIバックエンドに転送する。
gatewayがどこまで責務を持つべきかを明確にする必要がある。

## Decision

### Gatewayが担当する責務（Cloudflare Worker）

| 責務 | 実装状態 | 判定 |
|------|---------|------|
| Slack署名検証 | 実装済み | 採用 |
| ユーザー→バックエンドのルーティング | 実装済み | 採用 |
| replay攻撃対策 | 未実装 | 採用 |
| レート制限 | 未実装 | 採用 |
| 不正ユーザーの遮断 | USER_MAPで実現 | 採用 |

### Gatewayが担当しない責務（FastAPI側）

| 責務 | 理由 |
|------|------|
| ビジネスロジック | gatewayは振り分けのみ |
| 設定値の管理 | DBアクセスはFastAPI側 |
| 二重署名検証 | 冗長だが防御層として残す |

### 二重防御の方針

```
Slack → Gateway(Cloudflare) → FastAPI
         │                      │
         ├─ 署名検証 ✓           ├─ 署名検証 ✓ (二重防御)
         ├─ replay対策          ├─ ユーザー認可
         ├─ レート制限          ├─ 入力バリデーション
         └─ ルーティング        └─ ビジネスロジック
```

**判断理由**: Gatewayでの検証を突破しても、FastAPI側でも検証することで多層防御を実現。ただし、重複する処理は最小限にする。

### 具体的な実装要件

#### 1. Replay攻撃対策

```javascript
// 追加実装が必要
const MAX_TIMESTAMP_AGE = 300; // 5分

async function checkReplay(timestamp) {
  // X-Slack-Request-Timestampが現在時刻から5分以上離れている場合は拒否
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(timestamp)) > MAX_TIMESTAMP_AGE) {
    return false;
  }
  return true;
}
```

#### 2. レート制限

```javascript
// Cloudflare KVを使用した簡易レート制限
// 同一user_idから1分間に最大10リクエストまで
const RATE_LIMIT_WINDOW = 60; // 秒
const RATE_LIMIT_MAX = 10;

async function checkRateLimit(userId, env) {
  const key = `rate:${userId}`;
  const count = await env.KV.get(key);
  if (count && parseInt(count) >= RATE_LIMIT_MAX) {
    return false;
  }
  await env.KV.put(key, (parseInt(count || 0) + 1).toString(), {
    expirationTtl: RATE_LIMIT_WINDOW
  });
  return true;
}
```

#### 3. 同期転送への変更

現在の実装は非同期転送だが、Slackの3秒タイムアウト制約があるため、**同期転送に変更する**。

```javascript
// Before: 非同期（Slackに即座に200を返す）
fetch(backend, {...}); // awaitなし
return new Response(backend);

// After: 同期（バックエンドの応答を待つ）
const response = await fetch(backend, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Forwarded-Signature": signature,  // 検証用
    "X-Slack-Request-Timestamp": timestamp
  },
  body: JSON.stringify(payload)
});
return response;
```

### FastAPI側での二重検証

FastAPI側でも以下を実施する：
1. `X-Forwarded-Signature`の検証
2. `X-Slack-Request-Timestamp`のreplayチェック
3. ユーザー認可チェック（AUTHORIZED_USERS）

## Consequences

### Positive
- 多層防御によるセキュリティ向上
- Gatewayで不正リクエストを早期遮断
- FastAPI側での詳細な認可制御

### Negative
- 署名検証の計算コストが2倍（許容範囲）
- GatewayとFastAPIの設定同期が必要

### Risks
- Cloudflare WorkerのCPU時間制限（無料枠: 10ms）
  - 署名検証は軽量なため問題なし
  - レート制限のKVアクセスも高速

## Implementation Notes

1. `documents/v0.3/claudflare.js`を拡張
2. Cloudflare KVの設定（レート制限用）
3. FastAPI側での転送ヘッダー検証ミドルウェア実装

## Related
- ADR-003: 常時起動前提の防御設計
