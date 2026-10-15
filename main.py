
import json
import logging
import uuid
from datetime import datetime

import boto3
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel, Field

from fintrust import dynamo
from fintrust.db import (
    flag_transaction,
    get_db_connection,
    mark_alert_failed,
    mark_alert_sent,
    resolve_alert,
)
from fintrust.query import (
    get_insights,
    get_transactions,
)


logger = logging.getLogger()
logger.setLevel(logging.INFO)


app = FastAPI(
    title="FinTrust Transaction Insights and Risk Monitoring API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-Api-Key",
        "X-Amz-Date",
        "Authorization",
        "X-Amz-Security-Token",
    ],
)


_s3 = boto3.client("s3")
_lambda = boto3.client("lambda")
_stepfunctions = boto3.client("stepfunctions")

RAW_BUCKET = "fintrust-prod-raw-transactions"
REPORT_BUCKET = "fintrust-prod-reports"

ALERT_FUNCTION_NAME = "fintrust-prod-alert"

UPLOAD_STATE_MACHINE_ARN = (
    "arn:aws:states:eu-north-1:051084216179:"
    "stateMachine:fintrust-prod-upload-workflow"
)


class FlagRequest(BaseModel):
    transaction_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=255)


class ResolveRequest(BaseModel):
    alert_id: str = Field(min_length=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/transactions")
def transactions(
    account_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    search: str | None = Query(default=None),
    risk_filter: str | None = Query(default=None),
    flag_filter: str | None = Query(default=None),
) -> dict:
    try:
        return get_transactions(
            account_id=account_id,
            page=page,
            page_size=page_size,
            search=search,
            risk_filter=risk_filter,
            flag_filter=flag_filter,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception:
        logger.exception("Unable to retrieve transactions.")
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve transactions.",
        )


@app.get("/insights")
def insights() -> dict:
    try:
        return get_insights()
    except Exception:
        logger.exception("Unable to retrieve insights.")
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve insights.",
        )


@app.get("/reports")
def reports() -> dict:
    """List monthly reports stored in S3 and generate download URLs."""
    try:
        paginator = _s3.get_paginator("list_objects_v2")

        report_items = []

        for page in paginator.paginate(
            Bucket=REPORT_BUCKET,
            Prefix="monthly/",
        ):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                parts = key.split("/")

                # Only include files in monthly/YYYY-MM/ directories.
                if len(parts) != 3 or parts[0] != "monthly":
                    continue

                filename = parts[2]
                period = parts[1]

                file_extension = filename.rsplit(".", 1)[-1].lower()

                if file_extension not in {"csv", "json"}:
                    continue

                # Validate the reporting month.
                try:
                    datetime.strptime(period, "%Y-%m")
                except ValueError:
                    continue

                download_url = _s3.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": REPORT_BUCKET,
                        "Key": key,
                    },
                    ExpiresIn=900,
                )

                report_items.append(
                    {
                        "period": period,
                        "filename": filename,
                        "format": file_extension.upper(),
                        "key": key,
                        "last_modified": obj["LastModified"].isoformat(),
                        "size_bytes": obj["Size"],
                        "download_url": download_url,
                        "download_url_expires_in": 900,
                    }
                )

        report_items.sort(
            key=lambda report: report["last_modified"],
            reverse=True,
        )

        return {
            "reports": report_items,
            "count": len(report_items),
        }

    except Exception:
        logger.exception("Unable to retrieve monthly reports.")
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve monthly reports.",
        )


