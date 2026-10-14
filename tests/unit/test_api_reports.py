
import boto3
import pytest
from fastapi import HTTPException
from moto import mock_aws

import main


REPORT_BUCKET = "fintrust-test-reports"


@pytest.fixture
def reports_s3(monkeypatch):
    """Provide an isolated Moto S3 bucket for report API tests."""
    with mock_aws():
        s3 = boto3.client(
            "s3",
            region_name="eu-north-1",
        )

        s3.create_bucket(
            Bucket=REPORT_BUCKET,
            CreateBucketConfiguration={
                "LocationConstraint": "eu-north-1",
            },
        )

        monkeypatch.setattr(main, "_s3", s3)
        monkeypatch.setattr(main, "REPORT_BUCKET", REPORT_BUCKET)

        yield s3


def test_list_monthly_reports_returns_csv_and_json(reports_s3):
    reports_s3.put_object(
        Bucket=REPORT_BUCKET,
        Key="monthly/2026-10/fintrust-risk-report.csv",
        Body="account_id,risk_score\n123,80\n",
        ContentType="text/csv",
    )

    reports_s3.put_object(
        Bucket=REPORT_BUCKET,
        Key="monthly/2026-10/fintrust-risk-report.json",
        Body='{"report": "fintrust-risk-report"}',
        ContentType="application/json",
    )

    data = main.reports()

    assert data["count"] == 2
    assert len(data["reports"]) == 2

    formats = {
        report["format"]
        for report in data["reports"]
    }

    assert formats == {"CSV", "JSON"}

    for report in data["reports"]:
        assert report["period"] == "2026-10"
        assert report["download_url"]
        assert report["download_url_expires_in"] == 900
        assert report["size_bytes"] > 0
        assert report["last_modified"]


def test_list_monthly_reports_ignores_invalid_objects(reports_s3):
    valid_key = (
        "monthly/2026-10/fintrust-risk-report.csv"
    )

    invalid_keys = [
        "monthly/2026-10/fintrust-risk-report.txt",
        "monthly/invalid/fintrust-risk-report.csv",
        "monthly/2026-13/fintrust-risk-report.csv",
        "monthly/2026-10/nested/fintrust-risk-report.csv",
        "other/2026-10/fintrust-risk-report.csv",
    ]

    reports_s3.put_object(
        Bucket=REPORT_BUCKET,
        Key=valid_key,
        Body="account_id\n123\n",
    )

    for key in invalid_keys:
        reports_s3.put_object(
            Bucket=REPORT_BUCKET,
            Key=key,
            Body="ignored",
        )

    data = main.reports()

    assert data["count"] == 1
    assert len(data["reports"]) == 1
    assert data["reports"][0]["key"] == valid_key


def test_list_monthly_reports_returns_empty_list(reports_s3):
    data = main.reports()

    assert data == {
        "reports": [],
        "count": 0,
    }


def test_list_monthly_reports_handles_s3_errors(
    reports_s3,
    monkeypatch,
):
    def raise_s3_error(*args, **kwargs):
        raise RuntimeError("Simulated S3 failure")

    monkeypatch.setattr(
        main._s3,
        "get_paginator",
        raise_s3_error,
    )

    with pytest.raises(HTTPException) as exc_info:
        main.reports()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == (
        "Unable to retrieve monthly reports."
    )