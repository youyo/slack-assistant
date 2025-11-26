# Slack × Strands × AgentCore Runtime Bot 開発計画

## 概要

設計書 `docs/slack-strands-agentcore-architecture.md` に基づき、Slack Bot を構築する。
- **インフラ**: TypeScript CDK（heptagon-inc/template-cdk-typescript ベース）
- **Lambda**: Python 3.13
- **環境分離**: STAGE で dev/prod 分離
- **テスト方針**: TDD（テスト先行）

---

## フェーズ構成

### Phase 0: プロジェクト初期化
1. CDK プロジェクトをテンプレートから初期化
2. Slack App を作成し、認証情報を取得
3. 環境変数・シークレット管理の設定

### Phase 1: Ingress Lambda + API Gateway（E2E 疎通）
1. テスト作成 → Ingress Lambda 実装
2. API Gateway HTTP API 構築
3. Slack Events API の `url_verification` 確認

### Phase 2: Step Functions + Slack Posting Lambda（ダミー応答）
1. テスト作成 → Slack Posting Lambda 実装
2. Step Functions State Machine 構築（ダミー応答）
3. E2E でダミーメッセージ返信を確認

### Phase 3: AgentCore Runtime + Strands Graph
1. Router Agent / Conversation Agent 実装
2. Strands Graph 構築
3. AgentCore Runtime としてデプロイ
4. Step Functions から AgentCore を呼び出すよう変更

### Phase 4: AgentCore Memory 統合
1. Memory Resource 作成
2. SessionManager 統合
3. 長期記憶 / 短期記憶の動作確認

### Phase 5: チューニング・本番化
1. プロンプト最適化
2. 本番環境デプロイ
3. モニタリング・アラート設定

---

## Phase 0: プロジェクト初期化

### 0-1. CDK プロジェクト初期化

**ディレクトリ構成**:
```
slack-assistant/
├── bin/
│   └── cdk-app.ts
├── lib/
│   ├── constructs/
│   │   ├── utility.ts
│   │   ├── lambda.ts
│   │   ├── apigateway.ts
│   │   └── bedrock-agentcore-runtime.ts
│   └── stacks/
│       ├── stateful.ts      # Secrets Manager
│       └── stateless.ts     # Lambda, API Gateway, Step Functions, AgentCore
├── src/
│   └── lambda/
│       ├── ingress/         # Ingress Lambda (Python)
│       ├── post-to-slack/   # Slack Posting Lambda (Python)
│       └── agentcore-strands/  # AgentCore Runtime (Python + Docker)
├── test/
│   ├── unit/
│   │   ├── ingress.test.ts
│   │   └── post-to-slack.test.ts
│   └── integration/
├── docs/                    # 既存の設計書・参考ファイル
├── package.json
├── pyproject.toml           # Python 依存管理（uv）
├── cdk.json
└── .env
```

**作成するファイル**:
1. `package.json` - テンプレートから複製、依存関係調整
2. `cdk.json` - テンプレートから複製
3. `tsconfig.json` - テンプレートから複製
4. `bin/cdk-app.ts` - Stateful/Stateless スタック定義
5. `lib/constructs/utility.ts` - EnvProps 定義
6. `lib/constructs/lambda.ts` - Python Lambda コンストラクト
7. `lib/constructs/apigateway.ts` - HTTP API コンストラクト
8. `lib/constructs/bedrock-agentcore-runtime.ts` - AgentCore コンストラクト
9. `.env` - PRODUCT_ID 設定
10. `.envrc` - direnv 設定

**環境変数**:
```bash
PRODUCT_ID=slack-assistant
CDK_DEFAULT_ACCOUNT=<AWS_ACCOUNT_ID>
CDK_DEFAULT_REGION=ap-northeast-1
```

### 0-2. Slack App 作成

1. https://api.slack.com/apps で新規 App 作成
2. **Bot Token Scopes** 設定:
   - `chat:write` - メッセージ投稿
   - `app_mentions:read` - メンション読み取り
   - `channels:history` - パブリックチャンネル履歴
   - `groups:history` - プライベートチャンネル履歴
   - `im:history` - DM 履歴
   - `mpim:history` - グループDM 履歴
