import json
import time
import boto3

REGION = "eu-north-1"
TABLE = "fintrust-prod-risk-events-migration"
BACKUP = "dynamodb-risk-events-backup.json"

client = boto3.client("dynamodb", region_name=REGION)

with open(BACKUP, encoding="utf-8-sig") as f:
    records = json.load(f)["Items"]

print(f"Starting migration of {len(records)} records...")

migrated = 0

for start in range(0, len(records), 25):
    batch = records[start:start + 25]
    request = {
        TABLE: [{"PutRequest": {"Item": item}} for item in batch]
    }

    while request:
        response = client.batch_write_item(RequestItems=request)
        request = response.get("UnprocessedItems", {})

        if request:
            time.sleep(1)

    migrated += len(batch)
    print(f"Migrated: {migrated}/{len(records)}")

print("Migration copy completed.")
