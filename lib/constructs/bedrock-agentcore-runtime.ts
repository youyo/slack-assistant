import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import { Construct } from "constructs";
import { EnvProps, genResourceName } from "./utility";

/**
 * Bedrock AgentCore Runtime のプロパティ
 */
export interface BedrockAgentCoreRuntimeProps {
  /** 環境プロパティ */
  envProps: EnvProps;
  /** Agent Runtime 名 */
  agentRuntimeName: string;
  /** コンテナディレクトリパス */
  containerDirectory: string;
  /** 使用するモデルの ARN 一覧 */
  modelArns: string[];
  /** 環境変数 */
  environment?: { [key: string]: string };
  /** タイムアウト（秒） */
  timeoutSeconds?: number;
  /** メモリサイズ（MB） */
  memoryMb?: number;
}

/**
 * Bedrock AgentCore Runtime コンストラクト
 *
 * 注意: 2025年11月現在、CDK で AgentCore Runtime をネイティブサポートする
 * L2/L1 コンストラクトは未提供のため、このコンストラクトは
 * カスタムリソースまたは手動デプロイのプレースホルダとして機能します。
 *
 * 実際のデプロイは以下のいずれかで行います:
 * 1. AgentCore CLI (`agentcore deploy`)
 * 2. CloudFormation カスタムリソース
 * 3. CDK で ECR イメージをビルドし、手動で AgentCore にデプロイ
 */
export class BedrockAgentCoreRuntime extends Construct {
  public readonly runtimeName: string;
  public readonly runtimeId: string;
  public readonly runtimeArn: string;
  public readonly endpointArn?: string;
  public readonly role: iam.IRole;
  public readonly containerImage: ecr_assets.DockerImageAsset;

  constructor(
    scope: Construct,
    id: string,
    props: BedrockAgentCoreRuntimeProps
  ) {
    super(scope, id);

    this.runtimeName = genResourceName(
      props.agentRuntimeName,
      props.envProps
    );

    // コンテナイメージをビルド
    this.containerImage = new ecr_assets.DockerImageAsset(this, "Image", {
      directory: props.containerDirectory,
    });

    // AgentCore Runtime 用の IAM ロール
    this.role = new iam.Role(this, "Role", {
      roleName: `${this.runtimeName}-role`,
      assumedBy: new iam.ServicePrincipal("bedrock.amazonaws.com"),
    });

    // Bedrock モデル呼び出し権限
    for (const modelArn of props.modelArns) {
      this.role.addToPrincipalPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
          resources: [modelArn],
        })
      );
    }

    // CloudWatch Logs 権限
    this.role.addToPrincipalPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        resources: ["*"],
      })
    );

    // ロググループ
    new logs.LogGroup(this, "LogGroup", {
      logGroupName: `/aws/agentcore/${this.runtimeName}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // プレースホルダ: 実際の AgentCore Runtime ID/ARN は
    // デプロイ後に SSM パラメータストアから取得するか、
    // カスタムリソースで設定します
    this.runtimeId = "PLACEHOLDER_RUNTIME_ID";
    this.runtimeArn = `arn:aws:bedrock:${cdk.Stack.of(this).region}:${cdk.Stack.of(this).account}:agent-runtime/${this.runtimeId}`;

    // 出力: デプロイ後に AgentCore CLI で使用
    new cdk.CfnOutput(this, "ContainerImageUri", {
      value: this.containerImage.imageUri,
      description: "AgentCore Runtime container image URI",
    });

    new cdk.CfnOutput(this, "RoleArn", {
      value: this.role.roleArn,
      description: "AgentCore Runtime IAM role ARN",
    });
  }

  /**
   * Memory リソースへのアクセス権限を付与
   */
  public grantMemoryAccess(memoryArn: string): void {
    this.role.addToPrincipalPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "bedrock:RetrieveMemory",
          "bedrock:UpdateMemory",
          "bedrock:DeleteMemory",
        ],
        resources: [memoryArn],
      })
    );
  }
}
