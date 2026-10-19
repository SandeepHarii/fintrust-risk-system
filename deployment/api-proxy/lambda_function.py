
import base64
import hmac
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE = (
    "https://a1tia7lthb.execute-api.eu-north-1.amazonaws.com/prod"
)

MAX_BODY_BYTES = 5 * 1024 * 1024
UPSTREAM_TIMEOUT = 25

ALLOWED_ROUTES = {
    ("GET", "/health"),
    ("GET", "/transactions"),
    ("GET", "/insights"),
    ("GET", "/reports"),
    ("POST", "/upload"),
}

PROGRESS_ROUTE = re.compile(
    r"^/uploads/[A-Za-z0-9._~-]+/progress$"
)


def response(status_code, body="", headers=None, is_base64=False):
    return {
        "statusCode": status_code,
        "headers": headers or {},
        "body": body,
        "isBase64Encoded": is_base64,
    }


def valid_cloudfront_request(headers):
    expected = os.environ.get("PROXY_ORIGIN_SECRET", "")
    supplied = headers.get("x-origin-verify", "")

    if not expected or not supplied:
        return False

    return hmac.compare_digest(supplied, expected)


def cors_headers(origin):
    allowed_origins = {
        item.strip()
        for item in os.environ.get(
            "ALLOWED_ORIGINS",
            "http://localhost:5173",
        ).split(",")
        if item.strip()
    }

    if origin not in allowed_origins:
        return None

    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "300",
        "Vary": "Origin",
    }


def lambda_handler(event, context):
    headers = {
        str(key).lower(): str(value)
        for key, value in (event.get("headers") or {}).items()
        if value is not None
    }

    # Only accept requests carrying the private CloudFront header.
    if not valid_cloudfront_request(headers):
        return response(403, "Forbidden")

    origin = headers.get("origin")
    cors = cors_headers(origin) if origin else {}

    if origin and cors is None:
        return response(403, "Origin not allowed")

    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", "GET")
        .upper()
    )

    # Handle browser CORS preflight.
    if method == "OPTIONS":
        return response(204, "", cors)

    # Only accept requests under the CloudFront /api/ path.
    incoming_path = event.get("rawPath", "/")

    if not incoming_path.startswith("/api/"):
        return response(
            404,
            json.dumps({"message": "Route not found"}),
            {
                **cors,
                "Content-Type": "application/json",
            },
        )

    # Remove /api before forwarding to the existing API Gateway.
    path = incoming_path[4:]
    raw_query = event.get("rawQueryString", "")

    # Restrict requests to approved API routes.
    route_allowed = (
        (method, path) in ALLOWED_ROUTES
        or (
            method == "GET"
            and bool(PROGRESS_ROUTE.fullmatch(path))
        )
    )

    if not route_allowed:
        return response(
            404,
            json.dumps({"message": "Route not found"}),
            {
                **cors,
                "Content-Type": "application/json",
            },
        )

    # Retrieve the API key from the Lambda environment.
    api_key = os.environ.get("UPSTREAM_API_KEY")

    if not api_key:
        return response(
            500,
            json.dumps({"message": "Proxy configuration error"}),
            {
                **cors,
                "Content-Type": "application/json",
            },
        )

    # Decode and validate the incoming request body.
    body = event.get("body")

    if body is not None:
        try:
            if event.get("isBase64Encoded"):
                body_bytes = base64.b64decode(
                    body,
                    validate=True,
                )
            else:
                body_bytes = body.encode("utf-8")

        except (ValueError, UnicodeEncodeError, TypeError):
            return response(400, "Invalid request body", cors)

        if len(body_bytes) > MAX_BODY_BYTES:
            return response(
                413,
                json.dumps({"message": "Request body too large"}),
                {
                    **cors,
                    "Content-Type": "application/json",
                },
            )
    else:
        body_bytes = None

    content_type = headers.get("content-type", "")

    # Only accept CSV uploads.
    if method == "POST" and path == "/upload":
        if (
            content_type.split(";")[0].strip().lower()
            != "text/csv"
        ):
            return response(
                415,
                json.dumps({"message": "CSV content type required"}),
                {
                    **cors,
                    "Content-Type": "application/json",
                },
            )

    # Construct the upstream URL using only approved routes.
    url = f"{API_BASE}{path}"

    if raw_query:
        url += f"?{raw_query}"

    upstream_headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
    }

    if content_type:
        upstream_headers["Content-Type"] = content_type

    request = Request(
        url=url,
        data=body_bytes,
        headers=upstream_headers,
        method=method,
    )

    # Forward the request to the existing API Gateway.
    try:
        with urlopen(
            request,
            timeout=UPSTREAM_TIMEOUT,
        ) as upstream:
            upstream_body = upstream.read()
            status_code = upstream.status
            content_type_out = upstream.headers.get(
                "Content-Type",
                "application/json",
            )

    except HTTPError as error:
        upstream_body = error.read()
        status_code = error.code
        content_type_out = error.headers.get(
            "Content-Type",
            "application/json",
        )

    except (URLError, TimeoutError):
        return response(
            502,
            json.dumps({"message": "Upstream API unavailable"}),
            {
                **cors,
                "Content-Type": "application/json",
            },
        )

    # Preserve the upstream response.
    result_headers = {
        **cors,
        "Content-Type": content_type_out,
    }

    try:
        response_body = upstream_body.decode("utf-8")
        is_base64 = False

    except UnicodeDecodeError:
        response_body = base64.b64encode(
            upstream_body
        ).decode("ascii")
        is_base64 = True

    return response(
        status_code,
        response_body,
        result_headers,
        is_base64,
    )