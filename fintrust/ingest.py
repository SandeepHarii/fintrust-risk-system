import json
import logging
from typing import Any


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle an S3 object-created event."""

    logger.info(
        json.dumps(
            {
                "event": "ingest_lambda_invoked",
                "record_count": len(event.get("Records", [])),
                "request_id": getattr(context, "aws_request_id", None),
            },
            default=str,
        )
    )

    records = event.get("Records", [])

    for record in records:
        bucket = record.get("s3", {}).get("bucket", {}).get("name")
        object_key = record.get("s3", {}).get("object", {}).get("key")

        logger.info(
            json.dumps(
                {
                    "event": "s3_object_received",
                    "bucket": bucket,
                    "object_key": object_key,
                },
                default=str,
            )
        )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "S3 event received successfully",
                "records_processed": len(records),
            }
        ),
    }