3. **Event Subscriptions** 有効化（URL は後で設定）
4. **Subscribe to bot events**:
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`
   - `app_mention`
5. 認証情報取得:
   - `SLACK_BOT_TOKEN` (xoxb-...)
   - `SLACK_SIGNING_SECRET`
   - `SLACK_BOT_USER_ID`

### 0-3. シークレット管理

**Secrets Manager** で以下を管理:
- `slack-assistant/dev/slack-bot-token`
- `slack-assistant/dev/slack-signing-secret`
- `slack-assistant/dev/slack-bot-user-id`

---

## Phase 1: Ingress Lambda + API Gateway

### 1-1. テスト作成（Red）

**test/unit/ingress.test.ts**:
- Slack 署名検証のテスト
- `url_verification` 応答テスト
- メッセージイベント正規化テスト
- Bot 自身のメッセージ除外テスト

**test/unit/lambda/ingress/** (Python pytest):
- 同様のテストを Python で実装

### 1-2. Ingress Lambda 実装（Green）

**src/lambda/ingress/handler.py**:
- `docs/ingress_lambda.py` をベースに実装
- 環境変数: `SLACK_SIGNING_SECRET`, `SLACK_BOT_USER_ID`, `STEP_FUNCTION_ARN`
- 出力: 正規化ペイロードを Step Functions に渡す

### 1-3. CDK スタック実装

**lib/stacks/stateless.ts**:
```typescript
// API Gateway HTTP API
const api = new HttpApi(this, "SlackEventsApi", {
  apiName: `${envProps.product_id}-${envProps.stage}-slack-events`,
});

// Ingress Lambda
const ingressLambda = new LambdaPythonFunction(this, "IngressLambda", {
  entry: "src/lambda/ingress",
  handler: "handler.lambda_handler",
  environment: {
    SLACK_SIGNING_SECRET: secretSlackSigningSecret.secretValue.unsafeUnwrap(),
    SLACK_BOT_USER_ID: secretSlackBotUserId.secretValue.unsafeUnwrap(),
    STEP_FUNCTION_ARN: stateMachine.stateMachineArn,
  },
});

// POST /slack/events
api.addRoutes({
  path: "/slack/events",
  methods: [HttpMethod.POST],
  integration: new HttpLambdaIntegration("IngressIntegration", ingressLambda),
});
```

### 1-4. デプロイ・動作確認

```bash
STAGE=dev VERSION=v1 npm run cdk:deploy
```

- Slack App の Event Subscriptions URL を設定
- `url_verification` が成功することを確認

---

## Phase 2: Step Functions + Slack Posting Lambda

### 2-1. テスト作成（Red）

**test/unit/post-to-slack.test.ts** / **pytest**:
- `should_reply=false` でスキップ
- `reply_mode=thread` でスレッド返信
- `reply_mode=channel` でチャンネル返信
- エラーハンドリング

### 2-2. Slack Posting Lambda 実装（Green）

**src/lambda/post-to-slack/handler.py**:
- `docs/post_to_slack_lambda.py` をベースに実装
- 環境変数: `SLACK_BOT_TOKEN`

### 2-3. Step Functions 構築

**lib/stacks/stateless.ts**:
```typescript
// Step Functions State Machine
const stateMachine = new sfn.StateMachine(this, "SlackBotStateMachine", {
  definitionBody: sfn.DefinitionBody.fromChainable(
    // Task 1: Invoke Agent (ダミー実装)
    new sfn.Pass(this, "InvokeAgentDummy", {
      result: sfn.Result.fromObject({
        should_reply: true,
        route: "full_reply",
        reply_mode: "thread",
        reply_text: "(dummy) メッセージを受け取りました",
      }),
      resultPath: "$.agentResult",
    })
    // Task 2: Post to Slack
    .next(new tasks.LambdaInvoke(this, "PostToSlack", {
      lambdaFunction: postToSlackLambda,
      payloadResponseOnly: true,
    }))
  ),
});
```

### 2-4. E2E 動作確認

- Slack でメッセージ送信 → ダミー応答が返ることを確認

---

## Phase 3: AgentCore Runtime + Strands Graph

### 3-1. Router Agent 実装

**src/lambda/agentcore-strands/agents/router_agent.py**:
- `docs/router_agent.py` のプロンプトを使用
- モデル: `amazon.nova-micro`
- 出力: `should_reply`, `route`, `reply_mode`, `typing_style`, `reason`

### 3-2. Conversation Agent 実装

**src/lambda/agentcore-strands/agents/conversation_agent.py**:
- `docs/conversation_agent.py` のプロンプトを使用
- モデル: `claude-sonnet-4.5`
- 出力: Router の出力 + `reply_text`

### 3-3. Strands Graph 実装

**src/lambda/agentcore-strands/graph.py**:
```python
from strands import Agent
from strands.multiagent import Graph

def build_slack_graph(session_manager=None):
    router = Agent(
        system_prompt=ROUTER_SYSTEM_PROMPT,
        model="amazon.nova-micro",
    )

    conversation = Agent(
        system_prompt=CONVERSATION_SYSTEM_PROMPT,
        model="us.anthropic.claude-sonnet-4.5",
        session_manager=session_manager,
    )

    graph = Graph()
    graph.add_node("router", router)
    graph.add_node("conversation", conversation)
    graph.set_entry_point("router")
    graph.add_conditional_edges("router", route_condition)
    graph.add_edge("conversation", END)

    return graph
