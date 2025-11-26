import * as cdk from "aws-cdk-lib";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as sfn from "aws-cdk-lib/aws-stepfunctions";
import * as tasks from "aws-cdk-lib/aws-stepfunctions-tasks";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
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

    // Secrets Manager からシークレットを参照
    const slackBotTokenSecretArn = ssm.StringParameter.valueForStringParameter(
      this,
      genSsmName("secrets.slackBotToken.arn", envProps)
    );
    const slackSigningSecretArn = ssm.StringParameter.valueForStringParameter(
      this,
      genSsmName("secrets.slackSigningSecret.arn", envProps)
    );
    const slackBotUserIdSecretArn = ssm.StringParameter.valueForStringParameter(
      this,
      genSsmName("secrets.slackBotUserId.arn", envProps)
    );

    const slackBotTokenSecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      "SlackBotTokenSecret",
      slackBotTokenSecretArn
    );
    const slackSigningSecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      "SlackSigningSecret",
      slackSigningSecretArn
    );
    const slackBotUserIdSecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      "SlackBotUserIdSecret",
      slackBotUserIdSecretArn
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
          SLACK_BOT_TOKEN_SECRET_ARN: slackBotTokenSecretArn,
        },
        timeout: cdk.Duration.seconds(30),
      }
    );
    slackBotTokenSecret.grantRead(postToSlackLambda.function);

    // Step Functions State Machine
    // Phase 2: ダミー実装（AgentCore 統合前）
    const invokeAgentDummy = new sfn.Pass(this, "InvokeAgentDummy", {
      result: sfn.Result.fromObject({
        should_reply: true,
        route: "full_reply",
        reply_mode: "thread",
        typing_style: "short",
        reply_text: "(dummy) メッセージを受け取りました",
        reason: "ダミー応答",
      }),
      resultPath: "$.agentResult",
    });

    const postToSlackTask = new tasks.LambdaInvoke(this, "PostToSlack", {
      lambdaFunction: postToSlackLambda.function,
      payloadResponseOnly: true,
    });

    this.stateMachine = new sfn.StateMachine(this, "SlackBotStateMachine", {
      stateMachineName: genResourceName("slack-bot", envProps),
      definitionBody: sfn.DefinitionBody.fromChainable(
        invokeAgentDummy.next(postToSlackTask)
      ),
      tracingEnabled: true,
    });

    // Ingress Lambda
    const ingressLambda = new LambdaPythonFunction(this, "IngressLambda", {
      envProps,
      functionName: "ingress",
      entry: "src/lambda/ingress",
      environment: {
        SLACK_SIGNING_SECRET_ARN: slackSigningSecretArn,
        SLACK_BOT_USER_ID_SECRET_ARN: slackBotUserIdSecretArn,
        STEP_FUNCTION_ARN: this.stateMachine.stateMachineArn,
      },
      timeout: cdk.Duration.seconds(10),
    });
    slackSigningSecret.grantRead(ingressLambda.function);
    slackBotUserIdSecret.grantRead(ingressLambda.function);
    this.stateMachine.grantStartExecution(ingressLambda.function);

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
  }
}
