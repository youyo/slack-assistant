"""Entry point for the Bedrock AgentCore Runtime.

AgentCore Runtime will call into this handler when invoked via the
InvokeAgentRuntime API from Step Functions.

This handler:
1. Parses the prompt and metadata from the payload
2. Derives actor_id (channel_id) and session_id (thread_ts)
3. Runs the 2-agent orchestration (Router -> Conversation)
4. Returns the final JSON result for the Slack Posting Lambda
"""

import logging
import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from graph import run_orchestration

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
AGENTCORE_MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

# Initialize the AgentCore App
app = BedrockAgentCoreApp()


def _derive_ids_from_metadata(metadata: dict) -> dict:
    """Derive actor_id and session_id from Slack metadata.

    - actor_id: channel_id (used for channel-level memory)
    - session_id: thread_ts or ts (used for thread-level memory)

    Note: sessionId must match pattern [a-zA-Z0-9][a-zA-Z0-9-_]*
    Slack timestamps contain dots (e.g., "1766995363.547589") which are invalid,
    so we replace them with underscores.
    """
    slack_meta = metadata.get("slack", {})
    channel_id = slack_meta.get("channel_id", "unknown")
    thread_ts = slack_meta.get("thread_ts") or slack_meta.get("ts", "session")

    # Replace dots with underscores to satisfy AgentCore Memory API constraints
    session_id = thread_ts.replace(".", "_")

    return {
        "actor_id": channel_id,
        "session_id": session_id,
    }


def _build_user_message(prompt: str, metadata: dict) -> str:
    """Build the user message with Slack context for the agents."""
    slack_meta = metadata.get("slack", {})

    context_parts = [
        f"User message: {prompt}",
        "",
        "Slack context:",
        f"- is_mentioned: {slack_meta.get('is_mentioned', False)}",
        f"- is_dm: {slack_meta.get('is_dm', False)}",
        f"- channel_kind: {slack_meta.get('channel_kind', 'unknown')}",
    ]

    return "\n".join(context_parts)


@app.entrypoint
def invoke(payload: dict) -> dict:
    """Main AgentCore Runtime handler.

    Expected payload structure from Step Functions:
    {
        "prompt": "user message text",
        "metadata": {
            "slack": {
                "team_id": "...",
                "channel_id": "...",
                "user_id": "...",
                "is_mentioned": true,
                "is_dm": false,
                "channel_kind": "public",
                "ts": "...",
                "thread_ts": "..."
            }
        }
    }

    Returns:
        Dict with should_reply, route, reply_mode, typing_style, reply_text, reason
    """
    logger.info("AgentCore handler invoked with payload keys: %s", list(payload.keys()))

    # Extract prompt and metadata
    prompt = payload.get("prompt", "")
    metadata = payload.get("metadata", {})

    if not prompt:
        logger.warning("Empty prompt received")
        return {
            "should_reply": False,
            "route": "ignore",
            "reply_mode": "thread",
            "typing_style": "none",
            "reply_text": "",
            "reason": "Empty prompt",
        }

    # Derive IDs for memory
    ids = _derive_ids_from_metadata(metadata)
    actor_id = ids["actor_id"]
    session_id = ids["session_id"]

    logger.info(
        "Processing message: actor_id=%s, session_id=%s, prompt_length=%d",
        actor_id,
        session_id,
        len(prompt),
    )

    try:
        # Build user message with context
        user_message = _build_user_message(prompt, metadata)

        # Run the 2-agent orchestration (Router -> Conversation)
        logger.info("Running orchestration...")
        final_result = run_orchestration(
            user_message=user_message,
            memory_id=AGENTCORE_MEMORY_ID if AGENTCORE_MEMORY_ID else None,
            session_id=session_id,
            actor_id=actor_id,
        )

        logger.info(
            "Orchestration completed: should_reply=%s, route=%s",
            final_result.get("should_reply"),
            final_result.get("route"),
        )

        return final_result

    except Exception as e:
        logger.error("Error during orchestration: %s", str(e), exc_info=True)
        return {
            "should_reply": False,
            "route": "ignore",
            "reply_mode": "thread",
            "typing_style": "none",
            "reply_text": "",
            "reason": f"Error: {str(e)}",
        }


if __name__ == "__main__":
    app.run()
