import boto3

table = boto3.resource(
    "dynamodb", region_name="eu-north-1"
).Table("fintrust-prod-risk-events")

deleted = 0
kwargs = {
    "ProjectionExpression": "#a, #t",
    "ExpressionAttributeNames": {
        "#a": "account_id",
        "#t": "transaction_timestamp"
    }
}

while True:
    response = table.scan(**kwargs)

    with table.batch_writer() as batch:
        for item in response.get("Items", []):
            batch.delete_item(Key={
                "account_id": item["account_id"],
                "transaction_timestamp": item["transaction_timestamp"]
            })
            deleted += 1

    if "LastEvaluatedKey" not in response:
        break

    kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

print(f"Delete requests submitted: {deleted}")
print("DynamoDB cleanup finished.")
