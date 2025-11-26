\"\"\"Helper script to create an AgentCore Memory resource for the Slack bot.

NOTE:
    The exact service name and API parameters for AgentCore Memory may
    change; please confirm with the latest AWS Bedrock AgentCore docs.

    This script is intentionally conservative and uses placeholders where
    the API surface is not yet final.  Treat it as a starting point.
\"\"\"

import json
import os

import boto3


def main() -> None:
    # TODO: Confirm the correct client name. It might be "bedrock-agent",
    # "bedrock-agentcore", or similar depending on the AWS SDK release.
    client = boto3.client("bedrock-agent")  # placeholder; update as needed

    name = os.environ.get("AGENTCORE_MEMORY_NAME", "SlackStrandsAgentMemory")
    description = "Slack bot memory (channel LTM + thread STM)"

    # The following payload is illustrative.  Adjust it to match the
    # actual Memory create API for AgentCore.
    params = {
        "name": name,
        "description": description,
        "strategies": [
            {
                "summaryMemoryStrategy": {
                    "name": "SessionSummarizer",
                    "namespaces": ["/summaries/{actorId}/{sessionId}"],
                }
            },
            {
                "userPreferenceMemoryStrategy": {
                    "name": "ChannelPreferences",
                    "namespaces": ["/preferences/{actorId}"],
                }
            },
            {
                "semanticMemoryStrategy": {
                    "name": "ChannelFacts",
                    "namespaces": ["/facts/{actorId}"],
                }
            },
        ],
    }

    print("Creating AgentCore Memory with params:")
    print(json.dumps(params, indent=2, ensure_ascii=False))

    # resp = client.create_memory(**params)
    # print("Created memory:", resp)

    print(
        "NOTE: The create_memory call is commented out. "
        "Uncomment it and adjust `client` + `params` according to the "
        "latest AgentCore Memory API."
    )


if __name__ == "__main__":
    main()
