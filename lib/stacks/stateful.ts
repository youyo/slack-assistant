import * as cdk from "aws-cdk-lib";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";
import { EnvProps, genSsmName, genStackName } from "../constructs/utility";

/**
 * Stateful スタックのプロパティ
 */
export interface StatefulStackProps extends cdk.StackProps {
  envProps: EnvProps;
}

/**
 * Stateful スタック
 *
 * ステートフルなリソース（削除しにくいもの）を管理:
 * - Secrets Manager シークレット
 * - AgentCore Memory（将来）
 */
export class StatefulStack extends cdk.Stack {
  public readonly slackBotTokenSecret: secretsmanager.ISecret;
  public readonly slackSigningSecretSecret: secretsmanager.ISecret;
  public readonly slackBotUserIdSecret: secretsmanager.ISecret;

  constructor(scope: Construct, id: string, props: StatefulStackProps) {
    super(scope, id, {
      ...props,
      stackName: genStackName("stateful", props.envProps),
    });

    const { envProps } = props;

    // Slack Bot Token シークレット（手動で値を設定）
    this.slackBotTokenSecret = new secretsmanager.Secret(
      this,
      "SlackBotTokenSecret",
      {
        secretName: `${envProps.product_id}/${envProps.stage}/slack-bot-token`,
        description: "Slack Bot Token (xoxb-...)",
      }
    );

    // Slack Signing Secret シークレット（手動で値を設定）
    this.slackSigningSecretSecret = new secretsmanager.Secret(
      this,
      "SlackSigningSecretSecret",
      {
        secretName: `${envProps.product_id}/${envProps.stage}/slack-signing-secret`,
        description: "Slack Signing Secret",
      }
    );

    // Slack Bot User ID シークレット（手動で値を設定）
    this.slackBotUserIdSecret = new secretsmanager.Secret(
      this,
      "SlackBotUserIdSecret",
      {
        secretName: `${envProps.product_id}/${envProps.stage}/slack-bot-user-id`,
        description: "Slack Bot User ID (U...)",
      }
    );

    // SSM パラメータストアにシークレット ARN を保存
    new ssm.StringParameter(this, "SlackBotTokenSecretArn", {
      parameterName: genSsmName("secrets.slackBotToken.arn", envProps),
      stringValue: this.slackBotTokenSecret.secretArn,
    });

    new ssm.StringParameter(this, "SlackSigningSecretSecretArn", {
      parameterName: genSsmName("secrets.slackSigningSecret.arn", envProps),
      stringValue: this.slackSigningSecretSecret.secretArn,
    });

    new ssm.StringParameter(this, "SlackBotUserIdSecretArn", {
      parameterName: genSsmName("secrets.slackBotUserId.arn", envProps),
      stringValue: this.slackBotUserIdSecret.secretArn,
    });

    // 出力
    new cdk.CfnOutput(this, "SlackBotTokenSecretArnOutput", {
      value: this.slackBotTokenSecret.secretArn,
      description: "Slack Bot Token Secret ARN",
    });

    new cdk.CfnOutput(this, "SlackSigningSecretArnOutput", {
      value: this.slackSigningSecretSecret.secretArn,
      description: "Slack Signing Secret ARN",
    });

    new cdk.CfnOutput(this, "SlackBotUserIdSecretArnOutput", {
      value: this.slackBotUserIdSecret.secretArn,
      description: "Slack Bot User ID Secret ARN",
    });
  }
}