@app.post("/upload", status_code=202)
async def upload(request: Request) -> Response:
    csv_content = await request.body()

    if not csv_content:
        raise HTTPException(
            status_code=400,
            detail="CSV upload body cannot be empty.",
        )

    content_type = request.headers.get("content-type", "").lower()

    if "text/csv" not in content_type:
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be text/csv.",
        )

    upload_id = str(uuid.uuid4())
    object_key = f"uploads/{upload_id}.csv"

    try:
        # Store the uploaded CSV in the raw S3 bucket.
        _s3.put_object(
            Bucket=RAW_BUCKET,
            Key=object_key,
            Body=csv_content,
            ContentType="text/csv",
        )

        # Create the upload's tracking record.
        dynamo.create_upload_tracking(
            upload_id=upload_id,
            bucket=RAW_BUCKET,
            object_key=object_key,
        )

        # Start asynchronous workflow orchestration.
        execution = _stepfunctions.start_execution(
            stateMachineArn=UPLOAD_STATE_MACHINE_ARN,
            name=upload_id,
            input=json.dumps(
                {
                    "upload_id": upload_id,
                    "bucket": RAW_BUCKET,
                    "object_key": object_key,
                }
            ),
        )

        execution_arn = execution["executionArn"]

        # Record that Step Functions has successfully started.
        try:
            dynamo.mark_workflow_started(
                upload_id=upload_id,
            )
        except Exception:
            logger.exception(
                "Unable to record workflow start for upload_id=%s",
                upload_id,
            )

        # Store the execution ARN for tracking and troubleshooting.
        try:
            dynamo.set_upload_execution_arn(
                upload_id=upload_id,
                execution_arn=execution_arn,
            )
        except Exception:
            # The workflow has already started, so do not report
            # the upload as failed because this metadata update failed.
            logger.exception(
                "Unable to save execution ARN for upload_id=%s",
                upload_id,
            )

        return Response(
            content=json.dumps(
                {
                    "message": "CSV upload accepted for asynchronous processing.",
                    "upload_id": upload_id,
                    "bucket": RAW_BUCKET,
                    "object_key": object_key,
                    "execution_arn": execution_arn,
                    "progress_url": f"/uploads/{upload_id}/progress",
                }
            ),
            status_code=202,
            media_type="application/json",
        )

    except Exception as exc:
        logger.exception(
            "Unable to start CSV upload workflow for upload_id=%s",
            upload_id,
        )

        # Mark the upload as failed if its tracking record exists.
        try:
            dynamo.mark_upload_failed(
                upload_id=upload_id,
                reason=str(exc),
            )
        except Exception:
            logger.exception(
                "Unable to mark upload as failed for upload_id=%s",
                upload_id,
            )

        raise HTTPException(
            status_code=500,
            detail="Unable to accept CSV upload.",
        ) from exc


@app.get("/uploads/{upload_id}/progress")
def upload_progress(upload_id: str) -> dict:
    try:
        tracking = dynamo.get_upload_tracking(upload_id)

        if not tracking:
            raise HTTPException(
                status_code=404,
                detail="Upload tracking record not found.",
            )

        return tracking

    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unable to retrieve upload progress for upload_id=%s",
            upload_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve upload progress.",
        )


@app.post("/flag")
def flag(request: FlagRequest) -> dict:
    try:
        with get_db_connection() as conn:
            alert = flag_transaction(
                conn=conn,
                transaction_id=request.transaction_id,
                reason=request.reason,
            )

        try:
            response = _lambda.invoke(
                FunctionName=ALERT_FUNCTION_NAME,
                InvocationType="RequestResponse",
                Payload=json.dumps(alert).encode("utf-8"),
            )

            if response.get("FunctionError"):
                with get_db_connection() as conn:
                    mark_alert_failed(
                        conn=conn,
                        alert_id=alert["alert_id"],
                    )

                raise HTTPException(
                    status_code=502,
                    detail="Alert email failed to send.",
                )

            with get_db_connection() as conn:
                sent_alert = mark_alert_sent(
                    conn=conn,
                    alert_id=alert["alert_id"],
                )

            return sent_alert

        except HTTPException:
            raise
        except Exception:
            logger.exception(
                "D1 /flag alert dispatch failed for alert_id=%s",
                alert.get("alert_id"),
            )

            with get_db_connection() as conn:
                mark_alert_failed(
                    conn=conn,
                    alert_id=alert["alert_id"],
                )

            raise HTTPException(
                status_code=502,
                detail="Unable to dispatch alert.",
            )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "D1 /flag transaction processing failed for transaction_id=%s",
            request.transaction_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to flag transaction.",
        )


@app.post("/resolve")
def resolve(request: ResolveRequest) -> dict:
    try:
        with get_db_connection() as conn:
            return resolve_alert(
                conn=conn,
                alert_id=request.alert_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except Exception:
        logger.exception("Unable to resolve alert.")
        raise HTTPException(
            status_code=500,
            detail="Unable to resolve alert.",
        )


handler = Mangum(app)