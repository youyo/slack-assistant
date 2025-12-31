"""
Slack Events API Ingress Lambda

役割:
- Slack の署名検証
- url_verification 応答
- event_callback 内のメッセージ系イベントを抽出
- bot 自身の発言などを除外
- 正規化したイベントを Step Functions に渡す
- Slack には常に速やかに 200 を返す（3 秒以内）
"""

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: str,
    signature: str,
) -> bool:
    """Slack のリクエスト署名を検証"""
    # タイムスタンプが古すぎないかチェック（5分以内）
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False

    # 署名を計算
    sig_basestring = f"v0:{timestamp}:{body}"
    computed_signature = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(computed_signature, signature)


def is_bot_message(event: dict[str, Any], bot_user_id: str) -> bool:
    """Bot 自身のメッセージかどうかを判定"""
    # bot_id が設定されている場合は bot のメッセージ
    if event.get("bot_id"):
        return True

    # user が bot_user_id と一致する場合
    if event.get("user") == bot_user_id:
        return True

    return False


def is_processable_event(event: dict[str, Any]) -> bool:
    """処理対象のイベントかどうかを判定"""
    event_type = event.get("type")

    # message イベントのみ対象
    if event_type != "message":
        return False

    # サブタイプがある場合は除外（編集、削除など）
    if event.get("subtype"):
        return False

    return True


def detect_channel_kind(channel_id: str) -> str:
    """チャンネル種別を判定"""
    if channel_id.startswith("C"):
        return "public"
    elif channel_id.startswith("G"):
        return "private"
    elif channel_id.startswith("D"):
        return "dm"
    else:
        return "unknown"


def normalize_event(event: dict[str, Any], bot_user_id: str) -> dict[str, Any]:
    """Slack イベントを正規化"""
    channel_id = event.get("channel", "")
    text = event.get("text", "")
    ts = event.get("ts", "")
    thread_ts = event.get("thread_ts", ts)  # スレッドでない場合は ts を使用

    # メンション判定
    is_mentioned = f"<@{bot_user_id}>" in text

    # DM 判定
    is_dm = channel_id.startswith("D")

    return {
        "team_id": event.get("team", ""),
        "channel_id": channel_id,
        "channel_kind": detect_channel_kind(channel_id),
        "user_id": event.get("user", ""),
        "text": text,
        "ts": ts,
        "thread_ts": thread_ts,
        "is_mentioned": is_mentioned,
        "is_dm": is_dm,
        "event_type": "message",
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda ハンドラー"""
    logger.info(f"Received event: {json.dumps(event)}")

    # リクエストボディを取得
    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")

    # ヘッダーを取得（小文字に正規化）
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    timestamp = headers.get("x-slack-request-timestamp", "")
    signature = headers.get("x-slack-signature", "")

    # SSM Parameter Store から動的に取得
    from ssm_params import get_slack_bot_user_id, get_slack_signing_secret

    signing_secret = get_slack_signing_secret()
    bot_user_id = get_slack_bot_user_id()

    # 署名検証
    if not verify_slack_signature(signing_secret, timestamp, body, signature):
        logger.warning("Invalid Slack signature")
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "Invalid signature"}),
        }

    # ボディをパース
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Failed to parse request body")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON"}),
        }

    # url_verification 応答
    if payload.get("type") == "url_verification":
        logger.info("Handling url_verification")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"challenge": payload.get("challenge")}),
        }

    # event_callback 処理
    if payload.get("type") == "event_callback":
        slack_event = payload.get("event", {})

        # 処理対象外のイベントはスキップ
        if not is_processable_event(slack_event):
            logger.info(f"Skipping non-processable event: {slack_event.get('type')}")
            return {
                "statusCode": 200,
                "body": json.dumps({"ok": True}),
            }

        # Bot 自身のメッセージはスキップ
        if is_bot_message(slack_event, bot_user_id):
            logger.info("Skipping bot's own message")
            return {
                "statusCode": 200,
                "body": json.dumps({"ok": True}),
            }

        # イベントを正規化
        normalized_event = normalize_event(slack_event, bot_user_id)
        normalized_event["team_id"] = payload.get("team_id", "")
        logger.info(f"Normalized event: {json.dumps(normalized_event)}")

        # Step Functions を開始
        step_function_arn = os.environ.get("STEP_FUNCTION_ARN", "")
        if step_function_arn:
            sfn_client = boto3.client("stepfunctions")
            execution_name = f"{normalized_event['channel_id']}-{normalized_event['ts'].replace('.', '-')}"
            sfn_client.start_execution(
                stateMachineArn=step_function_arn,
                name=execution_name,
                input=json.dumps(normalized_event),
            )
            logger.info(f"Started Step Functions execution: {execution_name}")

    # Slack には即座に 200 を返す
    return {
        "statusCode": 200,
        "body": json.dumps({"ok": True}),
    }
