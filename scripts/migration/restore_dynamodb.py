import time
import boto3

client = boto3.client("dynamodb", region_name="eu-north-1")

SOURCE = "fintrust-prod-risk-events-migration"
TARGET = "fintrust-prod-risk-events"

records = []
response = client.scan(TableName=SOURCE)
records.extend(response.get("Items", []))

while "LastEvaluatedKey" in response:
    response = client.scan(
        TableName=SOURCE,
        ExclusiveStartKey=response["LastEvaluatedKey"]
    )
    records.extend(response.get("Items", []))

print(f"Records found in migration table: {len(records)}")

restored = 0

for start in range(0, len(records), 25):
    batch = records[start:start + 25]
    request = {
        TARGET: [{"PutRequest": {"Item": item}} for item in batch]
    }

    while request:
        result = client.batch_write_item(RequestItems=request)
        request = result.get("UnprocessedItems", {})
        if request:
            time.sleep(1)

    restored += len(batch)
    print(f"Restored: {restored}/{len(records)}")

print("Restore completed.")
