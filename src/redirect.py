import os

import boto3
from botocore.exceptions import ClientError

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def lambda_handler(event, context):
    code = (event.get("pathParameters") or {}).get("code")
    if not code:
        return {"statusCode": 400, "body": "Missing code"}

    try:
        # a single call counts the click and fetches the URL
        result = table.update_item(
            Key={"code": code},
            UpdateExpression="ADD clicks :one",
            ConditionExpression="attribute_exists(code)",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {"statusCode": 404, "body": "Short link not found"}
        raise

    return {
        "statusCode": 302,  # 302, not 301, so browsers don't cache it and every click is counted
        "headers": {"Location": result["Attributes"]["long_url"]},
        "body": "",
    }
