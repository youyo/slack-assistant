"""Strands Graph for the Slack x Strands x AgentCore bot.

This module builds a Graph with two main nodes:
1. Router Agent - decides whether to reply and how
2. Conversation Agent - generates the actual reply

The Graph uses conditional edges to route based on the Router's decision.
"""

import json
import logging
import os
from typing import Any, Optional

from strands import Agent
from strands.multiagent import GraphBuilder
from strands.multiagent.base import Status

from agents import ROUTER_SYSTEM_PROMPT, CONVERSATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Model IDs for Bedrock
ROUTER_MODEL_ID = os.environ.get(
    "ROUTER_MODEL_ID", "amazon.nova-micro-v1:0"
)
CONVERSATION_MODEL_ID = os.environ.get(
    "CONVERSATION_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250514-v1:0"
)


def _parse_router_result(state: Any) -> dict:
    """Parse the Router agent's JSON result from state."""
    router_node = state.results.get("router")
    if not router_node or not router_node.result:
        return {}

    try:
        result_text = str(router_node.result.message.content[0].get("text", ""))
        # Try to extract JSON from the result
        return json.loads(result_text)
    except (json.JSONDecodeError, AttributeError, IndexError, KeyError) as e:
        logger.warning("Failed to parse router result: %s", e)
        return {}


def _needs_full_reply(state: Any) -> bool:
    """Condition: route to Conversation Agent if full_reply is needed."""
    data = _parse_router_result(state)
    should_reply = data.get("should_reply", False)
    route = data.get("route", "ignore")

    if should_reply and route == "full_reply":
        logger.info("Routing to conversation agent: full_reply requested")
        return True
    return False


def build_slack_graph(
    session_manager: Optional[Any] = None,
    memory_id: Optional[str] = None,
    session_id: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> Any:
    """Build a Strands Graph for Slack Bot.

    Args:
        session_manager: Optional AgentCoreMemorySessionManager instance.
                         If not provided, memory will not be used.
        memory_id: Memory ID (used only if session_manager is not provided)
        session_id: Session ID (used only if session_manager is not provided)
        actor_id: Actor ID (used only if session_manager is not provided)

    Returns:
        A compiled Strands Graph ready for execution.
    """
    # Create Session Manager if not provided but memory_id is available
    if session_manager is None and memory_id:
        try:
            from bedrock_agentcore.memory.integrations.strands.config import (
                AgentCoreMemoryConfig,
                RetrievalConfig,
            )
            from bedrock_agentcore.memory.integrations.strands.session_manager import (
                AgentCoreMemorySessionManager,
            )

            memory_config = AgentCoreMemoryConfig(
                memory_id=memory_id,
                session_id=session_id or "default_session",
                actor_id=actor_id or "default_actor",
                retrieval_config={
                    "/preferences/{actorId}": RetrievalConfig(
                        top_k=5, relevance_score=0.7
                    ),
                    "/facts/{actorId}": RetrievalConfig(
                        top_k=10, relevance_score=0.3
                    ),
                    "/summaries/{actorId}/{sessionId}": RetrievalConfig(
                        top_k=3, relevance_score=0.5
                    ),
                },
            )
            session_manager = AgentCoreMemorySessionManager(
                agentcore_memory_config=memory_config,
                region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
            )
            logger.info("Created AgentCoreMemorySessionManager with memory_id=%s", memory_id)
        except ImportError:
            logger.warning("bedrock_agentcore not available, memory disabled")
            session_manager = None
        except Exception as e:
            logger.warning("Failed to create session manager: %s", e)
            session_manager = None

    # Create Router Agent (lightweight model, no memory needed)
    router = Agent(
        name="router",
        system_prompt=ROUTER_SYSTEM_PROMPT,
        model=ROUTER_MODEL_ID,
    )

    # Create Conversation Agent (high-performance model with memory)
    conversation = Agent(
        name="conversation",
        system_prompt=CONVERSATION_SYSTEM_PROMPT,
        model=CONVERSATION_MODEL_ID,
        session_manager=session_manager,
    )

    # Build the Graph
    builder = GraphBuilder()
    builder.add_node(router, "router")
    builder.add_node(conversation, "conversation")

    # Router -> Conversation (conditional: only if full_reply)
    builder.add_edge("router", "conversation", condition=_needs_full_reply)

    # Set entry point
    builder.set_entry_point("router")

    # Set execution limits
    builder.set_execution_timeout(60)  # 60 seconds timeout

    return builder.build()


def extract_final_result(graph_result: Any) -> dict:
    """Extract the final JSON result from Graph execution.

    The result could come from either:
    - Router (if simple_reply or ignore)
    - Conversation (if full_reply)

    Args:
        graph_result: The result from graph execution

    Returns:
        A dict with should_reply, route, reply_mode, typing_style, reply_text, reason
    """
    default_result = {
        "should_reply": False,
        "route": "ignore",
        "reply_mode": "thread",
        "typing_style": "none",
        "reply_text": "",
        "reason": "No result from graph",
    }

    if not graph_result or graph_result.status != Status.COMPLETED:
        logger.warning("Graph execution did not complete successfully")
        return default_result

    # Check Conversation Agent result first (higher priority)
    if "conversation" in graph_result.results:
        conv_result = graph_result.results["conversation"]
        if conv_result.result:
            try:
                text = str(conv_result.result.message.content[0].get("text", ""))
                return json.loads(text)
            except (json.JSONDecodeError, AttributeError, IndexError, KeyError) as e:
                logger.warning("Failed to parse conversation result: %s", e)

    # Fall back to Router Agent result
    if "router" in graph_result.results:
        router_result = graph_result.results["router"]
        if router_result.result:
            try:
                text = str(router_result.result.message.content[0].get("text", ""))
                data = json.loads(text)
                # Router doesn't provide reply_text for simple_reply, add default
                if "reply_text" not in data:
                    data["reply_text"] = ""
                return data
            except (json.JSONDecodeError, AttributeError, IndexError, KeyError) as e:
                logger.warning("Failed to parse router result: %s", e)

    return default_result