```

### 3-4. AgentCore Runtime Handler

**src/lambda/agentcore-strands/handler.py**:
- `docs/agentcore_runtime_handler.py` をベースに実装
- Graph を実行し、JSON を返す

### 3-5. Dockerfile

**src/lambda/agentcore-strands/Dockerfile**:
```dockerfile
FROM public.ecr.aws/lambda/python:3.13

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . ${LAMBDA_TASK_ROOT}

CMD ["handler.lambda_handler"]
```

### 3-6. CDK で AgentCore Runtime デプロイ

**lib/stacks/stateless.ts**:
```typescript
const agentCoreRuntime = new BedrockAgentCoreRuntime(this, "SlackBotAgent", {
  envProps,
  agentRuntimeName: "slack_bot_agent",
  containerDirectory: "src/lambda/agentcore-strands",
  modelArns: [
    `arn:aws:bedrock:${this.region}::foundation-model/amazon.nova-micro-v1:0`,
    `arn:aws:bedrock:${this.region}::foundation-model/us.anthropic.claude-sonnet-4.5`,
  ],
});
```

### 3-7. Step Functions 更新（AWS SDK 統合）

**lib/stacks/stateless.ts**:
```typescript
import * as tasks from "aws-cdk-lib/aws-stepfunctions-tasks";
import * as sfn from "aws-cdk-lib/aws-stepfunctions";

// Step Functions State Machine
const stateMachine = new sfn.StateMachine(this, "SlackBotStateMachine", {
  stateMachineName: `${envProps.product_id}-${envProps.stage}-slack-bot`,
  definitionBody: sfn.DefinitionBody.fromChainable(
    // Task 1: Invoke AgentCore Runtime (AWS SDK 統合)
    new tasks.CallAwsService(this, "InvokeAgent", {
      service: "bedrockagentruntime",
      action: "invokeAgent",
      parameters: {
        AgentId: agentCoreRuntime.runtimeId,
        AgentAliasId: agentCoreRuntime.endpointArn ?
          // Endpoint がある場合はそのエイリアス ID を使用
          cdk.Fn.select(1, cdk.Fn.split("/", agentCoreRuntime.endpointArn)) :
          "TSTALIASID", // デフォルトテストエイリアス
        SessionId: sfn.JsonPath.stringAt("$.thread_ts"),
        InputText: sfn.JsonPath.stringAt("$.text"),
        // メタデータを JSON 文字列として渡す
        SessionState: {
          SessionAttributes: {
            "team_id": sfn.JsonPath.stringAt("$.team_id"),
            "channel_id": sfn.JsonPath.stringAt("$.channel_id"),
            "user_id": sfn.JsonPath.stringAt("$.user_id"),
            "is_mentioned": sfn.JsonPath.stringAt("States.Format('{}', $.is_mentioned)"),
            "is_dm": sfn.JsonPath.stringAt("States.Format('{}', $.is_dm)"),
            "channel_kind": sfn.JsonPath.stringAt("$.channel_kind"),
            "memory_id": memoryId,
          },
        },
      },
      iamResources: [agentCoreRuntime.runtimeArn],
      resultPath: "$.agentResult",
    })
    // Task 2: Post to Slack
    .next(new tasks.LambdaInvoke(this, "PostToSlack", {
      lambdaFunction: postToSlackLambda,
      payloadResponseOnly: true,
    }))
  ),
});

// Ingress Lambda に Step Functions 実行権限を付与
stateMachine.grantStartExecution(ingressLambda);
```

**注意**: AgentCore Runtime の API 仕様により、`invokeAgent` のレスポンス形式が異なる場合があります。実際のレスポンスを確認し、必要に応じて `PostToSlack` Lambda でパース処理を調整してください。

---

## Phase 4: AgentCore Memory 統合

### 4-1. Memory Resource 作成（CDK）

**lib/stacks/stateful.ts**:
```typescript
import * as agentcore from "@aws-cdk/aws-bedrock-agentcore-alpha";

// AgentCore Memory Resource
const memory = new agentcore.Memory(this, "SlackBotMemory", {
  memoryName: `${envProps.product_id}_${envProps.stage}_memory`,
  description: "Slack Bot memory for conversation context",
  expirationDuration: cdk.Duration.days(14), // STM 保持期間
  memoryStrategies: [
    // スレッド単位のサマリ保持
    agentcore.MemoryStrategy.usingBuiltInSummarization(),
    // チャンネルごとのトーン・好み・ルール
    agentcore.MemoryStrategy.usingBuiltInUserPreference(),
    // プロジェクト名・用語・チャンネルの意味
    agentcore.MemoryStrategy.usingBuiltInSemantic(),
  ],
});

