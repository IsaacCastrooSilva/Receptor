import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import os
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch
import wave

API_AVAILABLE = all(
    importlib.util.find_spec(name) is not None
    for name in ("fastapi", "httpx", "python_multipart")
)
if API_AVAILABLE:
    from fastapi.testclient import TestClient
    from receptor.api import MAX_AUDIO_BYTES, MAX_REQUEST_BYTES, create_app
else:
    TestClient = None


def wav_bytes(*, channels=1, rate=16000, frames=160):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x01\x00" * frames * channels)
    return buffer.getvalue()


@unittest.skipIf(TestClient is None, 'Instale o extra api e httpx para testar a API.')
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.paths = []

        def recognize(path, model, language):
            self.assertTrue(path.is_file())
            self.assertEqual(path.name, "audio.wav")
            self.assertEqual(language, "portuguese")
            self.paths.append(path)
            return "Preciso de água."

        self.transcriber = Mock(side_effect=recognize)
        self.client = self.enterContext(TestClient(create_app(self.transcriber)))

    def upload(self, content=None, consent="true", filename="recording.wav"):
        data = {} if consent is None else {"consent": consent}
        return self.client.post(
            "/api/transcriptions", data=data,
            files={"file": (filename, wav_bytes() if content is None else content, "audio/wav")},
        )

    def test_health_does_not_load_model_and_is_not_cached(self):
        with patch("receptor.api._default_transcriber") as recognize:
            with TestClient(create_app()) as client:
                response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "model": "openai/whisper-tiny"})
        self.assertEqual(response.headers["cache-control"], "no-store")
        recognize.assert_not_called()

    def test_environment_selects_model_without_loading_it(self):
        with patch.dict(os.environ, {"RECEPTOR_MODEL": "artifacts/custom-model"}):
            with TestClient(create_app(self.transcriber)) as client:
                self.assertEqual(client.get("/api/health").json()["model"], "artifacts/custom-model")
                response = client.post(
                    "/api/transcriptions", data={"consent": "true"},
                    files={"file": ("audio.wav", wav_bytes(), "audio/wav")},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transcriber.call_args.args[1], "artifacts/custom-model")

    def test_transcription_requires_review_and_removes_temporary_audio(self):
        response = self.upload(filename="../../PRIVATE_AUDIO.wav")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"text": "Preciso de água.", "review_required": True})
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(len(self.paths), 1)
        self.assertFalse(self.paths[0].exists())
        self.assertFalse(self.paths[0].parent.exists())

    def test_consent_is_required_before_creating_processing_files(self):
        for consent in (None, "false", "1", "yes", "PRIVATE_CONSENT"):
            with self.subTest(consent=consent), patch("receptor.api.tempfile.TemporaryDirectory") as temp:
                response = self.upload(consent=consent)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertNotIn("PRIVATE_CONSENT", response.text)
                temp.assert_not_called()
        self.transcriber.assert_not_called()

    def test_upload_parser_does_not_spool_unconsented_or_oversized_audio_to_disk(self):
        with patch("tempfile.SpooledTemporaryFile.rollover") as rollover:
            denied = self.upload(b"\x00" * (MAX_AUDIO_BYTES + 1), consent="false")
            oversized = self.upload(b"\x00" * (MAX_AUDIO_BYTES + 1))
        self.assertEqual(denied.status_code, 422)
        self.assertEqual(oversized.status_code, 413)
        rollover.assert_not_called()
        self.transcriber.assert_not_called()

    def test_invalid_audio_is_rejected_before_inference(self):
        for payload in (b"", b"PRIVATE_AUDIO_DATA", wav_bytes(channels=2), wav_bytes(rate=8000)):
            with self.subTest(size=len(payload)):
                response = self.upload(payload)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("PRIVATE_AUDIO_DATA", response.text)
        self.transcriber.assert_not_called()

    def test_malformed_multipart_returns_sanitized_422(self):
        for content_type, body in (
            ("multipart/form-data", b"PRIVATE_MULTIPART"),
            ("multipart/form-data; boundary=example", b"PRIVATE_MULTIPART"),
            ("multipart/form-data; boundary=example", b"--example\r\nmalformed\r\n"),
            ("application/json", b'{"file":"PRIVATE_MULTIPART"}'),
        ):
            with self.subTest(content_type=content_type, size=len(body)):
                response = self.client.post(
                    "/api/transcriptions", content=body,
                    headers={"content-type": content_type},
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertNotIn("PRIVATE_MULTIPART", response.text)
        self.transcriber.assert_not_called()

    def test_inference_errors_are_sanitized_and_temporary_audio_is_removed(self):
        def fail(path, model, language):
            self.paths.append(path)
            raise RuntimeError("PRIVATE_MODEL_ERROR and PRIVATE_TRANSCRIPTION")

        self.transcriber.side_effect = fail
        response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("PRIVATE", response.text)
        self.assertFalse(self.paths[0].exists())
        self.assertFalse(self.paths[0].parent.exists())
        self.transcriber.side_effect = None
        self.transcriber.return_value = "Tudo bem."
        self.assertEqual(self.upload().status_code, 200)

    def test_file_size_limit_is_enforced_before_processing(self):
        with patch("receptor.api.tempfile.TemporaryDirectory") as temp:
            response = self.upload(b"\x00" * (MAX_AUDIO_BYTES + 1))
        self.assertEqual(response.status_code, 413)
        temp.assert_not_called()
        self.transcriber.assert_not_called()

    def test_raw_request_size_limit_rejects_oversized_content_length(self):
        response = self.client.post(
            "/api/transcriptions", content=b"small",
            headers={"content-length": str(MAX_REQUEST_BYTES + 1)},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.transcriber.assert_not_called()

    def test_chunked_request_size_limit_cannot_be_bypassed_without_content_length(self):
        application = create_app(self.transcriber)
        messages = iter([
            {"type": "http.request", "body": b"x" * MAX_REQUEST_BYTES, "more_body": True},
            {"type": "http.request", "body": b"x", "more_body": False},
        ])
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": "/api/transcriptions",
            "raw_path": b"/api/transcriptions", "query_string": b"", "headers": [],
            "server": ("testserver", 80), "client": ("testclient", 1234),
        }
        asyncio.run(application(scope, receive, send))
        self.assertEqual(sent[0]["status"], 413)
        self.transcriber.assert_not_called()

    def test_busy_inference_returns_429_without_blocking_health(self):
        started = Event()
        release = Event()

        def slow_recognize(path, model, language):
            started.set()
            if not release.wait(timeout=10):
                raise TimeoutError
            return "Pronto."

        self.transcriber.side_effect = slow_recognize
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.upload)
            try:
                self.assertTrue(started.wait(timeout=5))
                busy = self.upload()
                self.assertEqual(busy.status_code, 429)
                self.assertEqual(busy.headers["retry-after"], "2")
                self.assertEqual(self.client.get("/api/health").status_code, 200)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5).status_code, 200)
        self.assertEqual(self.upload().status_code, 200)


