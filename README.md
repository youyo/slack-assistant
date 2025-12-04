# Slack Assistant

Slack Bot powered by AWS Bedrock AgentCore Runtime and Strands Agents.

## Architecture

- **Slack Events API** -> API Gateway -> Ingress Lambda -> Step Functions -> AgentCore Runtime -> Posting Lambda -> Slack

## Setup

### Prerequisites

- Node.js 22+
- Python 3.13+
- AWS CLI configured
- Docker (for Lambda bundling)

### 1. Install Dependencies

```bash
npm install
```

### 2. Create Slack App

1. https://api.slack.com/apps にアクセス
2. **Create New App** -> **From scratch** を選択
3. App 名を入力（例: `slack-assistant`）
4. Workspace を選択

#### Bot Token Scopes 設定

**OAuth & Permissions** -> **Scopes** -> **Bot Token Scopes** で以下を追加:

| Scope | Description |
|-------|-------------|
| `chat:write` | メッセージ投稿 |
| `app_mentions:read` | メンション読み取り |
| `channels:history` | パブリックチャンネル履歴 |
| `groups:history` | プライベートチャンネル履歴 |
| `im:history` | DM 履歴 |
| `mpim:history` | グループDM 履歴 |

#### App をワークスペースにインストール

**OAuth & Permissions** -> **Install to Workspace**

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

### 5. Configure Slack Event Subscriptions

1. Slack App 設定画面で **Event Subscriptions** を有効化
2. **Request URL** に API Gateway エンドポイントを設定:
   ```
   https://<api-id>.execute-api.ap-northeast-1.amazonaws.com/slack/events
   ```
3. **Subscribe to bot events** で以下を追加:
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`
   - `app_mention`

## Development

### CDK Commands

```bash
# Synthesize CloudFormation template
PRODUCT_ID=slack-assistant STAGE=preview VERSION=v0 npm run cdk:synth

# Deploy all stacks
PRODUCT_ID=slack-assistant STAGE=preview VERSION=v0 npm run cdk:deploy

# Show diff
PRODUCT_ID=slack-assistant STAGE=preview VERSION=v0 npm run cdk:diff
```

### Testing

```bash
npm test
```

## Project Structure

```
slack-assistant/
├── bin/
│   └── cdk-app.ts           # CDK entry point
├── lib/
│   ├── constructs/          # Reusable CDK constructs
│   │   ├── apigateway.ts
│   │   ├── bedrock-agentcore-runtime.ts
│   │   ├── lambda.ts
│   │   └── utility.ts
│   └── stacks/
│       ├── stateful.ts      # AgentCore Memory (future)
│       └── stateless.ts     # Lambda, API Gateway, Step Functions
├── src/
│   └── lambda/
│       ├── ingress/         # Slack Events API handler
│       ├── post-to-slack/   # Slack posting handler
│       └── agentcore-strands/  # AgentCore Runtime (future)
├── test/
├── docs/                    # Design documents
└── package.json
```

## License

MIT
