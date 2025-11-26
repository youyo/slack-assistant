import base64
import hashlib
import hmac
import json
import logging
import os
import time

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sfn = boto3.client("stepfunctions")

SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
SLACK_BOT_USER_ID = os.environ.get("SLACK_BOT_USER_ID", "")
STEP_FUNCTION_ARN = os.environ.get("STEP_FUNCTION_ARN", "")


def _verify_slack_signature(event: dict) -> bool:
    \"\"\"Return True if the Slack signature is valid.

    Slack docs:
    https://api.slack.com/authentication/verifying-requests-from-slack
    \"\"\"
    if not SLACK_SIGNING_SECRET:
        logger.error("SLACK_SIGNING_SECRET is not set")
        return False

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    timestamp = headers.get("x-slack-request-timestamp")
    slack_sig = headers.get("x-slack-signature")

    if not timestamp or not slack_sig:
        logger.warning("Missing Slack signature headers")
        return False

    # Replay attack protection (5 minutes window).
    try:
        ts = int(timestamp)
    except ValueError:
        logger.warning("Invalid timestamp header")
        return False

    if abs(time.time() - ts) > 60 * 5:
        logger.warning("Timestamp too old; possible replay attack")
        return False

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    basestring = f"v0:{timestamp}:{body}".encode("utf-8")
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode("utf-8"),
        basestring,
        hashlib.sha256,
    ).hexdigest()

    valid = hmac.compare_digest(expected, slack_sig)
    if not valid:
        logger.warning("Slack signature mismatch")
    return valid


def _channel_kind(channel_id: str) -> str:
    if not channel_id:
        return "unknown"
    if channel_id.startswith("C"):
        return "public"
    if channel_id.startswith("G"):
        return "private"
    if channel_id.startswith("D"):
        return "dm"
    return "unknown"


def lambda_handler(event, context):
    \"\"\"Ingress Lambda for Slack Events API.

    Responsibilities:
    - Verify Slack signature
    - Handle url_verification
    - Normalize message events
    - Start Step Functions execution
    - Always return 200 quickly to Slack
    \"\"\\"\"  # noqa: E501
    logger.info("Event: %s", json.dumps(event))

    if not _verify_slack_signature(event):
        return {
            "statusCode": 401,
            "body": "invalid signature",
        }

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.exception("Failed to decode JSON body")
        return {"statusCode": 400, "body": "invalid json"}

    # Slack URL verification
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge", "")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/plain"},
            "body": challenge,
        }

    if payload.get("type") != "event_callback":
        # Just ACK other event types
        return {"statusCode": 200, "body": ""}

    event_data = payload.get("event") or {}

    # Ignore bot messages (including our own).
    if event_data.get("subtype") == "bot_message":
        return {"statusCode": 200, "body": ""}

    if SLACK_BOT_USER_ID and event_data.get("user") == SLACK_BOT_USER_ID:
        return {"statusCode": 200, "body": ""}

    # Only handle message events for now.
    if event_data.get("type") != "message":
        return {"statusCode": 200, "body": ""}

    team_id = payload.get("team_id")
    channel_id = event_data.get("channel")
    user_id = event_data.get("user")
    text = event_data.get("text") or ""
    ts = event_data.get("ts")
    thread_ts = event_data.get("thread_ts") or ts

    if not (team_id and channel_id and user_id and ts):
        logger.warning("Missing required fields in event: %s", event_data)
        return {"statusCode": 200, "body": ""}

    channel_kind = _channel_kind(channel_id)
    is_dm = channel_kind == "dm"

    is_mentioned = False
    if SLACK_BOT_USER_ID:
        mention_token = f"<@{SLACK_BOT_USER_ID}>"
        if mention_token in text:
            is_mentioned = True

    normalized = {
        "team_id": team_id,
        "channel_id": channel_id,
        "channel_kind": channel_kind,
        "user_id": user_id,
        "text": text,
        "ts": ts,
        "thread_ts": thread_ts,
        "is_mentioned": is_mentioned,
        "is_dm": is_dm,
        "event_type": "message",
    }

    logger.info("Normalized event: %s", json.dumps(normalized))

    if not STEP_FUNCTION_ARN:
        logger.error("STEP_FUNCTION_ARN is not set; skipping Step Functions call")
    else:
        try:
            sfn.start_execution(
                stateMachineArn=STEP_FUNCTION_ARN,
                input=json.dumps(normalized),
            )
        except Exception:
            logger.exception("Failed to start Step Functions execution")

    # Always ACK quickly.
    return {"statusCode": 200, "body": ""}
