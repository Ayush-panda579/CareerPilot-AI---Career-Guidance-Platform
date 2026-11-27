import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import db


class DatabaseTests(unittest.TestCase):
    def test_uses_publishable_key_not_service_role_key(self):
        client = Mock()
        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://careerpilot.supabase.co",
                    "SUPABASE_PUBLISHABLE_KEY": "public-key",
                    "SUPABASE_ANON_KEY": "anon-key",
                    "SUPABASE_SECRET_KEY": "secret-key-must-not-be-used",
                    "SUPABASE_SERVICE_ROLE_KEY": "service-key-must-not-be-used",
                },
            ),
            patch.object(db, "create_client", return_value=client) as create_client,
        ):
            self.assertIs(db.get_client(), client)

        create_client.assert_called_once_with(
            "https://careerpilot.supabase.co", "public-key"
        )

    def test_sign_in_normalizes_supabase_session(self):
        session = SimpleNamespace(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=1800,
        )
        user = SimpleNamespace(id="user-id")
        client = SimpleNamespace(
            auth=SimpleNamespace(
                sign_in_with_password=Mock(
                    return_value=SimpleNamespace(session=session, user=user)
                )
            ),
            postgrest=SimpleNamespace(auth=Mock()),
        )
        with patch.object(db, "get_client", return_value=client):
            result = db.sign_in("user@example.test", "long-password")

        self.assertEqual(result.user.id, "user-id")
        self.assertEqual(result.session.access_token, "access-token")
        self.assertEqual(result.session.refresh_token, "refresh-token")
        self.assertEqual(result.session.expires_in, 1800)
        client.postgrest.auth.assert_called_once_with("access-token")

    def test_sign_out_revokes_the_current_refresh_session(self):
        client = SimpleNamespace(
            auth=SimpleNamespace(set_session=Mock(), sign_out=Mock())
        )
        with patch.object(db, "get_client", return_value=client):
            db.sign_out("access-token", "refresh-token")

        client.auth.set_session.assert_called_once_with("access-token", "refresh-token")
        client.auth.sign_out.assert_called_once_with()

    def test_update_password_uses_authenticated_session(self):
        client = SimpleNamespace(
            auth=SimpleNamespace(set_session=Mock(), update_user=Mock(return_value="updated"))
        )
        result = db.update_password(client, "access-token", "refresh-token", "new-password")

        self.assertEqual(result, "updated")
        client.auth.set_session.assert_called_once_with("access-token", "refresh-token")
        client.auth.update_user.assert_called_once_with({"password": "new-password"})

    def test_authentication_scopes_postgrest_client_to_access_token(self):
        user = SimpleNamespace(id="user-id", email="user@example.test")
        client = SimpleNamespace(
            auth=SimpleNamespace(
                get_user=Mock(return_value=SimpleNamespace(user=user)),
                refresh_session=Mock(),
            ),
            postgrest=SimpleNamespace(auth=Mock()),
        )
        with patch.object(db, "get_client", return_value=client):
            context = db.authenticate_session("valid-access", "valid-refresh")

        self.assertIs(context["user"], user)
        self.assertEqual(context["session"].access_token, "valid-access")
        client.postgrest.auth.assert_called_once_with("valid-access")
        client.auth.refresh_session.assert_not_called()

    def test_invalid_access_token_uses_refresh_token(self):
        user = SimpleNamespace(id="user-id")
        refreshed = SimpleNamespace(
            access_token="renewed-access",
            refresh_token="renewed-refresh",
            expires_in=2400,
        )
        client = SimpleNamespace(
            auth=SimpleNamespace(
                get_user=Mock(
                    side_effect=[RuntimeError("expired"), SimpleNamespace(user=user)]
                ),
                refresh_session=Mock(
                    return_value=SimpleNamespace(session=refreshed, user=user)
                ),
            ),
            postgrest=SimpleNamespace(auth=Mock()),
        )
        with patch.object(db, "get_client", return_value=client):
            context = db.authenticate_session("expired-access", "refresh-token")

        self.assertEqual(context["session"].access_token, "renewed-access")
        self.assertEqual(context["session"].refresh_token, "renewed-refresh")
        client.postgrest.auth.assert_called_once_with("renewed-access")

    def test_missing_auth_cookies_does_not_create_a_client(self):
        with patch.object(db, "get_client") as get_client:
            self.assertIsNone(db.authenticate_session(None, None))
        get_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
