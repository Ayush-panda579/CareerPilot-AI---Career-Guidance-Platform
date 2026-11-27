import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

_test_directory = tempfile.TemporaryDirectory()
os.environ.update(
    {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "test-publishable-key",
        "SUPABASE_ANON_KEY": "test-anon-key",
        "VERCEL": "",
        "SECRET_KEY": "test-only-secret",
        "SUPABASE_JWT_SECRET": "",
        "GEMINI_API_KEY": "",
    }
)

import app as app_module
import db
from services.gemini_service import GeminiConfigurationError

app_module.app.config.update(
    TESTING=True,
    UPLOAD_FOLDER=str(Path(_test_directory.name) / "uploads"),
)


class FlaskSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.user = SimpleNamespace(
            id="a4a4d19e-a75e-4df6-9873-161f2b457ceb",
            email="smoke-user@example.test",
            user_metadata={"display_name": "Smoke User"},
        )
        self.auth_session = db.AuthSession(
            "test-access-token", "test-refresh-token", 3600
        )
        self.auth_result = db.AuthResult(self.user, self.auth_session)
        self.auth_context = {
            "user": self.user,
            "client": object(),
            "session": self.auth_session,
        }
        self.patches = [
            patch.object(db, "authenticate_session", return_value=self.auth_context),
            patch.object(db, "sign_up", return_value=db.AuthResult(None, None)),
            patch.object(db, "sign_in", return_value=self.auth_result),
            patch.object(db, "sign_out"),
            patch.object(
                db,
                "get_dashboard_data",
                return_value={
                    "profile": {"display_name": "Smoke User"},
                    "resumes": [],
                    "progress": [],
                },
            ),
            patch.object(db, "create_contact_message"),
            patch.object(db, "create_resume_upload", return_value={"id": "resume-id"}),
            patch.object(db, "update_resume_upload_status", return_value=True),
            patch.object(db, "create_learning_progress", return_value={"id": "goal-id"}),
            patch.object(db, "update_learning_progress", return_value={"id": "goal-id"}),
            patch.object(db, "delete_learning_progress", return_value=True),
        ]
        for patcher in self.patches:
            patcher.start()
        self.addCleanup(self._stop_patches)

    def _stop_patches(self):
        for patcher in reversed(self.patches):
            patcher.stop()

    def _sign_in(self):
        response = self.client.post(
            "/login",
            data={"email": "smoke-user@example.test", "password": "test-password"},
        )
        self.assertEqual(response.status_code, 302)
        return response

    def test_public_pages_and_static_assets(self):
        for route in (
            "/", "/features", "/roadmap", "/careers", "/contact", "/about",
            "/register", "/login", "/resume-analyzer", "/skill-extractor",
            "/ai-mentor", "/job-matcher", "/resources", "/blog",
            "/learning-hub", "/interview-prep", "/help-center",
            "/privacy-policy", "/terms",
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

        css = self.client.get("/static/css/style.css", buffered=True)
        self.assertEqual(css.status_code, 200)
        css.close()

        favicon = self.client.get("/favicon.ico", follow_redirects=True, buffered=True)
        self.assertEqual(favicon.status_code, 200)
        favicon.close()
        self.assertEqual(self.client.get("/missing-page").status_code, 404)

    def test_vercel_entrypoint_and_rewrite_configuration(self):
        config = json.loads((PROJECT_ROOT / "vercel.json").read_text())
        self.assertEqual(config["rewrites"][0]["destination"], "/api/index")
        self.assertIn("templates/**", config["functions"]["api/index.py"]["includeFiles"])

        entrypoint_path = PROJECT_ROOT / "api" / "index.py"
        spec = importlib.util.spec_from_file_location("vercel_entrypoint", entrypoint_path)
        entrypoint = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entrypoint)
        self.assertIs(entrypoint.app, app_module.app)

    def test_registration_requires_valid_fields_and_sends_confirmation(self):
        invalid = self.client.post(
            "/register",
            data={"display_name": "Smoke User", "email": "invalid", "password": "test-password"},
        )
        self.assertEqual(invalid.status_code, 400)

        response = self.client.post(
            "/register",
            data={
                "display_name": "Smoke User",
                "email": "smoke-user@example.test",
                "password": "test-password",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"confirmation link", response.data.lower())
        db.sign_up.assert_called_once()
        self.assertTrue(db.sign_up.call_args.args[3])

    def test_authentication_rate_limit_rejects_excess_requests(self):
        with patch.object(app_module, "_is_auth_rate_limited", return_value=True):
            response = self.client.post(
                "/login",
                data={"email": "smoke-user@example.test", "password": "test-password"},
            )
        self.assertEqual(response.status_code, 429)
        db.sign_in.assert_not_called()

    def test_dashboard_renders_persisted_rows_and_realtime_feed(self):
        self._sign_in()
        db.get_dashboard_data.return_value = {
            "profile": {"display_name": "Smoke User"},
            "resumes": [
                {
                    "id": "resume-id",
                    "original_filename": "career-resume.pdf",
                    "status": "ready",
                    "created_at": "2026-11-27T09:00:00+00:00",
                }
            ],
            "progress": [
                {
                    "id": "b7ab48e2-9c88-4d3b-b4eb-bd04dc8e4bba",
                    "goal": "Finish a SQL portfolio project",
                    "completed": False,
                    "created_at": "2026-11-27T08:00:00+00:00",
                    "updated_at": "2026-11-27T08:00:00+00:00",
                }
            ],
        }

        page = self.client.get("/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Finish a SQL portfolio project", page.data)
        self.assertIn(b"career-resume.pdf", page.data)
        self.assertIn(b"Connecting to live updates", page.data)

        feed = self.client.get("/api/dashboard/data")
        self.assertEqual(feed.status_code, 200)
        self.assertEqual(feed.json["progress"][0]["goal"], "Finish a SQL portfolio project")
        self.assertEqual(feed.headers["Cache-Control"], "no-store")

    def test_protected_pages_login_realtime_and_logout(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(self.client.get("/upload").status_code, 302)
        self.assertEqual(self.client.get("/chatbot").status_code, 302)
        self.assertEqual(self.client.get("/api/realtime/session").status_code, 401)

        login = self._sign_in()
        self.assertIn("HttpOnly", login.headers.get("Set-Cookie", ""))
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/upload").status_code, 200)
        self.assertEqual(self.client.get("/chatbot").status_code, 200)

        realtime = self.client.get("/api/realtime/session")
        self.assertEqual(realtime.status_code, 200)
        self.assertEqual(realtime.json["access_token"], "test-access-token")
        self.assertEqual(realtime.headers["Cache-Control"], "no-store")

        logout = self.client.post("/logout")
        self.assertEqual(logout.status_code, 302)
        self.assertIn("Max-Age=0", logout.headers.get("Set-Cookie", ""))
        db.sign_out.assert_called_once_with("test-access-token", "test-refresh-token")

    def test_contact_form_persists_valid_submission(self):
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
        db.create_contact_message.assert_called_once_with(
            "Smoke Test", "smoke-contact@example.test", "Smoke test message"
        )

    def test_learning_goals_persist_through_user_scoped_helpers(self):
        self._sign_in()
        response = self.client.post(
            "/dashboard/progress", data={"goal": "Finish a SQL project"}
        )
        self.assertEqual(response.status_code, 302)
        db.create_learning_progress.assert_called_once_with(
            self.auth_context["client"], self.user.id, "Finish a SQL project"
        )

        progress_id = "b7ab48e2-9c88-4d3b-b4eb-bd04dc8e4bba"
        updated = self.client.post(
            f"/dashboard/progress/{progress_id}/toggle", data={"completed": "true"}
        )
        self.assertEqual(updated.status_code, 302)
        db.update_learning_progress.assert_called_once_with(
            self.auth_context["client"], self.user.id, progress_id, True
        )
        self.assertEqual(
            self.client.post("/dashboard/progress/not-a-uuid/toggle").status_code,
            404,
        )

    def test_upload_validation_and_local_storage(self):
        self._sign_in()
        invalid = self.client.post(
            "/upload",
            data={"resume": (io.BytesIO(b"not a resume"), "resume.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid.status_code, 302)
        db.create_resume_upload.assert_not_called()

        valid = self.client.post(
            "/upload",
            data={"resume": (io.BytesIO(b"sample resume"), "resume.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(valid.status_code, 302)
        self.assertIn("/dashboard", valid.headers["Location"])
        db.create_resume_upload.assert_called_once()
        db.update_resume_upload_status.assert_called_once_with(
            self.auth_context["client"], self.user.id, "resume-id", "ready"
        )
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
        self._sign_in()
        self.assertEqual(self.client.post("/chatbot/ask", json={}).status_code, 400)

        with patch.object(
            app_module,
            "generate_ai_response",
            side_effect=GeminiConfigurationError("Gemini is not configured."),
        ):
            unavailable = self.client.post(
                "/chatbot/ask", json={"message": "How do I prepare for an interview?"}
            )
        self.assertEqual(unavailable.status_code, 503)

        with patch.object(
            app_module, "generate_ai_response", return_value="Practice concise answers."
        ):
            response = self.client.post(
                "/chatbot/ask", json={"message": "How do I prepare for an interview?"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["response"], "Practice concise answers.")


if __name__ == "__main__":
    unittest.main()
