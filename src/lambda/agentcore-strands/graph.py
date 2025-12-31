"""Manual Orchestration for the Slack x Strands x AgentCore bot.

This module provides simple if/else orchestration instead of Graph:
1. Router Agent - decides whether to reply and how
2. Conversation Agent - generates the actual reply (only if needed)

Note: Strands Graph does not support session_manager on agent nodes yet,
so we use manual orchestration to enable Memory functionality.
"""

import logging
import os
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from strands import Agent

from agents import ROUTER_SYSTEM_PROMPT, CONVERSATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Model IDs for Bedrock
ROUTER_MODEL_ID = os.environ.get(
    "ROUTER_MODEL_ID", "amazon.nova-micro-v1:0"
)
CONVERSATION_MODEL_ID = os.environ.get(
    "CONVERSATION_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250514-v1:0"
)


# Pydantic models for structured output
class RouterResponse(BaseModel):
    """Router agent's structured response."""

    should_reply: bool = Field(description="Whether the bot should reply to this message")
    route: Literal["ignore", "simple_reply", "full_reply"] = Field(
        description="Route decision: ignore, simple_reply, or full_reply"
    )
    reply_mode: Literal["thread", "channel"] = Field(
        default="thread", description="Reply mode: thread or channel"
    )
    typing_style: Literal["none", "short", "long"] = Field(
        default="none", description="Typing style: none, short, or long"
    )
    reason: str = Field(description="Short explanation in Japanese for the decision")

    @field_validator("typing_style", mode="before")
    @classmethod
    def normalize_typing_style(cls, v: Any) -> str:
        """Normalize typing_style to valid values."""
        valid_values = {"none", "short", "long"}
        if v in valid_values:
            return v
        return "none"


class ConversationResponse(BaseModel):
    """Conversation agent's structured response."""

    should_reply: bool = Field(default=True, description="Whether the bot should reply")
    route: Literal["full_reply"] = Field(
        default="full_reply", description="Route is always full_reply for conversation"
    )
    reply_mode: Literal["thread", "channel"] = Field(
        default="thread", description="Reply mode: thread or channel"
    )
    typing_style: Literal["none", "short", "long"] = Field(
        default="none", description="Typing style: none, short, or long"
    )
    reply_text: str = Field(description="The actual reply text to send to Slack")
    reason: str = Field(
        default="Full reply generated", description="Short explanation for the reply"
    )

    @field_validator("typing_style", mode="before")
    @classmethod
    def normalize_typing_style(cls, v: Any) -> str:
        """Normalize typing_style to valid values."""
        valid_values = {"none", "short", "long"}
        if v in valid_values:
            return v
        return "none"


def _create_session_manager(
    memory_id: Optional[str],
    session_id: Optional[str],
    actor_id: Optional[str],
) -> Optional[Any]:
    """Create AgentCoreMemorySessionManager if memory_id is available.

    Args:
        memory_id: AgentCore Memory ID
        session_id: Session ID (e.g., thread timestamp with underscores)
        actor_id: Actor ID (e.g., channel ID)

    Returns:
        AgentCoreMemorySessionManager instance or None
    """
    if not memory_id:
        logger.info("No memory_id provided, memory disabled")
        return None

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
        logger.info(
            "Created AgentCoreMemorySessionManager: memory_id=%s, session_id=%s, actor_id=%s",
            memory_id,
            session_id,
            actor_id,
        )
        return session_manager
    except ImportError:
        logger.warning("bedrock_agentcore not available, memory disabled")
        return None
    except Exception as e:
        logger.warning("Failed to create session manager: %s", e)
        return None


