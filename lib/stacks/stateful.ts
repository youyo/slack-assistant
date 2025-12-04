import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { EnvProps, genStackName } from "../constructs/utility";

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
 * - AgentCore Memory（将来）
 */
export class StatefulStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: StatefulStackProps) {
    super(scope, id, {
      ...props,
      stackName: genStackName("stateful", props.envProps),
    });

    // 将来の AgentCore Memory などステートフルリソースのために残す
  }
}
