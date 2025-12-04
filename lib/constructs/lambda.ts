import * as cdk from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as lambdaPython from "@aws-cdk/aws-lambda-python-alpha";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import { EnvProps, genResourceName } from "./utility";

/**
 * Python Lambda 関数のプロパティ
 */
export interface LambdaPythonFunctionProps {
  /** 環境プロパティ */
  envProps: EnvProps;
  /** Lambda 関数名（リソース名のサフィックス） */
  functionName: string;
  /** Lambda 関数のエントリポイントディレクトリ */
  entry: string;
  /** エントリファイル名（デフォルト: handler.py） */
  index?: string;
  /** ハンドラ関数名（デフォルト: lambda_handler） */
  handler?: string;
  /** 環境変数 */
  environment?: { [key: string]: string };
  /** タイムアウト（デフォルト: 30秒） */
  timeout?: cdk.Duration;
  /** メモリサイズ（デフォルト: 256MB） */
  memorySize?: number;
  /** IAM ロール（指定しない場合は自動生成） */
  role?: iam.IRole;
  /** ログ保持期間（デフォルト: 14日） */
  logRetention?: logs.RetentionDays;
}

/**
 * Python Lambda 関数コンストラクト
 */
export class LambdaPythonFunction extends Construct {
  public readonly function: lambdaPython.PythonFunction;

  constructor(scope: Construct, id: string, props: LambdaPythonFunctionProps) {
    super(scope, id);

    const fullFunctionName = genResourceName(props.functionName, props.envProps);

    this.function = new lambdaPython.PythonFunction(this, "Function", {
      functionName: fullFunctionName,
      runtime: lambda.Runtime.PYTHON_3_13,
      entry: props.entry,
      index: props.index ?? "handler.py",
      handler: props.handler ?? "lambda_handler",
      environment: props.environment,
      timeout: props.timeout ?? cdk.Duration.seconds(30),
      memorySize: props.memorySize ?? 256,
      role: props.role,
      logRetention: props.logRetention ?? logs.RetentionDays.TWO_WEEKS,
      bundling: {
        assetExcludes: [
          ".venv",
          "__pycache__",
          ".pytest_cache",
          ".mypy_cache",
          "tests",
          "*.md",
        ],
        commandHooks: {
          beforeBundling(inputDir: string): string[] {
            return [
              "python -m pip install uv -t /tmp/",
              "/tmp/bin/uv pip compile pyproject.toml -o requirements.txt --no-cache",
            ];
          },
          afterBundling(inputDir: string): string[] {
            return [
              "/tmp/bin/uv pip install -r requirements.txt --target /asset-output --no-cache",
            ];
          },
        },
      },
    });
  }

  /**
   * Lambda 関数に IAM ポリシーステートメントを追加
   */
  public addToRolePolicy(statement: iam.PolicyStatement): void {
    this.function.addToRolePolicy(statement);
  }

  /**
   * 環境変数を追加
   */
  public addEnvironment(key: string, value: string): void {
    this.function.addEnvironment(key, value);
  }
}

/**
 * Docker Lambda 関数のプロパティ
 */
export interface LambdaDockerFunctionProps {
  /** 環境プロパティ */
  envProps: EnvProps;
  /** Lambda 関数名（リソース名のサフィックス） */
  functionName: string;
  /** Dockerfile が存在するディレクトリ */
  directory: string;
  /** 環境変数 */
  environment?: { [key: string]: string };
  /** タイムアウト（デフォルト: 60秒） */
  timeout?: cdk.Duration;
  /** メモリサイズ（デフォルト: 512MB） */
  memorySize?: number;
  /** IAM ロール（指定しない場合は自動生成） */
  role?: iam.IRole;
  /** ログ保持期間（デフォルト: 14日） */
  logRetention?: logs.RetentionDays;
}

/**
 * Docker Lambda 関数コンストラクト
 */
export class LambdaDockerFunction extends Construct {
  public readonly function: lambda.DockerImageFunction;

  constructor(scope: Construct, id: string, props: LambdaDockerFunctionProps) {
    super(scope, id);

    const fullFunctionName = genResourceName(props.functionName, props.envProps);

    this.function = new lambda.DockerImageFunction(this, "Function", {
      functionName: fullFunctionName,
      code: lambda.DockerImageCode.fromImageAsset(props.directory),
      environment: props.environment,
      timeout: props.timeout ?? cdk.Duration.seconds(60),
      memorySize: props.memorySize ?? 512,
      role: props.role,
      logRetention: props.logRetention ?? logs.RetentionDays.TWO_WEEKS,
    });
  }

  /**
   * Lambda 関数に IAM ポリシーステートメントを追加
   */
  public addToRolePolicy(statement: iam.PolicyStatement): void {
    this.function.addToRolePolicy(statement);
  }

  /**
   * 環境変数を追加
   */
  public addEnvironment(key: string, value: string): void {
    this.function.addEnvironment(key, value);
  }
}
