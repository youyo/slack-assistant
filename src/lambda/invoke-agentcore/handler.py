"""
AgentCore Runtime Invoker Lambda

Step FunctionsからAgentCore Runtime APIを呼び出すラッパー。
Step Functions SDK統合がbedrockagentcoreruntimeサービスを
サポートしていないため、Lambda経由で呼び出す。
"""

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    AgentCore Runtime APIを呼び出し、結果を返す。

    入力 (Step Functionsから):
    {
        "text": "ユーザーメッセージ",
        "thread_ts": "1234567890.123456",
        "team_id": "...",
        "channel_id": "...",
        "user_id": "...",
        "is_mentioned": true,
        "is_dm": false,
        "channel_kind": "public",
        "ts": "..."
    }

    出力:
    元のeventに agentResult を追加した形式
    """
    logger.info(f"Received event: {json.dumps(event)}")

    agent_runtime_arn = os.environ["AGENT_RUNTIME_ARN"]

    # AgentCoreクライアント初期化
    client = boto3.client("bedrock-agentcore")

    # ペイロード構築（AgentCore handlerが期待する形式）
    payload = {
        "prompt": event.get("text", ""),
        "metadata": {
            "slack": {
                "team_id": event.get("team_id"),
                "channel_id": event.get("channel_id"),
                "user_id": event.get("user_id"),
                "is_mentioned": event.get("is_mentioned"),
                "is_dm": event.get("is_dm"),
                "channel_kind": event.get("channel_kind"),
                "ts": event.get("ts"),
                "thread_ts": event.get("thread_ts"),
            }
        },
    }

    try:
        # AgentCore Runtime呼び出し
        response = client.invoke_agent_runtime(
            agentRuntimeArn=agent_runtime_arn,
            runtimeSessionId=event.get("thread_ts", "default-session"),
            payload=json.dumps(payload).encode(),
        )

        # レスポンス処理
        agent_result = _process_response(response)

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        logger.error(f"AgentCore error: {error_code} - {error_message}")

        agent_result = {
            "should_reply": False,
            "reason": f"AgentCore error: {error_code}",
        }

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        agent_result = {
            "should_reply": False,
            "reason": f"Unexpected error: {type(e).__name__}",
        }

    # 元のeventにagentResultを追加して返す
    result = {**event, "agentResult": agent_result}
    logger.info(f"Returning result: {json.dumps(result)}")
    return result


def _process_response(response: dict[str, Any]) -> dict[str, Any]:
    """AgentCore Runtimeのレスポンスを処理"""
    content_type = response.get("contentType", "")
    logger.info(f"Response content type: {content_type}")

    if "text/event-stream" in content_type:
        # ストリーミングレスポンスを処理
        content = []
        for line in response["response"].iter_lines(chunk_size=10):
            if line:
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    content.append(line_str[6:])

        # 最後のチャンクがJSON結果であることを期待
        if content:
            try:
                return json.loads(content[-1])
            except json.JSONDecodeError:
                # JSON以外の場合はテキストとして返す
                return {
                    "should_reply": True,
                    "reply_text": "\n".join(content),
                    "route": "full_reply",
                    "reply_mode": "thread",
                    "typing_style": "none",
                    "reason": "Non-JSON streaming response",
                }

    elif content_type == "application/json":
        # 標準JSONレスポンス
        chunks = []
        for chunk in response.get("response", []):
            if isinstance(chunk, bytes):
                chunks.append(chunk.decode("utf-8"))
            else:
                chunks.append(str(chunk))
        return json.loads("".join(chunks))

    else:
        logger.warning(f"Unknown content type: {content_type}")
        return {
            "should_reply": False,
            "reason": f"Unknown response format: {content_type}",
        }
