/**
 * 環境プロパティ定義
 */
export interface EnvProps {
  /** プロダクト ID (例: slack-assistant) */
  product_id: string;
  /** レイヤー名 (例: infra) */
  layer: string;
  /** ステージ名 (例: dev, prod) */
  stage: string;
  /** バージョン (例: v1) */
  version: string;
}

/**
 * SSM パラメータ名を生成する
 * @param name パラメータ名
 * @param envProps 環境プロパティ
 * @returns SSM パラメータ名 (例: /slack-assistant/dev/parameterName)
 */
export function genSsmName(name: string, envProps: EnvProps): string {
  return `/${envProps.product_id}/${envProps.stage}/${name}`;
}

/**
 * リソース名を生成する
 * @param name リソース名
 * @param envProps 環境プロパティ
 * @returns リソース名 (例: slack-assistant-dev-resourceName)
 */
export function genResourceName(name: string, envProps: EnvProps): string {
  return `${envProps.product_id}-${envProps.stage}-${name}`;
}

/**
 * スタック名を生成する
 * @param layer レイヤー名
 * @param envProps 環境プロパティ
 * @returns スタック名 (例: slack-assistant-infra-dev-v1)
 */
export function genStackName(layer: string, envProps: EnvProps): string {
  return `${envProps.product_id}-${layer}-${envProps.stage}-${envProps.version}`;
}
