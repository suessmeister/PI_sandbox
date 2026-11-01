from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from target import run_target


class TargetTests(unittest.TestCase):
    def test_multipart_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "test.jpg"
            image.write_bytes(b"image bytes")
            body = {"request_id": "request-1", "response": "answer"}
            def post(url, **kwargs):
                self.assertEqual(url, "http://localhost:8001/run")
                self.assertEqual(kwargs["data"], {"prompt": "trusted prompt"})
                name, handle, mime = kwargs["files"]["image"]
                self.assertEqual((name, handle.read(), mime), ("test.jpg", b"image bytes", "image/jpeg"))
                self.assertEqual(kwargs["timeout"], 200)
                return httpx.Response(200, json=body, request=httpx.Request("POST", url))
            with patch("target.httpx.post", side_effect=post):
                self.assertEqual(run_target("trusted prompt", image,
                    target_url="http://localhost:8001/run", timeout=200), body)
            self.assertEqual(list(Path(directory).iterdir()), [image])

    def test_http_and_contract_errors_propagate(self):
        for status, body in [(502, {"detail": "upstream failure"}),
                             (200, {"request_id": "id", "response": " "}),
                             (200, {"request_id": "id", "response": 123}),
                             (200, {"response": "answer"})]:
            with self.subTest(status=status, body=body), tempfile.TemporaryDirectory() as directory:
                image = Path(directory) / "image.png"
                image.write_bytes(b"image bytes")
                response = httpx.Response(status, json=body,
                                          request=httpx.Request("POST", "http://localhost/run"))
                with patch("target.httpx.post", return_value=response):
                    with self.assertRaises((ValueError, httpx.HTTPStatusError)):
                        run_target("prompt", image)