// SSM パラメータストアに Memory ID を保存
new ssm.StringParameter(this, "AgentCoreMemoryId", {
  parameterName: genSsmName("agentCoreMemory.id", envProps),
  stringValue: memory.memoryId,
});
```

### 4-2. AgentCore Runtime に Memory 権限付与

**lib/stacks/stateless.ts**:
```typescript
// Memory ID を SSM から取得
const memoryId = ssm.StringParameter.fromStringParameterName(
  this, "GetMemoryId", genSsmName("agentCoreMemory.id", envProps)
).stringValue;

// AgentCore Runtime に環境変数として渡す
// ※ Docker イメージビルド時に環境変数は設定できないため、
//    Runtime 側で SSM から取得するか、Step Functions 経由で渡す
```

### 4-3. SessionManager 統合

**src/lambda/agentcore-strands/handler.py**:
```python
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager
)
from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig,
)

# Memory 設定
memory_config = AgentCoreMemoryConfig(
    memory_id=os.environ["AGENTCORE_MEMORY_ID"],
    session_id=thread_ts,  # スレッド単位
    actor_id=channel_id,   # チャンネル単位
    retrieval_config={
        "/preferences/{actorId}": RetrievalConfig(top_k=5, relevance_score=0.7),
        "/facts/{actorId}": RetrievalConfig(top_k=10, relevance_score=0.3),
    }
)

session_manager = AgentCoreMemorySessionManager(
    agentcore_memory_config=memory_config,
    region_name="ap-northeast-1"
)

graph = build_slack_graph(session_manager)
```

---

## Phase 5: チューニング・本番化

1. **プロンプト最適化**: Router/Conversation のプロンプト調整
2. **prod 環境デプロイ**: `STAGE=prod` でデプロイ
3. **モニタリング**: CloudWatch Logs, X-Ray トレーシング
4. **アラート**: エラー率、レイテンシ閾値

---

## 作成ファイル一覧

### CDK (TypeScript)
| ファイル | 説明 |
|---------|------|
| `bin/cdk-app.ts` | CDK エントリーポイント |
| `lib/constructs/utility.ts` | EnvProps, ユーティリティ |
| `lib/constructs/lambda.ts` | Python Lambda コンストラクト |
| `lib/constructs/apigateway.ts` | HTTP API コンストラクト |
| `lib/constructs/bedrock-agentcore-runtime.ts` | AgentCore コンストラクト |
| `lib/stacks/stateful.ts` | Secrets Manager |
| `lib/stacks/stateless.ts` | Lambda, API GW, Step Functions, AgentCore |

### Lambda (Python)
| ファイル | 説明 |
|---------|------|
| `src/lambda/ingress/handler.py` | Ingress Lambda |
| `src/lambda/ingress/pyproject.toml` | 依存管理 |
| `src/lambda/post-to-slack/handler.py` | Slack Posting Lambda |
| `src/lambda/post-to-slack/pyproject.toml` | 依存管理 |
| `src/lambda/agentcore-strands/handler.py` | AgentCore Handler |
| `src/lambda/agentcore-strands/graph.py` | Strands Graph |
| `src/lambda/agentcore-strands/agents/router_agent.py` | Router Agent |
| `src/lambda/agentcore-strands/agents/conversation_agent.py` | Conversation Agent |
| `src/lambda/agentcore-strands/Dockerfile` | AgentCore 用 Dockerfile |
| `src/lambda/agentcore-strands/requirements.txt` | 依存管理 |

### テスト
| ファイル | 説明 |
|---------|------|
| `test/unit/stacks/stateless.test.ts` | CDK スナップショットテスト |
| `src/lambda/ingress/tests/test_handler.py` | Ingress Lambda 単体テスト |
| `src/lambda/post-to-slack/tests/test_handler.py` | Posting Lambda 単体テスト |

### 設定
| ファイル | 説明 |
|---------|------|
| `package.json` | npm 依存管理 |
| `cdk.json` | CDK 設定 |
| `tsconfig.json` | TypeScript 設定 |
| `pyproject.toml` | Python 依存管理（ルート） |
| `.env` | 環境変数 |
| `.envrc` | direnv 設定 |

---

## 参考リソース

- 設計書: `docs/slack-strands-agentcore-architecture.md`
- 参考実装: `docs/*.py`, `docs/state_machine_definition.json`
- CDK テンプレート: https://github.com/heptagon-inc/template-cdk-typescript
- AgentCore コンストラクト: `lib/constructs/bedrock-agentcore-runtime.ts`
