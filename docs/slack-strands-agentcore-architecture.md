# Slack × Strands × Bedrock AgentCore Runtime Bot 設計書

## 0. ゴール

- Slack チャンネルの **すべてのメッセージ**を取得する
- まずは **安価な LLM（例: Amazon Nova Micro）** で  
  「応答すべきか？」「どのモードで返すか？」を判断する（Router）
- 会話が必要な場合のみ **高性能 LLM（例: Sonnet 4.5）** に処理を委譲（Conversation）
- メモリは **Bedrock AgentCore Memory × Strands SessionManager** を使用  
  - チャンネル = actor（長期記憶）  
  - スレッド = session（短期記憶）
- インフラは **TypeScript CDK**
- Lambda は **Python 3.13**

---

## 1. 全体アーキテクチャ

### コンポーネント

- Slack App（Events API）
- API Gateway HTTP API  
  - `POST /slack/events` → Ingress Lambda
- Ingress Lambda (Python 3.13)
  - Slack 署名検証
  - `url_verification` 応答
  - Slack イベント正規化
  - Step Functions 実行開始
- Step Functions State Machine
  - Task1: Bedrock AgentCore Runtime（Strands Graph）の呼び出し（AWS SDK 統合）
  - Task2: Slack Posting Lambda 実行
- Bedrock AgentCore Runtime
  - Strands マルチエージェント Graph（Router + Conversation）を実行
- Bedrock AgentCore Memory Resource
- Slack Posting Lambda (Python 3.13)

---

## 2. メッセージフロー（E2E）

1. User が Slack チャンネル/DM にメッセージを送信
2. Slack Events API → API Gateway HTTP API (`/slack/events`)
3. Ingress Lambda
    - Slack 署名検証
    - `url_verification` は `challenge` を返して終了
    - `event_callback` のメッセージイベントのみを抽出
    - bot 自身の発言など不要なものを除外
    - 必要情報を正規化して Step Functions に渡す
    - Slack には **即 200** を返して 3 秒制約をクリア
4. Step Functions
    - Task `InvokeAgent` で Bedrock AgentCore Runtime の handler を AWS SDK 統合で呼び出し
    - Task `PostToSlack` で Slack Posting Lambda を呼び、応答を投稿
5. Slack Posting Lambda
    - AgentCore からの JSON 出力を解釈
    - `should_reply` / `reply_mode` / `typing_style` などに応じて Slack Web API をコール

---

## 3. メモリ設計（AgentCore Memory）

### actor_id / session_id

- `actor_id`: Slack チャンネルID
  - public: `Cxxxxxx`
  - private: `Gxxxxxx`
  - DM: `Dxxxxxx`（DM もチャンネル扱い）
- `session_id`: スレッド単位
  - スレッドメッセージ: `thread_ts`
  - スレッドでないメッセージ: `ts`

### Long-term memory 戦略（namespaces）

Memory resource 作成時の strategy 例:

- `summaryMemoryStrategy`  
  - name: `SessionSummarizer`  
  - namespaces: `/summaries/{actorId}/{sessionId}`  
  - スレッドごとのサマリを保持
- `userPreferenceMemoryStrategy`  
  - name: `ChannelPreferences`  
  - namespaces: `/preferences/{actorId}`  
  - チャンネルごとのトーン・好み・ルールなど
- `semanticMemoryStrategy`（facts 用）  
  - name: `ChannelFacts`  
  - namespaces: `/facts/{actorId}`  
  - プロジェクト名・よく出る用語・チャンネルの意味など

### 保持期間（例）

- `short_term_retention_days = 14`
- `long_term_retention_days = 365`

---

## 4. Strands マルチエージェント Graph 設計

### ノード構成

Graph: Router Agent → (必要に応じて) Conversation Agent

#### Node 1: Router Agent（判断専用・安価モデル）

- モデル例: `amazon.nova-micro`
- 役割:
  - `should_reply`: 返信すべきか
  - `route`: `"ignore" | "simple_reply" | "full_reply"`
  - `reply_mode`: `"thread" | "channel"`
  - `typing_style`: `"none" | "short" | "long"`（プレースホルダ/typing 用）
