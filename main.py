from fastapi import FastAPI, HTTPException, Query
from mangum import Mangum

from fintrust.query import get_insights, get_transactions


app = FastAPI(
    title="FinTrust Transaction Insights and Risk Monitoring API",
    version="1.0.0",
)


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


handler = Mangum(app)