@unittest.skipIf(TestClient is None, 'Instale o extra api e httpx para testar a API.')
class FrontendServingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.frontend = self.root / "frontend"
        self.frontend.mkdir()
        (self.frontend / "index.html").write_text("<h1>Receptor PWA</h1>", encoding="utf-8")
        (self.frontend / "sw.js").write_text("/* service worker */", encoding="utf-8")
        (self.frontend / "assets").mkdir()
        (self.frontend / "assets" / "app.js").write_text("/* frontend bundle */", encoding="utf-8")
        (self.frontend / "404.html").write_text("<p>Frontend 404</p>", encoding="utf-8")

    def test_serves_build_and_api_with_separate_cache_policies(self):
        with TestClient(create_app(frontend_dir=self.frontend)) as client:
            for path in ("/", "/index.html"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Receptor PWA", response.text)
                self.assertEqual(response.headers["cache-control"], "no-cache")
            worker = client.get("/sw.js")
            self.assertEqual(worker.status_code, 200)
            self.assertEqual(worker.headers["cache-control"], "no-cache")
            asset = client.get("/assets/app.js")
            self.assertEqual(asset.status_code, 200)
            self.assertNotEqual(asset.headers.get("cache-control"), "no-store")
            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.headers["cache-control"], "no-store")

    def test_unknown_api_is_json_and_never_serves_frontend_files(self):
        (self.frontend / "api").mkdir()
        (self.frontend / "api" / "private.txt").write_text("PRIVATE_STATIC_DATA", encoding="utf-8")
        with TestClient(create_app(frontend_dir=self.frontend)) as client:
            for path in ("/api", "/api/missing", "/api/private.txt"):
                response = client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertIn("application/json", response.headers["content-type"])
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertIn("detail", response.json())
                self.assertNotIn("PRIVATE_STATIC_DATA", response.text)
            self.assertEqual(client.get("/unknown-client-route").status_code, 404)

    def test_missing_frontend_build_keeps_api_available(self):
        for directory in (self.root / "absent", self.root / "empty"):
            if directory.name == "empty":
                directory.mkdir()
            with self.subTest(directory=directory.name):
                with TestClient(create_app(frontend_dir=directory)) as client:
                    self.assertEqual(client.get("/api/health").status_code, 200)
                    self.assertEqual(client.get("/").status_code, 404)

    def test_environment_selects_build_and_explicit_directory_takes_precedence(self):
        with patch.dict(os.environ, {"RECEPTOR_FRONTEND_DIR": str(self.frontend)}):
            with TestClient(create_app()) as client:
                self.assertIn("Receptor PWA", client.get("/").text)
            with TestClient(create_app(frontend_dir=self.root / "missing")) as client:
                self.assertEqual(client.get("/").status_code, 404)

    def test_static_mount_does_not_expose_audio_outside_build(self):
        (self.root / "audio").mkdir()
        (self.root / "audio" / "private.wav").write_bytes(b"PRIVATE_AUDIO_DATA")
        with TestClient(create_app(frontend_dir=self.frontend)) as client:
            for path in ("/audio/private.wav", "/%2e%2e/audio/private.wav", "/audio.wav"):
                response = client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("PRIVATE_AUDIO_DATA", response.text)


if __name__ == "__main__":
    unittest.main()
