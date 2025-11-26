import * as cdk from "aws-cdk-lib";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as apigwv2Integrations from "aws-cdk-lib/aws-apigatewayv2-integrations";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { Construct } from "constructs";
import { EnvProps, genResourceName } from "./utility";

/**
 * HTTP API のプロパティ
 */
export interface HttpApiProps {
  /** 環境プロパティ */
  envProps: EnvProps;
  /** API 名（リソース名のサフィックス） */
  apiName: string;
  /** CORS 設定を有効にするか */
  enableCors?: boolean;
}

/**
 * HTTP API コンストラクト
 */
export class HttpApi extends Construct {
  public readonly api: apigwv2.HttpApi;

  constructor(scope: Construct, id: string, props: HttpApiProps) {
    super(scope, id);

    const fullApiName = genResourceName(props.apiName, props.envProps);

    this.api = new apigwv2.HttpApi(this, "Api", {
      apiName: fullApiName,
      corsPreflight: props.enableCors
        ? {
            allowOrigins: ["*"],
            allowMethods: [apigwv2.CorsHttpMethod.ANY],
            allowHeaders: ["*"],
          }
        : undefined,
    });

    new cdk.CfnOutput(this, "ApiUrl", {
      value: this.api.apiEndpoint,
      description: `${fullApiName} HTTP API URL`,
    });
  }

  /**
   * Lambda 統合のルートを追加
   * @param path パス (例: /slack/events)
   * @param method HTTP メソッド
   * @param handler Lambda 関数
   */
  public addLambdaRoute(
    path: string,
    method: apigwv2.HttpMethod,
    handler: lambda.IFunction
  ): void {
    const integration = new apigwv2Integrations.HttpLambdaIntegration(
      `Integration-${path.replace(/\//g, "-")}`,
      handler
    );

    this.api.addRoutes({
      path,
      methods: [method],
      integration,
    });
  }

  /**
   * POST メソッドの Lambda 統合ルートを追加
   */
  public addPostRoute(path: string, handler: lambda.IFunction): void {
    this.addLambdaRoute(path, apigwv2.HttpMethod.POST, handler);
  }
}
