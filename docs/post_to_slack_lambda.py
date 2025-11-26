import json
import logging
import os
from typing import Any, Dict

import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_API_BASE = "https://slack.com/api"


def _call_slack_api(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN is not set")

    url = f"{SLACK_API_BASE}/{method}"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=5)
    try:
        data = resp.json()
    except Exception:
        logger.exception("Failed to parse Slack response JSON")
        raise

    if not data.get("ok"):
        logger.error("Slack API error for %s: %s", method, data)
    return data


def lambda_handler(event, context):
    \"\"\"Post the agent's response to Slack.

    Expected `event`:

    {
      "team_id": "...",
      "channel_id": "...",
      "thread_ts": "...",
      "agentResult": {
        "reply": "{...}"  # or already-parsed dict
      }
    }
    \"\"\"
    logger.info("PostToSlack event: %s", json.dumps(event))

    channel_id = event.get("channel_id")
    thread_ts = event.get("thread_ts")
    agent_result = event.get("agentResult") or {}

    # AgentCore Runtime might nest the actual payload; adapt as needed.
    # We accept both a JSON string and a dict.
    reply_payload = agent_result.get("reply") or agent_result
    if isinstance(reply_payload, str):
        try:
            reply_payload = json.loads(reply_payload)
        except json.JSONDecodeError:
            logger.exception("Failed to decode agent reply JSON")
            return {"statusCode": 500, "body": "invalid agent reply"}

    logger.info("Agent reply payload: %s", json.dumps(reply_payload))

    should_reply = reply_payload.get("should_reply", False)
    if not should_reply:
        logger.info("Agent decided not to reply; exiting")
        return {"statusCode": 200, "body": ""}

    reply_mode = reply_payload.get("reply_mode", "thread")
    text = reply_payload.get("reply_text") or ""
    typing_style = reply_payload.get("typing_style", "none")

    if not channel_id:
        logger.error("Missing channel_id in event")
        return {"statusCode": 500, "body": "missing channel_id"}

    if not text:
        logger.warning("Agent reply_text is empty")

    post_args: Dict[str, Any] = {
        "channel": channel_id,
        "text": text,
    }

    if reply_mode == "thread" and thread_ts:
        post_args["thread_ts"] = thread_ts

    # typing_style could be used to post a placeholder message earlier and update it here.
    # For now we simply post a single message.
    logger.info("Posting message to Slack: %s", json.dumps(post_args))
    _call_slack_api("chat.postMessage", post_args)

    return {"statusCode": 200, "body": ""}
