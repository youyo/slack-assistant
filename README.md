# Slack Assistant

Slack Bot powered by AWS Bedrock AgentCore Runtime and Strands Agents.

## Tech Stack

| Category | Technology |
|----------|------------|
| Infrastructure | TypeScript CDK (aws-cdk v2.201.0) |
| Lambda Runtime | Python 3.13 (uv依存管理) |
| Agent Framework | [Strands Agents](https://github.com/strands-agents/sdk-python) |
| Router Model | Amazon Nova 2 Lite (`global.amazon.nova-2-lite-v1:0`) |
| Conversation Model | Claude Sonnet 4.5 (`global.anthropic.claude-sonnet-4-5-20250929-v1:0`) |
| Memory | Bedrock AgentCore Memory |
| Orchestration | AWS Step Functions |

## Architecture

```mermaid
sequenceDiagram
    participant Slack
    participant APIGateway as API Gateway
    participant Ingress as Ingress Lambda
    participant SFN as Step Functions
    participant Invoke as Invoke Lambda
    participant Agent as AgentCore Runtime
    participant Post as Post Lambda

    Slack->>APIGateway: POST /slack/events
    APIGateway->>Ingress: Event
    Ingress->>Ingress: 署名検証・正規化
    Ingress->>SFN: startExecution
    Ingress-->>APIGateway: 200 OK
    APIGateway-->>Slack: 200 OK

    SFN->>Invoke: InvokeAgentTask
    Invoke->>Agent: invoke_agent_runtime
    Agent->>Agent: Router Agent (返信判定)
    Agent->>Agent: Conversation Agent (返信生成)
    Agent-->>Invoke: AgentResult
    Invoke-->>SFN: Result

    SFN->>Post: PostToSlackTask
    Post->>Slack: chat.postMessage
    Post-->>SFN: Result
```

### Components

| Component | Description |
|-----------|-------------|
| **Ingress Lambda** | Slack署名検証、イベント正規化、Step Functions起動 |
| **Invoke Lambda** | AgentCore Runtime呼び出し、セッションID生成 |
| **AgentCore Runtime** | Router Agent + Conversation Agent（構造化出力） |
| **Post Lambda** | Slack Web API投稿 |
| **AgentCore Memory** | 会話履歴・コンテキスト保持（要約・好み学習・セマンティック検索） |

## Prerequisites

- Node.js 22+
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- AWS CLI configured
- Docker (for Lambda bundling)

## Setup

### 1. Install Dependencies

```bash
npm install
```

### 2. Create Slack App (App Manifest)

App Manifest を使用して Slack App を作成します。

1. https://api.slack.com/apps にアクセス
2. **Create New App** -> **From an app manifest** を選択
3. Workspace を選択
4. `docs/manifest.json` の内容を貼り付け（JSON/YAML 両対応）
5. **Create** をクリック

#### 認証情報を取得

| 項目 | 場所 | 形式 |
|------|------|------|
| Bot User OAuth Token | OAuth & Permissions | `xoxb-...` |
| Signing Secret | Basic Information -> App Credentials | 文字列 |
| Bot User ID | OAuth & Permissions (Bot User 欄) | `U...` |

### 3. Configure Environment

```bash
cp .env.example .env
```

`.env` を編集:

```bash
PRODUCT_ID=slack-assistant
STAGE=preview
VERSION=v0
CDK_DEFAULT_ACCOUNT=<your-aws-account-id>
CDK_DEFAULT_REGION=ap-northeast-1
```

### 4. Deploy

```bash
# 1. Parameter Store に認証情報を設定
aws ssm put-parameter \
  --name "/slack-assistant/preview/slack-bot-token" \
  --value "xoxb-your-token" \
  --type String

aws ssm put-parameter \
  --name "/slack-assistant/preview/slack-signing-secret" \
  --value "your-signing-secret" \
  --type String

aws ssm put-parameter \
  --name "/slack-assistant/preview/slack-bot-user-id" \
  --value "U..." \
  --type String

# 2. スタックをデプロイ
PRODUCT_ID=slack-assistant STAGE=preview VERSION=v0 npx cdk deploy --all
```

### 5. Update Event Subscriptions URL

デプロイ完了後、API Gateway URL を Slack App に設定:

1. Slack App 設定画面 -> **Event Subscriptions**
2. **Request URL** を更新:
   ```
   https://<api-id>.execute-api.ap-northeast-1.amazonaws.com/slack/events
   ```

※ Subscribe events は Manifest で定義済みのため設定不要

## Development

### CDK Commands

```bash
# Synthesize CloudFormation template
PRODUCT_ID=slack-assistant STAGE=preview VERSION=v0 npm run cdk:synth

# Deploy all stacks
PRODUCT_ID=slack-assistant STAGE=preview VERSION=v0 npm run cdk:deploy

# Show diff
PRODUCT_ID=slack-assistant STAGE=preview VERSION=v0 npm run cdk:diff

# Hotswap deploy (Lambda only, faster)
PRODUCT_ID=slack-assistant STAGE=preview VERSION=v0 npm run cdk:hotswap
```

### Lambda Development (Python/uv)

```bash
# 依存パッケージ同期
cd src/lambda/agentcore-strands && uv sync

# テスト実行
uv run pytest

# コード整形
uv run ruff format .
uv run ruff check --fix .
```

### Testing

```bash
# TypeScript CDK テスト
npm test

# Python Lambda テスト
cd src/lambda/agentcore-strands && uv run pytest
```

## Configuration

### SSM Parameters

| Parameter Name | Description |
|----------------|-------------|
| `/{product_id}/{stage}/slack-bot-token` | Slack Bot OAuth Token (`xoxb-...`) |
| `/{product_id}/{stage}/slack-signing-secret` | Slack Signing Secret |
| `/{product_id}/{stage}/slack-bot-user-id` | Slack Bot User ID (`U...`) |
| `/{product_id}/{stage}/agentcore-memory-id` | AgentCore Memory ID (自動生成) |

### Environment Variables

デプロイ時に自動設定される環境変数:

| Lambda | Variable | Description |
|--------|----------|-------------|
| ingress | `SLACK_SIGNING_SECRET` | Slack署名検証用 |
| ingress | `SLACK_BOT_USER_ID` | Bot自身の発言除外用 |
| ingress | `STEP_FUNCTION_ARN` | State Machine ARN |
| invoke-agentcore | `AGENT_RUNTIME_ARN` | AgentCore Runtime ARN |
| agentcore-strands | `AGENTCORE_MEMORY_ID` | Memory ID |
| agentcore-strands | `ROUTER_MODEL_ID` | Router Agent用モデルID |
| agentcore-strands | `CONVERSATION_MODEL_ID` | Conversation Agent用モデルID |
| post-to-slack | `SLACK_BOT_TOKEN` | Slack API Token |

## Project Structure

```
slack-assistant/
├── bin/
│   └── cdk-app.ts              # CDK entry point
├── lib/
│   ├── constructs/             # Reusable CDK constructs
│   │   ├── apigateway.ts       # HTTP API construct
│   │   ├── bedrock-agentcore-runtime.ts
│   │   ├── lambda.ts           # Lambda (Python/Docker) construct
│   │   └── utility.ts          # Naming conventions
│   └── stacks/
│       ├── stateful.ts         # AgentCore Memory
│       └── stateless.ts        # Lambda, API Gateway, Step Functions, AgentCore Runtime
├── src/
│   └── lambda/
│       ├── ingress/            # Slack Events API handler
│       │   ├── handler.py
│       │   └── pyproject.toml
│       ├── invoke-agentcore/   # AgentCore Runtime invoker
│       │   ├── handler.py
│       │   └── pyproject.toml
│       ├── agentcore-strands/  # Router + Conversation Agent
│       │   ├── agents/
│       │   │   ├── router_agent.py
│       │   │   └── conversation_agent.py
│       │   ├── graph.py        # Multi-agent orchestration
│       │   ├── handler.py      # AgentCore Runtime entry point
│       │   └── pyproject.toml
│       └── post-to-slack/      # Slack posting handler
│           ├── handler.py
│           └── pyproject.toml
├── test/                       # CDK tests
├── docs/                       # Design documents
│   ├── manifest.json          # Slack App Manifest
│   ├── slack-strands-agentcore-architecture.md
│   └── api-specification.md
└── package.json
```

## License

MIT
