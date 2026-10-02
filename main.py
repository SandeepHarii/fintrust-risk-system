import json
import logging
import uuid

import boto3
from fastapi import FastAPI, HTTPException, Query, Request, Response
from mangum import Mangum
from pydantic import BaseModel, Field

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


_s3 = boto3.client("s3")
_lambda = boto3.client("lambda")

RAW_BUCKET = "fintrust-prod-raw-transactions"
INGEST_FUNCTION_NAME = "fintrust-prod-ingest"
ALERT_FUNCTION_NAME = "fintrust-prod-alert"


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
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    try:
        return get_transactions(
            account_id=account_id,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve transactions.",
        )


@app.get("/insights")
def insights() -> dict:
    try:
        return get_insights()
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve insights.",
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

    object_key = f"uploads/{uuid.uuid4()}.csv"

    try:
        _s3.put_object(
            Bucket=RAW_BUCKET,
            Key=object_key,
            Body=csv_content,
            ContentType="text/csv",
        )

        s3_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {
                            "name": RAW_BUCKET,
                        },
                        "object": {
                            "key": object_key,
                        },
                    }
                }
            ]
        }

        _lambda.invoke(
            FunctionName=INGEST_FUNCTION_NAME,
            InvocationType="Event",
            Payload=json.dumps(s3_event).encode("utf-8"),
        )

        return Response(
            content=json.dumps(
                {
                    "message": "CSV upload accepted for asynchronous processing.",
                    "bucket": RAW_BUCKET,
                    "object_key": object_key,
                }
            ),
            status_code=202,
            media_type="application/json",
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to accept CSV upload.",
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
        raise HTTPException(
            status_code=500,
            detail="Unable to resolve alert.",
        )


handler = Mangum(app)