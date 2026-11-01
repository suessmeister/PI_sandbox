"""Exercise the real SDK parser against a local HTTP server, without API calls."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from pathlib import Path
import tempfile

from call_logging import CALL_DIRECTORY
import unittest
from unittest.mock import patch

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from models import ask


class Reply(BaseModel):
    answer: str


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                cls.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                body = json.dumps(cls.response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        type(self).requests = []
        type(self).response = {
            "id": "resp_test", "object": "response", "created_at": 0,
            "model": "mock", "status": "completed",
            "output": [{"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": '{"answer":"yes"}', "annotations": []}]}],
        }

    def call(self, provider="openai"):
        def local_client(**kwargs):
            self.client_options = kwargs.copy()
            kwargs["base_url"] = f"http://127.0.0.1:{self.server.server_port}/v1"
            return OpenAI(**kwargs)
        with patch("models.OpenAI", side_effect=local_client), patch("models.load_dotenv"), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-openai", "OPENROUTER_API_KEY": "test-router"}):
            return ask(Reply, "Return a structured answer.", {"input": "test"}, model_name="mock", provider=provider)

    def test_sdk_sends_schema_and_parses_answer_for_both_providers(self):
        for provider, key, url in (("openai", "test-openai", "https://api.openai.com/v1"),
                                   ("openrouter", "test-router", "https://openrouter.ai/api/v1")):
            with self.subTest(provider=provider):
                self.assertEqual(self.call(provider).answer, "yes")
                self.assertEqual(self.client_options["api_key"], key)
                self.assertEqual(self.client_options["base_url"], url)
                request = self.requests[-1]
                self.assertFalse(request["store"])
                self.assertEqual(request["text"]["format"]["type"], "json_schema")
                self.assertTrue(request["text"]["format"]["strict"])
                self.assertNotIn("tools", request)

    def test_refusal_or_incomplete_answer_stops_feedback(self):
        self.response["output"][0]["content"] = [{"type": "refusal", "refusal": "declined"}]
        with self.assertRaisesRegex(ValueError, "refused"):
            self.call()
        self.response["status"] = "incomplete"
        with self.assertRaisesRegex(ValueError, "complete structured"):
            self.call()

    def test_schema_violation_is_not_accepted(self):
        self.response["output"][0]["content"][0]["text"] = '{"wrong_key": "yes"}'
        with self.assertRaises(ValidationError):
            self.call()

    def test_call_log_records_inputs_attempts_response_and_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            token = CALL_DIRECTORY.set(Path(directory))
            try:
                self.call()
            finally:
                CALL_DIRECTORY.reset(token)
            events = [json.loads(line) for line in (Path(directory) / "llm_calls.jsonl").read_text().splitlines()]
            self.assertEqual([e["event"] for e in events],
                             ["start", "attempt_start", "attempt_response", "response", "end"])
            self.assertEqual(len({e["call_id"] for e in events}), 1)
            self.assertEqual(events[0]["request"]["context"], {"input": "test"})
            self.assertEqual(events[3]["response_id"], "resp_test")
            self.assertGreaterEqual(events[-1]["elapsed_seconds"], 0)
            text = (Path(directory) / "llm_calls.log").read_text()
            self.assertNotIn("test-openai", text)

    def test_refusal_is_logged_as_error(self):
        self.response["output"][0]["content"] = [{"type": "refusal", "refusal": "declined"}]
        with tempfile.TemporaryDirectory() as directory:
            token = CALL_DIRECTORY.set(Path(directory))
            try:
                with self.assertRaises(ValueError):
                    self.call()
            finally:
                CALL_DIRECTORY.reset(token)
            events = [json.loads(line) for line in (Path(directory) / "llm_calls.jsonl").read_text().splitlines()]
            self.assertEqual(events[-1]["event"], "error")
            self.assertEqual(events[-1]["error_type"], "ValueError")

    def test_unknown_provider_fails_before_request(self):
        with self.assertRaisesRegex(ValueError, "provider"):
            self.call("ollama")
        self.assertEqual(self.requests, [])
