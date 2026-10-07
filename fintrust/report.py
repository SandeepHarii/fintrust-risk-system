import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3

from fintrust.db import get_db_connection

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

REPORT_BUCKET = os.getenv("REPORT_BUCKET", "fintrust-prod-reports")

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def load_sql(filename: str) -> str:
    """Load a reporting SQL file from the project SQL directory."""
    sql_path = SQL_DIR / filename

    if not sql_path.exists():
        raise FileNotFoundError(f"SQL report file not found: {sql_path}")

    return sql_path.read_text(encoding="utf-8")


def execute_report(sql: str) -> tuple[list[str], list[dict]]:
    """Execute a reporting query and return column names and rows."""
    with get_db_connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)

                columns = [description[0] for description in cursor.description]
                rows = cursor.fetchall()

            return columns, [dict(zip(columns, row)) for row in rows]

        except Exception:
            conn.rollback()
            raise


def generate_csv(columns: list[str], rows: list[dict]) -> str:
    """Convert report rows into CSV format."""
    output = io.StringIO()

    writer = csv.DictWriter(
        output,
        fieldnames=columns,
        extrasaction="ignore",
    )

    writer.writeheader()
    writer.writerows(rows)

    return output.getvalue()


def generate_json(
    report_name: str,
    columns: list[str],
    rows: list[dict],
) -> str:
    """Convert report rows into JSON format."""
    payload = {
        "report": report_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "columns": columns,
        "data": rows,
    }

    return json.dumps(payload, default=str, indent=2)


def upload_report(
    key: str,
    content: str,
    content_type: str,
) -> None:
    """Upload generated report content to S3."""
    s3.put_object(
        Bucket=REPORT_BUCKET,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType=content_type,
    )


def lambda_handler(event, context):
    """Generate the monthly risk report and store CSV and JSON in S3."""
    logger.info(
        json.dumps(
            {
                "event": "report_started",
                "report_bucket": REPORT_BUCKET,
            }
        )
    )

    sql = load_sql("risk_report.sql")

    columns, rows = execute_report(sql)

    timestamp = datetime.now(timezone.utc)
    report_month = timestamp.strftime("%Y-%m")

    base_key = f"monthly/{report_month}/fintrust-risk-report"

    csv_content = generate_csv(columns, rows)
    json_content = generate_json(
        "fintrust-risk-report",
        columns,
        rows,
    )

    csv_key = f"{base_key}.csv"
    json_key = f"{base_key}.json"

    upload_report(
        csv_key,
        csv_content,
        "text/csv",
    )

    upload_report(
        json_key,
        json_content,
        "application/json",
    )

    result = {
        "status": "SUCCESS",
        "report": "fintrust-risk-report",
        "row_count": len(rows),
        "csv_key": csv_key,
        "json_key": json_key,
        "bucket": REPORT_BUCKET,
    }

    logger.info(
        json.dumps(
            {
                "event": "report_completed",
                **result,
            }
        )
    )

    return {
        "statusCode": 200,
        "body": json.dumps(result, default=str),
    }