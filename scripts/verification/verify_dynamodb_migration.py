import json
import boto3

client = boto3.client("dynamodb", region_name="eu-north-1")
table = "fintrust-prod-risk-events-migration"

with open("dynamodb-risk-events-backup.json", encoding="utf-8-sig") as f:
    original = json.load(f)["Items"]

migrated = []
response = client.scan(TableName=table)

migrated.extend(response.get("Items", []))

while "LastEvaluatedKey" in response:
    response = client.scan(
        TableName=table,
        ExclusiveStartKey=response["LastEvaluatedKey"]
    )
    migrated.extend(response.get("Items", []))

def key(item):
    return (item["account_id"]["S"], item["transaction_id"]["S"])

original_map = {key(item): item for item in original}
migrated_map = {key(item): item for item in migrated}

print(f"Original records: {len(original)}")
print(f"Migrated records: {len(migrated)}")
print(f"Missing records: {len(set(original_map) - set(migrated_map))}")
print(f"Unexpected records: {len(set(migrated_map) - set(original_map))}")

differences = [
    k for k in original_map.keys() & migrated_map.keys()
    if original_map[k] != migrated_map[k]
]

print(f"Records with content differences: {len(differences)}")
print(f"Unique transaction keys: {len(migrated_map)}")

if (
    len(original) == 371
    and len(migrated) == 371
    and not differences
    and original_map.keys() == migrated_map.keys()
):
    print("VERIFICATION PASSED")
else:
    print("VERIFICATION FAILED")
