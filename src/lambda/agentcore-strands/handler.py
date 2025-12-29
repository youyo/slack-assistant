"""Entry point for the Bedrock AgentCore Runtime.

AgentCore Runtime will call into this handler when invoked via the
InvokeAgentRuntime API from Step Functions.

This handler:
1. Parses the prompt and metadata from the payload
2. Derives actor_id (channel_id) and session_id (thread_ts)
3. Builds and executes the Strands Graph
4. Returns the final JSON result for the Slack Posting Lambda
"""

import json
import logging
import os
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from graph import build_slack_graph, extract_final_result

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
    """
    slack_meta = metadata.get("slack", {})
    channel_id = slack_meta.get("channel_id", "unknown")
    thread_ts = slack_meta.get("thread_ts") or slack_meta.get("ts", "session")

    return {
        "actor_id": channel_id,
        "session_id": thread_ts,
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
        # Build the Graph with memory (if available)
        graph = build_slack_graph(
            memory_id=AGENTCORE_MEMORY_ID if AGENTCORE_MEMORY_ID else None,
            session_id=session_id,
            actor_id=actor_id,
        )

        # Build user message with context
        user_message = _build_user_message(prompt, metadata)

        # Execute the Graph
        logger.info("Executing Strands Graph...")
        result = graph(user_message)

        # Extract final result
        final_result = extract_final_result(result)
        logger.info(
            "Graph execution completed: should_reply=%s, route=%s",
            final_result.get("should_reply"),
            final_result.get("route"),
        )

        return final_result

    except Exception as e:
        logger.error("Error executing graph: %s", str(e), exc_info=True)
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
