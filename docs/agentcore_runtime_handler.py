\"\"\"Entry point for the Bedrock AgentCore Runtime.

AgentCore Runtime will call into this handler when invoked via the
`InvokeAgent` / runtime API.

The concrete request/response structure may differ depending on how
you configure AgentCore.  This file provides a clear place to:

- Parse the inputText + metadata from Step Functions (Slack event).
- Construct actor_id / session_id.
- Create an AgentCoreMemorySessionManager.
- Build the Strands Graph.
- Run the graph and return the final JSON result expected by the
  Slack Posting Lambda.
\"\"\"

import json
import logging
import os
from typing import Any, Dict

# from bedrock_agentcore.memory.integrations.strands import (
#     AgentCoreMemoryConfig,
#     AgentCoreMemorySessionManager,
# )
#
# from strands import Agent  # or Graph runtime
#
# from graph import build_slack_graph

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AGENTCORE_MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")


def _derive_ids_from_metadata(metadata: Dict[str, Any]) -> Dict[str, str]:
    \"\"\"Derive actor_id and session_id from Slack metadata.

    - actor_id: channel_id
    - session_id: thread_ts (or ts)
    \"\"\"
    slack_meta = metadata.get("slack") or {}
    channel_id = slack_meta.get("channel_id") or "unknown"
    thread_ts = slack_meta.get("thread_ts") or slack_meta.get("ts") or "session"
    return {
        "actor_id": channel_id,
        "session_id": thread_ts,
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    \"\"\"Main AgentCore Runtime handler.

    The exact shape of `event` depends on how you wire InvokeAgent
    from Step Functions.

    A common pattern is:

    {
      "inputText": "user message text",
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

    This handler should:

    1. Extract inputText + Slack metadata.
    2. Build actor_id/session_id.
    3. Create an AgentCoreMemorySessionManager.
    4. Build and run the Strands Graph.
    5. Return the final JSON reply (as a dict). AgentCore will
       encode it back to the caller (Step Functions).
    \"\"\"
    logger.info("AgentCore handler event: %s", json.dumps(event))

    input_text = event.get("inputText") or ""
    metadata = event.get("metadata") or {}

    ids = _derive_ids_from_metadata(metadata)
    actor_id = ids["actor_id"]
    session_id = ids["session_id"]

    # TODO: Instantiate AgentCoreMemorySessionManager with AGENTCORE_MEMORY_ID,
    #       actor_id, session_id.  Example (pseudocode):
    #
    # memory_config = AgentCoreMemoryConfig(
    #     memory_id=AGENTCORE_MEMORY_ID,
    #     actor_id=actor_id,
    #     session_id=session_id,
    #     retrieval_config={
    #         "/preferences/{actorId}": {"top_k": 5, "relevance_score": 0.7},
    #         "/facts/{actorId}": {"top_k": 10, "relevance_score": 0.5},
    #         "/summaries/{actorId}/{sessionId}": {"top_k": 3, "relevance_score": 0.4},
    #     },
    # )
    # session_manager = AgentCoreMemorySessionManager(
    #     agentcore_memory_config=memory_config,
    #     region_name=AWS_REGION,
    # )
    #
    # graph = build_slack_graph(session_manager)

    # For now, just return a dummy reply so that the plumbing can be
    # tested end-to-end.  Replace this with an actual Strands graph
    # execution.
    dummy_reply = {
        "should_reply": True,
        "route": "full_reply",
        "reply_mode": "thread",
        "typing_style": "none",
        "reply_text": f"(dummy reply) You said: {input_text}",
        "reason": "dummy implementation",
    }

    return dummy_reply
