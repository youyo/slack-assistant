import * as cdk from "aws-cdk-lib";
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as agentcore from "@aws-cdk/aws-bedrock-agentcore-alpha";
import { Construct } from "constructs";
import {
  EnvProps,
  genStackName,
  genResourceName,
  genSsmName,
} from "../constructs/utility";

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
 * - AgentCore Memory
 */
export class StatefulStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: StatefulStackProps) {
    super(scope, id, {
      ...props,
      stackName: genStackName("stateful", props.envProps),
    });

    const { envProps } = props;

    // ========================================
    // AgentCore Memory
    // ========================================
    // Slack Bot の会話履歴・コンテキストを保持するメモリ
    // Memory 名はアンダースコア形式が必要
    const memory = new agentcore.Memory(this, "SlackBotMemory", {
      memoryName: genResourceName("slack_bot_memory", envProps).replace(
        /-/g,
        "_"
      ),
      memoryStrategies: [
        // 会話の要約を自動生成
        agentcore.MemoryStrategy.usingBuiltInSummarization(),
        // ユーザーの好みを学習
        agentcore.MemoryStrategy.usingBuiltInUserPreference(),
        // セマンティック検索用のベクトル埋め込み
        agentcore.MemoryStrategy.usingBuiltInSemantic(),
      ],
    });

    // Memory ID を SSM Parameter Store に保存
    // Stateless スタックから参照するため
    new ssm.StringParameter(this, "AgentCoreMemoryIdParam", {
      parameterName: genSsmName("agentcore-memory-id", envProps),
      stringValue: memory.memoryId,
      description: "AgentCore Memory ID for Slack Bot",
    });

    // CloudFormation Output
    new cdk.CfnOutput(this, "MemoryId", {
      value: memory.memoryId,
      description: "AgentCore Memory ID",
    });
  }
}
