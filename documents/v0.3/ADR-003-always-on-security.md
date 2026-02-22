# ADR-003: 常時起動前提の防御設計

## Status
Proposed

## Context
v0.3ではFastAPIが常時起動することが前提となる（Slack Webhook受信、Worker定期実行）。
これにより、外部からの攻撃面が増加するため、適切な防御設計が必要。

## Decision

### 防御レイヤー構成

```
┌──────────────────────────────────────────────────────────┐
│                      Internet                             │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                 Layer 1: Gateway                          │
│  - Slack署名検証                                          │
│  - replay攻撃対策 (5分window)                             │
│  - レート制限 (10 req/min per user)                       │
│  - ユーザールーティング                                    │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                 Layer 2: Network                          │
│  - inbound制限 (Slack IP ranges + Gateway IPのみ許可)     │
│  - TLS/HTTPS                                              │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                 Layer 3: Application (FastAPI)            │
│  - 署名再検証                                             │
│  - ユーザー認可 (AUTHORIZED_USERS)                         │
│  - 入力バリデーション                                      │
│  - /internal保護                                          │
└──────────────────────────────────────────────────────────┘
```

### 1. Inbound制限

#### /internalエンドポイントの保護

`/internal/*`エンドポイントはWorker専用とし、外部アクセスを遮断する。

**方式**: ヘッダー署名方式を採用

```python
# FastAPI middleware
import hmac
import hashlib

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET")

@app.middleware("http")
async def verify_internal_access(request: Request, call_next):
    if request.url.path.startswith("/internal"):
        signature = request.headers.get("X-Internal-Signature")
        timestamp = request.headers.get("X-Internal-Timestamp")

        # 1. タイムスタンプ検証 (5分以内)
        if abs(time.time() - int(timestamp)) > 300:
            raise HTTPException(401, "Expired timestamp")

        # 2. 署名検証
        body = await request.body()
        expected = hmac.new(
            INTERNAL_SECRET.encode(),
            f"{timestamp}:{body}".encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            raise HTTPException(401, "Invalid signature")

    return await call_next(request)
```

**Worker側の実装**:

```python
# Workerが/internalをコールする際
def call_internal_api(endpoint: str, data: dict):
    timestamp = str(int(time.time()))
    body = json.dumps(data)
    signature = hmac.new(
        INTERNAL_SECRET.encode(),
        f"{timestamp}:{body}".encode(),
        hashlib.sha256
    ).hexdigest()

    requests.post(
        f"http://localhost:8000{endpoint}",
        headers={
            "X-Internal-Signature": signature,
            "X-Internal-Timestamp": timestamp,
            "Content-Type": "application/json"
        },
        data=body
    )
```

#### 外部IP制限（オプション）

将来的にSlack IPレンジのみ許可する場合:

```
# Slack IP ranges (定期更新必要)
https://api.slack.com/docs/rate-limits
```

**現状判断**: Gateway経由のみアクセス可能であれば、IP制限は必須ではない。
Gatewayが適切に検証していれば、FastAPIへの直接アクセスは発生しないため。

### 2. レート制限戦略

#### Gatewayレベル

| 制限 | 値 | 対象 |
|------|-----|------|
| リクエスト数 | 10 req/min | user_id単位 |
| バースト | 20 req/min | 短期間の許容 |

#### FastAPIレベル

| 制限 | 値 | 対象 |
|------|-----|------|
| コマンド実行 | 5 req/min | /slack/command |
| Interactive | 20 req/min | /slack/interactive |
| Internal | 制限なし | /internal/* |

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/slack/command")
@limiter.limit("5/minute")
async def slack_command(request: Request):
    ...
```

### 3. 認可・認証

#### 認証フロー

```
1. Gateway: Slack署名検証
2. FastAPI: 転送署名検証 (X-Forwarded-Signature)
3. FastAPI: ユーザー認可 (AUTHORIZED_USERS)
4. FastAPI: コマンド/アクション別の追加チェック
```

#### 認可マトリックス

| コマンド | 認証済みユーザー | ADMIN |
|---------|-----------------|-------|
| `/base_commit` | ✅ | ✅ |
| `/stop` | ✅ | ✅ |
| `/restart` | ✅ | ✅ |
| `/config` | ✅ | ✅ |
| `/audit` | ✅ | ✅ |
| `/admin/*` | ❌ | ✅ |

※ 現状1ユーザー前提のため、ADMIN分離は将来拡張用

### 4. 入力バリデーション

#### コマンド引数

```python
# /stop, /restart: 引数禁止
if text.strip():
    return {"text": "このコマンドは引数を受け付けません"}

# /base_commit: 入力長制限
MAX_COMMITMENT_LENGTH = 100
if len(task) > MAX_COMMITMENT_LENGTH:
    return {"text": f"タスク名は{MAX_COMMITMENT_LENGTH}文字以内で入力してください"}
```

#### Interactive Component

```python
# action_idのバリデーション
VALID_ACTIONS = {
    "remind_yes", "remind_no",
    "ignore_yes", "ignore_no",
    "commitment_add_row",
    "config_reset_all", "config_history"
}

if action_id not in VALID_ACTIONS:
    raise HTTPException(400, "Invalid action")
```

### 5. ログ・監視

#### セキュリティイベントログ

```python
# 監査ログに記録するイベント
SECURITY_EVENTS = [
    "auth_failure",      # 認証失敗
    "signature_invalid", # 署名検証失敗
    "rate_limit",        # レート制限超過
    "unauthorized_user", # 未認可ユーザー
    "internal_access",   # /internalへのアクセス
]
```

## Consequences

### Positive
- 多層防御によるセキュリティ向上
- /internalエンドポイントの保護
- 適切なレート制限

### Negative
- 実装複雑性の増加
- 設定項目の増加 (INTERNAL_SECRET等)

### Risks
- INTERNAL_SECRETの漏洩リスク
  - 対策: 環境変数管理、ローテーション計画

## Implementation Notes

1. `INTERNAL_SECRET`環境変数の設定
2. FastAPI middleware実装
3. Worker側の署名生成ロジック
4. slowapiの導入（レート制限）

## Related
- ADR-001: Gateway責務境界
- ADR-002: ルーティングキーとマッピング方式
