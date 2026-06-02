"""AWS Secrets Manager integration.

This module provides utilities for fetching database credentials
from AWS Secrets Manager.
"""

import json

from pydantic import BaseModel

from core.exceptions import DbConnectionError


class AWSDbCredentials(BaseModel):
    """AWS database credentials from Secrets Manager."""

    username: str = ""
    password: str = ""
    host: str = "localhost"
    port: int = 5432
    dbname: str = "postgres"

    @classmethod
    def from_secret(cls, secret_dict: dict) -> "AWSDbCredentials":
        """Create credentials from a Secrets Manager secret dictionary."""
        return cls(
            username=secret_dict.get("username", ""),
            password=secret_dict.get("password", ""),
            host=secret_dict.get("proxyEndpoint") or secret_dict.get("host", "localhost"),
            port=int(secret_dict.get("port", 5432)),
            dbname=secret_dict.get("dbname", "postgres"),
        )


def get_secret_value(secret_id: str, region: str = "us-west-1") -> dict:
    """Fetch a secret value from AWS Secrets Manager.

    Args:
        secret_id: The ARN or name of the secret
        region: AWS region (default: us-west-1)

    Returns:
        Parsed JSON secret as a dictionary

    Raises:
        ImportError: If boto3 is not installed
        ValueError: If secret is not found or has no string value
        PermissionError: If access is denied
        DbConnectionError: For other AWS errors
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as e:
        raise ImportError("boto3 required. Install with: pip install boto3") from e

    client = boto3.client("secretsmanager", region_name=region)
    try:
        response = client.get_secret_value(SecretId=secret_id)
        if secret_string := response.get("SecretString"):
            return json.loads(secret_string)
        raise ValueError(f"Secret {secret_id} has no string value")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        if code == "ResourceNotFoundException":
            raise ValueError(f"Secret not found: {secret_id}") from e
        elif code == "AccessDeniedException":
            raise PermissionError(f"Access denied: {secret_id}") from e
        raise DbConnectionError(f"AWS error: {str(e)}", original_error=e) from e


def get_db_credentials_from_secret(secret_name: str, region: str = "us-west-1") -> AWSDbCredentials:
    return AWSDbCredentials.from_secret(get_secret_value(secret_name, region))
