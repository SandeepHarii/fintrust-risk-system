import json
import boto3

client = boto3.client("dynamodb", region_name="eu-north-1")
table = "fintrust-prod-risk-events"

with open("dynamodb-risk-events-backup.json", encoding="utf-8-sig") as f:
    original = json.load(f)["Items"]

restored = []
response = client.scan(TableName=table)
restored.extend(response.get("Items", []))

while "LastEvaluatedKey" in response:
    response = client.scan(
        TableName=table,
        ExclusiveStartKey=response["LastEvaluatedKey"]
    )
    restored.extend(response.get("Items", []))

def key(item):
    return (item["account_id"]["S"], item["transaction_id"]["S"])

original_map = {key(item): item for item in original}
restored_map = {key(item): item for item in restored}

differences = [
    k for k in original_map.keys() & restored_map.keys()
    if original_map[k] != restored_map[k]
]

print(f"Original records: {len(original)}")
print(f"Restored records: {len(restored)}")
print(f"Missing records: {len(set(original_map) - set(restored_map))}")
print(f"Unexpected records: {len(set(restored_map) - set(original_map))}")
print(f"Content differences: {len(differences)}")

if len(original) == len(restored) == 371 and not differences and original_map.keys() == restored_map.keys():
    print("FINAL RESTORE VERIFICATION PASSED")
else:
    print("FINAL RESTORE VERIFICATION FAILED")
