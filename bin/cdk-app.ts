#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import * as dotenv from "dotenv";
import { EnvProps } from "../lib/constructs/utility";
import { StatefulStack } from "../lib/stacks/stateful";
import { StatelessStack } from "../lib/stacks/stateless";

// 環境変数を読み込み
dotenv.config();

/**
 * 必須環境変数を取得
 */
function getRequiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`必須環境変数 ${name} が設定されていません`);
  }
  return value;
}

/**
 * 環境変数から EnvProps を生成
 */
function getEnvProps(): EnvProps {
  return {
    product_id: getRequiredEnv("PRODUCT_ID"),
    layer: "infra",
    stage: getRequiredEnv("STAGE"),
    version: getRequiredEnv("VERSION"),
  };
}

// CDK アプリケーション
const app = new cdk.App();

// 環境プロパティ
const envProps = getEnvProps();

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
