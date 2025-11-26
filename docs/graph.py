\"\"\"Strands Graph skeleton for the Slack × Strands × AgentCore bot.

This file does NOT try to fully implement the Strands Graph, because the
exact APIs depend on the Strands version you use.

Instead, it documents the intended structure so that a coding agent or a
human can wire it up correctly.

Intended structure:

- Graph with two main nodes:
    1. router_node  (uses build_router_prompt())
    2. convo_node   (uses build_conversation_prompt() and memory)

- Shared memory/session manager should be created outside and injected
  so both nodes share the same actor_id / session_id.
\"\"\"

from typing import Any, Dict

from router_agent import build_router_prompt
from conversation_agent import build_conversation_prompt

# NOTE: The following pseudocode illustrates how you might build the graph.
# Replace it with the actual Strands Graph / Workflow APIs you use.


def build_slack_graph() -> Any:
    \"\"\"Return a Strands Graph (or equivalent) for use in AgentCore Runtime.

    Pseudocode idea:

    from strands import Agent, Graph

    router = Agent(
        system_prompt=build_router_prompt(),
        model="amazon.nova-micro",   # TODO: wire actual provider/model
        session_manager=shared_session_manager,
    )

    convo = Agent(
        system_prompt=build_conversation_prompt(),
        model="sonnet-4.5",          # TODO: wire actual provider/model
        session_manager=shared_session_manager,
    )

    def route_fn(state):
        # state contains router output JSON
        if not state["router"]["should_reply"]:
            return "END"
        if state["router"]["route"] == "simple_reply":
            return "END"  # router output is final
        return "convo"

    graph = Graph()
    graph.add_node("router", router)
    graph.add_node("convo", convo)
    graph.set_start("router")
    graph.add_edge("router", "convo", condition=route_fn)
    graph.add_terminal("END")

    return graph

    This file is intentionally left as a skeleton.  Use the above comments
    as guidance when wiring your real Graph.
    \"\"\"
    raise NotImplementedError(
        "Implement build_slack_graph() using your Strands Graph APIs."
    )
