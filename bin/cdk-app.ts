#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import * as dotenv from "dotenv";
import { EnvProps } from "../lib/constructs/utility";
import { StatefulStack } from "../lib/stacks/stateful";
import { StatelessStack } from "../lib/stacks/stateless";

// 環境変数を読み込み
dotenv.config();

// CDK アプリケーション
const app = new cdk.App();

// 環境プロパティ（.envからPRODUCT_ID、コンテキストからstage/version）
const envProps: EnvProps = {
  product_id: process.env.PRODUCT_ID as string,
  layer: "infra",
  stage: app.node.tryGetContext("stage"),
  version: app.node.tryGetContext("version"),
};

// AWS 環境設定
const env: cdk.Environment = {
  account: process.env.CDK_DEFAULT_ACCOUNT || process.env.AWS_ACCOUNT_ID,
  region: process.env.CDK_DEFAULT_REGION || "ap-northeast-1",
};

// Stateful スタック（Secrets Manager など）
const statefulStack = new StatefulStack(app, "StatefulStack", {
  envProps,
  env,
  description: `${envProps.product_id} Stateful resources (Secrets Manager)`,
});

// Stateless スタック（Lambda, API Gateway, Step Functions）
const statelessStack = new StatelessStack(app, "StatelessStack", {
  envProps,
  env,
  description: `${envProps.product_id} Stateless resources (Lambda, API Gateway, Step Functions)`,
});

// Stateless は Stateful に依存
statelessStack.addDependency(statefulStack);

// タグ付け
cdk.Tags.of(app).add("Product", envProps.product_id);
cdk.Tags.of(app).add("Stage", envProps.stage);
cdk.Tags.of(app).add("Version", envProps.version);
cdk.Tags.of(app).add("ManagedBy", "CDK");
