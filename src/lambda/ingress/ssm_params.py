"""SSM Parameter Store ユーティリティ

Lambda実行時にSSM Parameter Storeから動的にパラメータを取得する。
aws-lambda-powertoolsのキャッシュ機能を使用してAPIコールを削減。
"""

import os

from aws_lambda_powertools.utilities.parameters import get_parameter


def get_slack_signing_secret() -> str:
    """Slack Signing Secret を取得

    Returns:
        str: Slack Signing Secret
    """
    param_name = os.environ["SSM_SLACK_SIGNING_SECRET"]
    return get_parameter(param_name, max_age=300)


def get_slack_bot_user_id() -> str:
    """Slack Bot User ID を取得

    Returns:
        str: Slack Bot User ID
    """
    param_name = os.environ["SSM_SLACK_BOT_USER_ID"]
    return get_parameter(param_name, max_age=300)
