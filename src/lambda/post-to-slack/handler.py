"""
Slack Posting Lambda

役割:
- agentResult をパース
- should_reply / reply_mode / typing_style / reply_text に応じて Slack Web API を呼ぶ
"""

import json
import logging
import os
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def parse_agent_result(agent_result: dict[str, Any] | str) -> dict[str, Any]:
    """AgentCore の結果をパース"""
    if isinstance(agent_result, str):
        try:
            return json.loads(agent_result)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse agent_result as JSON: {agent_result}")
            return {
                "should_reply": True,
                "reply_mode": "thread",
                "reply_text": agent_result,
            }
    return agent_result


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda ハンドラー"""
    logger.info(f"Received event: {json.dumps(event)}")

    # イベントから必要な情報を取得
    channel_id = event.get("channel_id", "")
    thread_ts = event.get("thread_ts", "")
    agent_result = event.get("agentResult", {})

    # AgentCore の結果をパース
    result = parse_agent_result(agent_result)

    should_reply = result.get("should_reply", False)
    reply_mode = result.get("reply_mode", "thread")
    reply_text = result.get("reply_text", "")
    reason = result.get("reason", "")

    logger.info(
        f"Agent result: should_reply={should_reply}, "
        f"reply_mode={reply_mode}, reason={reason}"
    )

    # 返信不要の場合は何もしない
    if not should_reply:
        logger.info("should_reply is False, skipping Slack post")
        return {
            "statusCode": 200,
            "body": json.dumps({"posted": False, "reason": reason}),
        }

    # 返信テキストがない場合はスキップ
    if not reply_text:
        logger.warning("reply_text is empty, skipping Slack post")
        return {
            "statusCode": 200,
            "body": json.dumps({"posted": False, "reason": "empty reply_text"}),
        }

    # Slack クライアントを初期化（SSM から動的に取得）
    from ssm_params import get_slack_bot_token

    bot_token = get_slack_bot_token()
    slack_client = WebClient(token=bot_token)

    try:
        # Slack にメッセージを投稿
        if reply_mode == "thread" and thread_ts:
            # スレッドに返信
            response = slack_client.chat_postMessage(
                channel=channel_id,
                text=reply_text,
                thread_ts=thread_ts,
            )
        else:
            # チャンネルに投稿
            response = slack_client.chat_postMessage(
                channel=channel_id,
                text=reply_text,
            )

        logger.info(f"Posted message to Slack: {response['ts']}")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "posted": True,
                    "channel": channel_id,
                    "ts": response["ts"],
                    "thread_ts": thread_ts if reply_mode == "thread" else None,
                }
            ),
        }

    except SlackApiError as e:
        logger.error(f"Slack API error: {e.response['error']}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "posted": False,
                    "error": e.response["error"],
                }
            ),
        }