- 入力（例）:
  - `text`: ユーザー発話
  - `is_mentioned`: bot がメンションされているか
  - `is_dm`: DM かどうか
  - `thread_depth`: スレッド内で何番目のメッセージか
  - `channel_kind`: `"public" | "private" | "dm"`
  - メモリから取得した `preferences` / `facts` / `summaries`
- 出力 JSON 例:

```json
{
  "should_reply": true,
  "route": "full_reply",
  "reply_mode": "thread",
  "typing_style": "short",
  "reason": "ユーザーがメンションしているため"
}
```

#### Node 2: Conversation Agent（本体・高性能モデル）

- モデル例: `sonnet-4.5`
- AgentCoreMemorySessionManager を使用  
  - `actor_id` / `session_id` は Router と共通
- 役割:
  - 実際の回答文を生成
  - 会話から得られる新しい `facts` / `preferences` / `summaries` をメモリに反映

- 入力:
  - 元のユーザーメッセージ
  - Router の出力（`route`, `reply_mode` など）
  - LTM / STM

- 出力 JSON 例:

```json
{
  "should_reply": true,
  "route": "full_reply",
  "reply_mode": "thread",
  "typing_style": "short",
  "reply_text": "こんにちは！お呼びでしょうか？",
  "reason": "メンションされたため"
}
```

### Graph 内の制御ロジック

- Router 実行 → JSON をパース
- `should_reply == false` → その時点で終了（Conversation Agent は呼ばない）
- `route == "simple_reply"` → Router の出力に簡単な `reply_text` を付けて終了
- `route == "full_reply"` → Conversation Agent に遷移
- Conversation Agent の JSON を Graph の最終出力として AgentCore Runtime handler が返す

---

## 5. System Prompt 設計

### Router Agent System Prompt（イメージ）

You are a routing assistant for a Slack bot.

- Decide whether the bot should reply.
- Decide the reply mode (thread/channel).
- Decide the typing style.

Rules:
- If the bot is mentioned (`is_mentioned=true`), MUST reply.
- In DMs (`is_dm=true`), normally reply.
- In busy channels, avoid replying too often unless needed.
- Use channel preferences and facts from memory to adjust your behavior.

Return ONLY a single JSON object:

```json
{
  "should_reply": boolean,
  "route": "ignore" | "simple_reply" | "full_reply",
  "reply_mode": "thread" | "channel",
  "typing_style": "none" | "short" | "long",
  "reason": "short Japanese explanation"
}
```

### Conversation Agent System Prompt（イメージ）

You are a helpful Slack assistant for a software engineering team.

- Use long-term memory (channel-level facts and preferences).
- Use short-term memory (thread context and summaries).
- Reply in natural Japanese unless instructed otherwise.
- Slack-friendly formatting:
  - concise
  - markdown allowed
  - polite and friendly tone, emojis ok but not too many.

Return ONLY a single JSON object:

```json
{
  "should_reply": boolean,
  "route": "ignore" | "simple_reply" | "full_reply",
  "reply_mode": "thread" | "channel",
  "typing_style": "none" | "short" | "long",
  "reply_text": "Slack message in Japanese",
  "reason": "short explanation for logs"
}
```

---

## 6. Ingress Lambda（Python 3.13）

### 役割

- Slack の署名検証
- `url_verification` 応答
- `event_callback` 内のメッセージ系イベントを抽出
- bot 自身の発言などを除外
- 正規化したイベントを Step Functions に渡す
- Slack には常に速やかに `200` を返す（3 秒以内）

### 環境変数

- `SLACK_SIGNING_SECRET`
- `SLACK_BOT_USER_ID`
- `STEP_FUNCTION_ARN`
- （必要に応じて）`SLACK_BOT_TOKEN`

### Step Functions に渡す正規化ペイロード例

```json
{
  "team_id": "T123",
  "channel_id": "C123",
  "channel_kind": "public",
  "user_id": "U123",
  "text": "こんにちは",
  "ts": "1710000000.12345",
  "thread_ts": "1710000000.12345",
  "is_mentioned": true,
  "is_dm": false,
  "event_type": "message"
}
```

---

## 7. Step Functions State Machine

### 構成

