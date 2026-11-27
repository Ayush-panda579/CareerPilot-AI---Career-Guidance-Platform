import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

_test_directory = tempfile.TemporaryDirectory()
os.environ.update(
    {
        "DATABASE_URL": "",
        "POSTGRES_URL": "",
        "VERCEL": "",
        "SECRET_KEY": "test-only-secret",
        "GEMINI_API_KEY": "",
        "SQLITE_PATH": str(Path(_test_directory.name) / "smoke-test.db"),
    }
)

import app as app_module
from services.gemini_service import GeminiConfigurationError

app_module.app.config.update(
    TESTING=True,
    UPLOAD_FOLDER=str(Path(_test_directory.name) / "uploads"),
)


class FlaskSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_public_pages_and_static_assets(self):
        for route in ("/", "/features", "/roadmap", "/careers", "/contact",
                      "/register", "/login"):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

        css = self.client.get("/static/css/style.css", buffered=True)
        self.assertEqual(css.status_code, 200)
        css.close()

        favicon = self.client.get(
            "/favicon.ico",
            follow_redirects=True,
            buffered=True,
        )
        self.assertEqual(favicon.status_code, 200)
        favicon.close()
        self.assertEqual(self.client.get("/missing-page").status_code, 404)

    def test_vercel_entrypoint_and_rewrite_configuration(self):
        config = json.loads((PROJECT_ROOT / "vercel.json").read_text())
        self.assertEqual(
            config["rewrites"][0]["destination"],
            "/api/index",
        )
        self.assertIn("templates/**", config["functions"]["api/index.py"]["includeFiles"])

        entrypoint_path = PROJECT_ROOT / "api" / "index.py"
        spec = importlib.util.spec_from_file_location(
            "vercel_entrypoint",
            entrypoint_path,
        )
        entrypoint = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entrypoint)
        self.assertIs(entrypoint.app, app_module.app)

    def test_account_contact_and_protected_pages(self):
        response = self.client.post(
            "/register",
            data={
                "username": "smoke-user",
                "email": "smoke-user@example.test",
                "password": "test-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

        duplicate = self.client.post(
            "/register",
            data={
                "username": "smoke-user",
                "email": "another@example.test",
                "password": "test-password",
            },
        )
        self.assertEqual(duplicate.status_code, 200)

        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(self.client.get("/upload").status_code, 302)
        self.assertEqual(self.client.get("/chatbot").status_code, 302)

        login = self.client.post(
            "/login",
            data={"username": "smoke-user", "password": "test-password"},
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/upload").status_code, 200)
        self.assertEqual(self.client.get("/chatbot").status_code, 200)

        contact = self.client.post(
            "/contact",
            data={
                "name": "Smoke Test",
                "email": "smoke-contact@example.test",
                "message": "Smoke test message",
            },
            follow_redirects=True,
        )
        self.assertEqual(contact.status_code, 200)
        self.assertIn(b"received", contact.data.lower())

        logout = self.client.get("/logout")
        self.assertEqual(logout.status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_upload_validation_and_local_storage(self):
        registration = self.client.post(
            "/register",
            data={
                "username": "upload-user",
                "email": "upload-user@example.test",
                "password": "test-password",
            },
        )
        self.assertEqual(registration.status_code, 302)

        login = self.client.post(
            "/login",
            data={"username": "upload-user", "password": "test-password"},
        )
        self.assertEqual(login.status_code, 302)
        self.assertIn("/dashboard", login.headers["Location"])

        invalid = self.client.post(
            "/upload",
            data={"resume": (io.BytesIO(b"not a resume"), "resume.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid.status_code, 302)

        valid = self.client.post(
            "/upload",
            data={"resume": (io.BytesIO(b"sample resume"), "resume.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(valid.status_code, 302)
        self.assertIn("/dashboard", valid.headers["Location"])
        uploaded_files = list(Path(app_module.app.config["UPLOAD_FOLDER"]).iterdir())
        self.assertEqual(len(uploaded_files), 1)

        with patch.dict(os.environ, {"VERCEL": "1", "S3_BUCKET": ""}):
            unconfigured = self.client.post(
                "/upload",
                data={"resume": (io.BytesIO(b"sample resume"), "another.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(unconfigured.status_code, 503)

    def test_chatbot_validation_configuration_and_response(self):
        self.assertEqual(
            self.client.post("/chatbot/ask", json={}).status_code,
            400,
        )

        with patch.object(
            app_module,
            "generate_ai_response",
            side_effect=GeminiConfigurationError("Gemini is not configured."),
        ):
            unavailable = self.client.post(
                "/chatbot/ask",
                json={"message": "How do I prepare for an interview?"},
            )
        self.assertEqual(unavailable.status_code, 503)

        with patch.object(
            app_module,
            "generate_ai_response",
            return_value="Practice concise answers.",
        ):
            response = self.client.post(
                "/chatbot/ask",
                json={"message": "How do I prepare for an interview?"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["response"], "Practice concise answers.")


if __name__ == "__main__":
    unittest.main()
