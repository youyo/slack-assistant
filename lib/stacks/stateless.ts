import * as cdk from "aws-cdk-lib";
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as sfn from "aws-cdk-lib/aws-stepfunctions";
import * as tasks from "aws-cdk-lib/aws-stepfunctions-tasks";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as iam from "aws-cdk-lib/aws-iam";
import * as agentcore from "@aws-cdk/aws-bedrock-agentcore-alpha";
import * as path from "path";
import { Construct } from "constructs";
import {
  EnvProps,
  genSsmName,
  genStackName,
  genResourceName,
} from "../constructs/utility";
import { LambdaPythonFunction } from "../constructs/lambda";
import { HttpApi } from "../constructs/apigateway";

/**
 * Stateless スタックのプロパティ
 */
export interface StatelessStackProps extends cdk.StackProps {
  envProps: EnvProps;
}

/**
 * Stateless スタック
 *
 * ステートレスなリソースを管理:
 * - Lambda 関数
 * - API Gateway
 * - Step Functions
 */
export class StatelessStack extends cdk.Stack {
  public readonly api: HttpApi;
  public readonly stateMachine: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: StatelessStackProps) {
    super(scope, id, {
      ...props,
      stackName: genStackName("stateless", props.envProps),
    });

    const { envProps } = props;

    // AgentCore Memory ID（Stateful スタックで作成）
    const agentcoreMemoryId = ssm.StringParameter.valueForStringParameter(
      this,
      genSsmName("agentcore-memory-id", envProps)
    );

    // ========================================
    // AgentCore Runtime
    // ========================================
    // Strands Graph を使用した AI エージェント
    const agentRuntimeArtifact = agentcore.AgentRuntimeArtifact.fromAsset(
      path.join(__dirname, "../../src/lambda/agentcore-strands")
    );

    const agentRuntime = new agentcore.Runtime(this, "SlackBotAgentRuntime", {
      runtimeName: genResourceName("slack_bot_agent", envProps).replace(
        /-/g,
        "_"
      ),
      agentRuntimeArtifact,
      environmentVariables: {
        AGENTCORE_MEMORY_ID: agentcoreMemoryId,
        AWS_REGION: cdk.Stack.of(this).region,
        // モデル ID（Global Inference Profile形式）
        ROUTER_MODEL_ID: "global.amazon.nova-2-lite-v1:0",
        CONVERSATION_MODEL_ID: "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
        // 更新トリガー用タイムスタンプ
        CONFIG_VERSION: "2025-12-29-v9-prefilter-short-messages",
      },
    });

    // AgentCore Runtime に Bedrock モデル呼び出し権限を付与
    // Global Inference Profile と foundation-model の両方を許可
    // （Strands SDKが内部でfoundation-modelとして呼び出す場合があるため）
    agentRuntime.grantPrincipal.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        resources: [
          // Global Inference Profile
          "arn:aws:bedrock:*:*:inference-profile/global.amazon.nova-2-lite-v1:0",
          "arn:aws:bedrock:*:*:inference-profile/global.anthropic.claude-sonnet-4-5-*",
          // Foundation Model（SDKが内部で使用する場合）
          "arn:aws:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0",
          "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-*",
        ],
      })
    );

    // AgentCore Memory へのアクセス権限を付与
    agentRuntime.grantPrincipal.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          "bedrock-agentcore:ListEvents",
          "bedrock-agentcore:CreateEvent",
          "bedrock-agentcore:GetEvent",
          "bedrock-agentcore:ListSessions",
          "bedrock-agentcore:CreateSession",
          "bedrock-agentcore:GetSession",
          "bedrock-agentcore:RetrieveMemoryRecords",
        ],
        resources: [
          `arn:aws:bedrock-agentcore:${cdk.Stack.of(this).region}:${cdk.Stack.of(this).account}:memory/*`,
        ],
      })
    );

    // Slack Posting Lambda
    const postToSlackLambda = new LambdaPythonFunction(
      this,
      "PostToSlackLambda",
      {
        envProps,
        functionName: "post-to-slack",
        entry: "src/lambda/post-to-slack",
        environment: {
          // SSM パラメータ名を渡す（Lambda実行時に動的取得）
          SSM_SLACK_BOT_TOKEN: genSsmName("slack-bot-token", envProps),
        },
        timeout: cdk.Duration.seconds(30),
      }
    );

    // SSM Parameter Store 読み取り権限
    postToSlackLambda.function.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["ssm:GetParameter"],
        resources: [
          `arn:aws:ssm:${cdk.Stack.of(this).region}:${cdk.Stack.of(this).account}:parameter${genSsmName("slack-bot-token", envProps)}`,
        ],
      })
    );

    // ========================================
    // Step Functions State Machine
    // ========================================
    // AgentCore Invoker Lambda
    // Note: Step Functions SDK統合がbedrockagentcoreruntimeを
    // サポートしていないため、Lambda経由で呼び出す
    const invokeAgentCoreLambda = new LambdaPythonFunction(
      this,
      "InvokeAgentCoreLambda",
      {
        envProps,
        functionName: "invoke-agentcore",
        entry: "src/lambda/invoke-agentcore",
        environment: {
          AGENT_RUNTIME_ARN: agentRuntime.agentRuntimeArn,
        },
        timeout: cdk.Duration.seconds(120),
      }
    );

    // AgentCore Runtime呼び出し権限を付与
    agentRuntime.grantInvokeRuntime(invokeAgentCoreLambda.function);

    // Step Functions タスク
    const invokeAgentTask = new tasks.LambdaInvoke(this, "InvokeAgent", {
      lambdaFunction: invokeAgentCoreLambda.function,
      payloadResponseOnly: true,
    });

    const postToSlackTask = new tasks.LambdaInvoke(this, "PostToSlack", {
      lambdaFunction: postToSlackLambda.function,
      payloadResponseOnly: true,
    });

    this.stateMachine = new sfn.StateMachine(this, "SlackBotStateMachine", {
      stateMachineName: genResourceName("slack-bot", envProps),
      definitionBody: sfn.DefinitionBody.fromChainable(
        invokeAgentTask.next(postToSlackTask)
      ),
      tracingEnabled: true,
    });

    // Ingress Lambda
    const ingressLambda = new LambdaPythonFunction(this, "IngressLambda", {
      envProps,
      functionName: "ingress",
      entry: "src/lambda/ingress",
      environment: {
        // SSM パラメータ名を渡す（Lambda実行時に動的取得）
        SSM_SLACK_SIGNING_SECRET: genSsmName("slack-signing-secret", envProps),
        SSM_SLACK_BOT_USER_ID: genSsmName("slack-bot-user-id", envProps),
        STEP_FUNCTION_ARN: this.stateMachine.stateMachineArn,
      },
      timeout: cdk.Duration.seconds(10),
    });
    this.stateMachine.grantStartExecution(ingressLambda.function);

    // SSM Parameter Store 読み取り権限
    ingressLambda.function.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["ssm:GetParameter"],
        resources: [
          `arn:aws:ssm:${cdk.Stack.of(this).region}:${cdk.Stack.of(this).account}:parameter${genSsmName("slack-signing-secret", envProps)}`,
          `arn:aws:ssm:${cdk.Stack.of(this).region}:${cdk.Stack.of(this).account}:parameter${genSsmName("slack-bot-user-id", envProps)}`,
        ],
      })
    );

    // API Gateway HTTP API
    this.api = new HttpApi(this, "SlackEventsApi", {
      envProps,
      apiName: "slack-events",
    });
    this.api.addPostRoute("/slack/events", ingressLambda.function);

    // SSM パラメータストアに API Gateway URL を保存
    new ssm.StringParameter(this, "ApiGatewayUrl", {
      parameterName: genSsmName("apigateway.url", envProps),
      stringValue: this.api.api.apiEndpoint,
    });

    // 出力
    new cdk.CfnOutput(this, "SlackEventsEndpoint", {
      value: `${this.api.api.apiEndpoint}/slack/events`,
      description: "Slack Events API endpoint URL",
    });

    new cdk.CfnOutput(this, "StateMachineArn", {
      value: this.stateMachine.stateMachineArn,
      description: "Step Functions State Machine ARN",
    });

    new cdk.CfnOutput(this, "AgentRuntimeArn", {
      value: agentRuntime.agentRuntimeArn,
      description: "AgentCore Runtime ARN",
    });
  }
}