- `InvokeAgent` (Task)
- `PostToSlack` (Task)
- 必要に応じて `Fail` / `Succeed`

### `InvokeAgent` State（AWS SDK 統合）

Resource の例:

- `arn:aws:states:::aws-sdk:bedrockagent:invokeAgent`  
  （実際の service/operation 名は AgentCore Runtime の仕様に合わせる）

Parameters のイメージ:

```json
{
  "agentId": "<AGENT_ID>",
  "agentAliasId": "<ALIAS_ID>",
  "sessionId.$": "$.thread_ts",
  "inputText.$": "$.text",
  "memoryConfig": {
    "actorId.$": "$.channel_id"
  },
  "metadata": {
    "slack": {
      "team_id.$": "$.team_id",
      "channel_id.$": "$.channel_id",
      "user_id.$": "$.user_id",
      "is_mentioned.$": "$.is_mentioned",
      "is_dm.$": "$.is_dm",
      "channel_kind.$": "$.channel_kind"
    }
  }
}
```

ResultPath: `"$.agentResult"`

### `PostToSlack` State（Lambda 統合）

Input 例:

```json
{
  "team_id.$": "$.team_id",
  "channel_id.$": "$.channel_id",
  "thread_ts.$": "$.thread_ts",
  "agentResult.$": "$.agentResult"
}
```

---

## 8. Slack Posting Lambda（Python 3.13）

### 役割

- `agentResult` をパース
- `should_reply` / `reply_mode` / `typing_style` / `reply_text` に応じて Slack Web API を呼ぶ

### 環境変数

- `SLACK_BOT_TOKEN`

### Agent 出力 JSON 形式

```json
{
  "should_reply": true,
  "route": "full_reply",
  "reply_mode": "thread",
  "typing_style": "short",
  "reply_text": "Slackに投稿する本文",
  "reason": "ログ用コメント"
}
```

### 挙動

- `should_reply == false` → 何も送らず終了
- `reply_mode == "thread"` → `thread_ts` を指定して `chat.postMessage`
- `reply_mode == "channel"` → `thread_ts` なしで `chat.postMessage`
- `typing_style == "short" or "long"`:
  - 入口 Lambda でプレースホルダを出す場合は `chat.update` で書き換え

---

## 9. TypeScript CDK 構成（概要）

### リソース

- API Gateway HTTP API
  - `/slack/events` → Ingress Lambda
- Ingress Lambda（Python 3.13）
- Slack Posting Lambda（Python 3.13）
- Step Functions State Machine
  - InvokeAgent（CallAwsService）
  - PostToSlack（LambdaInvoke）
- IAM Role
  - Ingress Lambda → `states:StartExecution`
  - StepFunctions → Bedrock AgentCore Runtime: `bedrockagent:Invoke*`
  - StepFunctions → Posting Lambda: `lambda:InvokeFunction`
  - Posting Lambda → VPC/Internet egress（Slack API 用）
- Bedrock AgentCore Runtime & Memory（別スタック or 別ツール）

---

## 10. 実装順序（推奨）

1. Slack Ingress Lambda + API Gateway  
   - Events API を受信し、`url_verification` に応答
2. Step Functions（ダミー実装）  
   - AgentCore 部分は stub Lambda などで代用
3. Slack Posting Lambda  
   - 固定メッセージを返す実装で E2E 確認
4. Bedrock AgentCore Runtime + Strands Graph（Router + Conversation）
5. Bedrock AgentCore Memory Resource の作成と SessionManager 組み込み
6. Step Functions から AgentCore Runtime を AWS SDK 統合で呼ぶよう変更
7. 本番相当のチャンネルで挙動確認し、メモリ・プロンプト・ルーティングをチューニング

---

## 11. メリット

- コスト最適化  
  - Router に安価モデル、Conversation に高性能モデルを使用
- UX 向上  
  - 必要なときだけ会話に参加
  - typing 風のプレースホルダ → 後から本回答に更新
- 高度なメモリ活用  
  - チャンネルの文脈とスレッドの流れを両方踏まえた回答
- 責務分離  
  - Ingress / Orchestration / AgentCore / Posting が疎結合で保守しやすい

---

END
