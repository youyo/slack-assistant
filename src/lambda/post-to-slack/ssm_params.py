"""SSM Parameter Store ユーティリティ

Lambda実行時にSSM Parameter Storeから動的にパラメータを取得する。
aws-lambda-powertoolsのキャッシュ機能を使用してAPIコールを削減。
"""

import os

from aws_lambda_powertools.utilities.parameters import get_parameter


def get_slack_bot_token() -> str:
    """Slack Bot Token を取得

    Returns:
        str: Slack Bot Token
    """
    param_name = os.environ["SSM_SLACK_BOT_TOKEN"]
    return get_parameter(param_name, max_age=300)
