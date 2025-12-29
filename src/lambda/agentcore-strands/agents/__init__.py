"""Agent definitions for the Slack × Strands × AgentCore bot."""

from .router_agent import ROUTER_SYSTEM_PROMPT
from .conversation_agent import CONVERSATION_SYSTEM_PROMPT

__all__ = ["ROUTER_SYSTEM_PROMPT", "CONVERSATION_SYSTEM_PROMPT"]
