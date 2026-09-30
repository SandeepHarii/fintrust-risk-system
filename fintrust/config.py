import os

import boto3


_ssm = boto3.client("ssm")


def get_parameter(name: str, decrypt: bool = False) -> str:
    """Retrieve a parameter from AWS Systems Manager Parameter Store."""
    response = _ssm.get_parameter(
        Name=name,
        WithDecryption=decrypt,
    )
    return response["Parameter"]["Value"]


def get_config(name: str, default: str | None = None, decrypt: bool = False) -> str:
    """Load configuration from environment variables or SSM Parameter Store."""
    value = os.getenv(name)

    if value:
        return value

    parameter_name = os.getenv(f"{name}_PARAMETER")

    if parameter_name:
        return get_parameter(parameter_name, decrypt=decrypt)

    if default is not None:
        return default

    raise RuntimeError(f"Missing required configuration: {name}")