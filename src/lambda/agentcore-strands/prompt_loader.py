"""System prompt loader with SSM Parameter Store integration.

Loads system prompts from SSM Parameter Store at runtime with fallback to defaults.
Uses aws-lambda-powertools cache to reduce API calls.
"""

import logging
import os

from aws_lambda_powertools.utilities.parameters import get_parameter

logger = logging.getLogger(__name__)


def get_router_system_prompt() -> str:
    """Get Router Agent system prompt from SSM or fallback to default.

    Environment:
        SSM_ROUTER_SYSTEM_PROMPT: SSM parameter name (optional)

    Returns:
        str: Router system prompt
    """
    param_name = os.environ.get("SSM_ROUTER_SYSTEM_PROMPT")
    if not param_name:
        logger.info("SSM_ROUTER_SYSTEM_PROMPT not set, using default prompt")
        from agents.router_agent import _DEFAULT_ROUTER_SYSTEM_PROMPT

        return _DEFAULT_ROUTER_SYSTEM_PROMPT

    try:
        prompt = get_parameter(param_name, max_age=300)
        logger.info("Loaded router prompt from SSM: %s", param_name)
        return prompt
    except Exception as e:
        logger.warning(
            "Failed to load router prompt from SSM (%s): %s, using default",
            param_name,
            e,
        )
        from agents.router_agent import _DEFAULT_ROUTER_SYSTEM_PROMPT

        return _DEFAULT_ROUTER_SYSTEM_PROMPT


def get_conversation_system_prompt() -> str:
    """Get Conversation Agent system prompt from SSM or fallback to default.

    Environment:
        SSM_CONVERSATION_SYSTEM_PROMPT: SSM parameter name (optional)

    Returns:
        str: Conversation system prompt
    """
    param_name = os.environ.get("SSM_CONVERSATION_SYSTEM_PROMPT")
    if not param_name:
        logger.info("SSM_CONVERSATION_SYSTEM_PROMPT not set, using default prompt")
        from agents.conversation_agent import _DEFAULT_CONVERSATION_SYSTEM_PROMPT

        return _DEFAULT_CONVERSATION_SYSTEM_PROMPT

    try:
        prompt = get_parameter(param_name, max_age=300)
        logger.info("Loaded conversation prompt from SSM: %s", param_name)
        return prompt
    except Exception as e:
        logger.warning(
            "Failed to load conversation prompt from SSM (%s): %s, using default",
            param_name,
            e,
        )
        from agents.conversation_agent import _DEFAULT_CONVERSATION_SYSTEM_PROMPT

        return _DEFAULT_CONVERSATION_SYSTEM_PROMPT


# Export as module-level constants for backward compatibility
# Evaluated once at module load time (Lambda cold start)
ROUTER_SYSTEM_PROMPT = get_router_system_prompt()
CONVERSATION_SYSTEM_PROMPT = get_conversation_system_prompt()
