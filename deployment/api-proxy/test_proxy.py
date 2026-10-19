
import os
import unittest
from unittest.mock import Mock, patch

import lambda_function


class ProxySecurityTests(unittest.TestCase):

    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "PROXY_ORIGIN_SECRET": "test-secret",
                "UPSTREAM_API_KEY": "test-api-key",
                "ALLOWED_ORIGINS": "http://localhost:5173",
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def make_event(self, method="GET", path="/health", **headers):
        return {
            "rawPath": f"/api{path}",
            "rawQueryString": "",
            "headers": {
                "origin": "http://localhost:5173",
                "x-origin-verify": "test-secret",
                **headers,
            },
            "requestContext": {
                "http": {"method": method}
            },
            "body": None,
            "isBase64Encoded": False,
        }

    def mock_upstream(self, body=b'{"status":"ok"}'):
        upstream = Mock()
        upstream.__enter__ = Mock(return_value=upstream)
        upstream.__exit__ = Mock(return_value=False)
        upstream.read.return_value = body
        upstream.status = 200
        upstream.headers.get.return_value = "application/json"
        return upstream

    def test_missing_secret_is_rejected(self):
        os.environ["PROXY_ORIGIN_SECRET"] = ""

        result = lambda_function.lambda_handler(
            self.make_event(),
            None,
        )

        self.assertEqual(result["statusCode"], 403)

    def test_incorrect_secret_is_rejected(self):
        event = self.make_event()
        event["headers"]["x-origin-verify"] = "wrong-secret"

        result = lambda_function.lambda_handler(event, None)

        self.assertEqual(result["statusCode"], 403)

    def test_preflight_is_accepted(self):
        result = lambda_function.lambda_handler(
            self.make_event("OPTIONS"),
            None,
        )

        self.assertEqual(result["statusCode"], 204)

    def test_unapproved_origin_is_rejected(self):
        event = self.make_event()
        event["headers"]["origin"] = "https://unknown.example.com"

        result = lambda_function.lambda_handler(event, None)

        self.assertEqual(result["statusCode"], 403)

    def test_unapproved_route_is_rejected(self):
        result = lambda_function.lambda_handler(
            self.make_event(path="/admin"),
            None,
        )

        self.assertEqual(result["statusCode"], 404)

    def test_missing_api_prefix_is_rejected(self):
        event = self.make_event()
        event["rawPath"] = "/transactions"

        result = lambda_function.lambda_handler(event, None)

        self.assertEqual(result["statusCode"], 404)

    def test_upload_requires_csv_content_type(self):
        result = lambda_function.lambda_handler(
            self.make_event(
                "POST",
                "/upload",
                **{"content-type": "application/json"},
            ),
            None,
        )

        self.assertEqual(result["statusCode"], 415)

    def test_oversized_upload_is_rejected(self):
        event = self.make_event(
            "POST",
            "/upload",
            **{"content-type": "text/csv"},
        )
        event["body"] = "x" * (
            lambda_function.MAX_BODY_BYTES + 1
        )

        result = lambda_function.lambda_handler(event, None)

        self.assertEqual(result["statusCode"], 413)

    @patch("lambda_function.urlopen")
    def test_get_request_forwards_api_key_and_query(self, mock_urlopen):
        mock_urlopen.return_value = self.mock_upstream()

        event = self.make_event(path="/transactions")
        event["rawQueryString"] = "page=1&page_size=20"

        result = lambda_function.lambda_handler(event, None)

        request = mock_urlopen.call_args.args[0]

        self.assertEqual(result["statusCode"], 200)
        self.assertIn(
            "/prod/transactions?page=1&page_size=20",
            request.full_url,
        )
        self.assertEqual(
            request.get_header("X-api-key"),
            "test-api-key",
        )

    @patch("lambda_function.urlopen")
    def test_csv_upload_forwards_body_and_content_type(self, mock_urlopen):
        mock_urlopen.return_value = self.mock_upstream(
            b'{"message":"accepted"}'
        )

        event = self.make_event(
            "POST",
            "/upload",
            **{"content-type": "text/csv"},
        )
        event["body"] = "transaction_id,amount\nTX001,100.00"

        result = lambda_function.lambda_handler(event, None)

        request = mock_urlopen.call_args.args[0]

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(
            request.full_url,
            f"{lambda_function.API_BASE}/upload",
        )
        self.assertEqual(
            request.data,
            b"transaction_id,amount\nTX001,100.00",
        )
        self.assertEqual(
            request.get_header("Content-type"),
            "text/csv",
        )

    @patch("lambda_function.urlopen")
    def test_progress_route_is_forwarded(self, mock_urlopen):
        mock_urlopen.return_value = self.mock_upstream()

        event = self.make_event(
            path="/uploads/UP-20261017-001/progress"
        )

        result = lambda_function.lambda_handler(event, None)

        request = mock_urlopen.call_args.args[0]

        self.assertEqual(result["statusCode"], 200)
        self.assertTrue(
            request.full_url.endswith(
                "/uploads/UP-20261017-001/progress"
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)