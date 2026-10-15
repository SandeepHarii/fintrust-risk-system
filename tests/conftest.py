
import boto3
import pytest
from moto import mock_aws

from fintrust import alert
from fintrust import dynamo
from fintrust import ingest


@pytest.fixture
def aws_resources():
    """Provide reusable mocked AWS resources."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="eu-north-1")
        dynamodb = boto3.resource("dynamodb", region_name="eu-north-1")
        dynamodb_client = boto3.client("dynamodb", region_name="eu-north-1")
        cloudwatch = boto3.client("cloudwatch", region_name="eu-north-1")
        sqs = boto3.client("sqs", region_name="eu-north-1")
        ses = boto3.client("ses", region_name="eu-north-1")

        ses.verify_email_identity(
            EmailAddress=alert.SENDER_EMAIL,
        )

        ses.verify_email_identity(
            EmailAddress=alert.COMPLIANCE_EMAIL,
        )

        # Replace module-level AWS clients with Moto clients.
        ingest._s3 = s3
        ingest._cloudwatch = cloudwatch
        ingest._sqs = sqs
        alert._ses = ses

        source_bucket = "fintrust-prod-raw-transactions"
        quarantine_bucket = "fintrust-prod-quarantine-transactions"
        dynamodb_table = "fintrust-prod-risk-events"
        upload_tracking_table_name = dynamo.UPLOAD_TRACKING_TABLE_NAME
        sqs_queue_name = "fintrust-prod-transaction-queue.fifo"

        s3.create_bucket(
            Bucket=source_bucket,
            CreateBucketConfiguration={
                "LocationConstraint": "eu-north-1",
            },
        )

        s3.create_bucket(
            Bucket=quarantine_bucket,
            CreateBucketConfiguration={
                "LocationConstraint": "eu-north-1",
            },
        )

        table = dynamodb.create_table(
            TableName=dynamodb_table,
            KeySchema=[
                {"AttributeName": "account_id", "KeyType": "HASH"},
                {"AttributeName": "transaction_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "account_id", "AttributeType": "S"},
                {"AttributeName": "transaction_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        upload_tracking_table = dynamodb.create_table(
            TableName=upload_tracking_table_name,
            KeySchema=[
                {"AttributeName": "upload_id", "KeyType": "HASH"},
                {"AttributeName": "record_type", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "upload_id", "AttributeType": "S"},
                {"AttributeName": "record_type", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Replace production DynamoDB resources and low-level client.
        dynamo.table = table
        dynamo.upload_tracking_table = upload_tracking_table
        dynamo._dynamodb_client = dynamodb_client

        queue = sqs.create_queue(
            QueueName=sqs_queue_name,
            Attributes={
                "FifoQueue": "true",
                "ContentBasedDeduplication": "false",
            },
        )

        # Replace the production queue URL with the Moto queue URL.
        ingest.TRANSACTION_QUEUE_URL = queue["QueueUrl"]

        yield {
            "s3": s3,
            "dynamodb": dynamodb,
            "cloudwatch": cloudwatch,
            "sqs": sqs,
            "table": table,
            "upload_tracking_table": upload_tracking_table,
            "queue": queue,
            "source_bucket": source_bucket,
            "quarantine_bucket": quarantine_bucket,
            "dynamodb_table": dynamodb_table,
            "upload_tracking_table_name": upload_tracking_table_name,
            "queue_url": queue["QueueUrl"],
        }