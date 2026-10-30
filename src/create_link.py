import json
import os
import secrets
import string
import time
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

# Created outside the handler so warm invocations reuse it (cold start optimisation).
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

ALPHABET = string.ascii_letters + string.digits  # 62 symbols
CODE_LENGTH = 7                                   # 62^7 ~ 3.5 trillion combinations
MAX_RETRIES = 5
MAX_URL_LENGTH = 2048


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def is_valid_url(url):
    if not isinstance(url, str) or len(url) > MAX_URL_LENGTH:
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def generate_code():
    # `secrets` is cryptographically secure, so codes are not guessable.
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def lambda_handler(event, context):
    # 1. Parse the body (API Gateway delivers it as a string).
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Body must be valid JSON"})

    # 2. Validate the input.
    long_url = body.get("url")
    if not is_valid_url(long_url):
        return response(400, {"error": "Provide a valid http(s) URL in the 'url' field"})

    # 3. Generate a code and save it, retrying if the code is already taken.
    for _ in range(MAX_RETRIES):
        code = generate_code()
        try:
            table.put_item(
                Item={
                    "code": code,
                    "long_url": long_url,
                    "created_at": int(time.time()),
                    "clicks": 0,
                },
                # Only write if nobody else already uses this code.
                ConditionExpression="attribute_not_exists(code)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                continue  # collision, try another code
            raise  # real error (permissions, throttling...), let it surface

        domain = event["requestContext"]["domainName"]
        return response(201, {"code": code, "short_url": f"https://{domain}/{code}"})

    return response(500, {"error": "Could not generate a unique code, try again"})
