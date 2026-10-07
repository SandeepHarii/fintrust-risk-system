import boto3
from moto import mock_aws

from fintrust import report


@mock_aws
def test_upload_report_to_s3():
    s3 = boto3.client("s3", region_name="eu-north-1")

    # Replace the module-level S3 client with the Moto client.
    report.s3 = s3

    bucket_name = "fintrust-test-reports"

    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={
            "LocationConstraint": "eu-north-1",
        },
    )

    report.REPORT_BUCKET = bucket_name

    content = "account_id,account_number\n123,4100000000000123\n"

    report.upload_report(
        "monthly/2026-10/test-report.csv",
        content,
        "text/csv",
    )

    response = s3.get_object(
        Bucket=bucket_name,
        Key="monthly/2026-10/test-report.csv",
    )

    downloaded_content = response["Body"].read().decode("utf-8")

    assert downloaded_content == content
    assert response["ContentType"] == "text/csv"