def run_orchestration(
    user_message: str,
    memory_id: Optional[str] = None,
    session_id: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> dict:
    """Run the 2-agent orchestration manually.

    Flow:
    0. Pre-filter short messages without mention
    1. Call Router Agent (no session_manager) to decide action
    2. If ignore -> return Router's decision
    3. If reply needed -> call Conversation Agent (with session_manager)
    4. Return final result

    Args:
        user_message: The user's input message with context
        memory_id: AgentCore Memory ID for session management
        session_id: Session ID (e.g., thread timestamp with underscores)
        actor_id: Actor ID (e.g., channel ID)

    Returns:
        dict with should_reply, route, reply_mode, typing_style, reply_text, reason
    """
    default_result = {
        "should_reply": False,
        "route": "ignore",
        "reply_mode": "thread",
        "typing_style": "none",
        "reply_text": "",
        "reason": "Error during orchestration",
    }

    # ========================================
    # Step 0: Pre-filter short messages
    # ========================================
    # Extract just the user text (before "Slack context:")
    text_only = user_message.split("\n\nSlack context:")[0].replace("User message: ", "").strip()

    # Check if mentioned (from context)
    is_mentioned = "is_mentioned: True" in user_message

    # Short messages (1-3 chars) without mention → immediate ignore
    # This avoids Router Agent timeout due to structured output validation failures
    if len(text_only) <= 3 and not is_mentioned:
        logger.info(
            "Pre-filter: Short message (%d chars) without mention, skipping Router",
            len(text_only),
        )
        return {
            "should_reply": False,
            "route": "ignore",
            "reply_mode": "thread",
            "typing_style": "none",
            "reply_text": "",
            "reason": "短いメッセージのため自動スキップ",
        }

    # ========================================
    # Step 1: Call Router Agent
    # ========================================
    try:
        logger.info("Step 1: Calling Router Agent...")
        router = Agent(
            name="router",
            system_prompt=ROUTER_SYSTEM_PROMPT,
            model=ROUTER_MODEL_ID,
            structured_output_model=RouterResponse,
            callback_handler=None,
        )

        router_result = router(user_message)

        # Get structured output
        if not hasattr(router_result, "structured_output") or router_result.structured_output is None:
            logger.error("Router Agent did not return structured output")
            default_result["reason"] = "Router failed to return structured output"
            return default_result

        router_output: RouterResponse = router_result.structured_output
        logger.info(
            "Router decision: should_reply=%s, route=%s, reason=%s",
            router_output.should_reply,
            router_output.route,
            router_output.reason,
        )

    except Exception as e:
        logger.error("Router Agent failed: %s", e, exc_info=True)
        default_result["reason"] = f"Router Agent error: {str(e)}"
        return default_result

    # ========================================
    # Step 2: Check Router's decision
    # ========================================
    if not router_output.should_reply or router_output.route == "ignore":
        logger.info("Router decided to ignore, returning early")
        return {
            "should_reply": router_output.should_reply,
            "route": router_output.route,
            "reply_mode": router_output.reply_mode,
            "typing_style": router_output.typing_style,
            "reply_text": "",
            "reason": router_output.reason,
        }

    # ========================================
    # Step 3: Call Conversation Agent (with Memory)
    # ========================================
    try:
        logger.info("Step 3: Calling Conversation Agent (route=%s)...", router_output.route)

        # Create session manager for memory
        session_manager = _create_session_manager(memory_id, session_id, actor_id)

        conversation = Agent(
            name="conversation",
            system_prompt=CONVERSATION_SYSTEM_PROMPT,
            model=CONVERSATION_MODEL_ID,
            session_manager=session_manager,
            structured_output_model=ConversationResponse,
            callback_handler=None,
        )

        conversation_result = conversation(user_message)

        # Get structured output
        if not hasattr(conversation_result, "structured_output") or conversation_result.structured_output is None:
            logger.error("Conversation Agent did not return structured output")
            # Fall back to router's decision
            return {
                "should_reply": router_output.should_reply,
                "route": router_output.route,
                "reply_mode": router_output.reply_mode,
                "typing_style": router_output.typing_style,
                "reply_text": "",
                "reason": "Conversation failed to return structured output",
            }

        conversation_output: ConversationResponse = conversation_result.structured_output
        logger.info(
            "Conversation completed: reply_text_length=%d",
            len(conversation_output.reply_text),
        )

        return conversation_output.model_dump()

    except Exception as e:
        logger.error("Conversation Agent failed: %s", e, exc_info=True)
        # Fall back to router's decision with error reason
        return {
            "should_reply": router_output.should_reply,
            "route": router_output.route,
            "reply_mode": router_output.reply_mode,
            "typing_style": router_output.typing_style,
            "reply_text": "",
            "reason": f"Conversation Agent error: {str(e)}",
        }
