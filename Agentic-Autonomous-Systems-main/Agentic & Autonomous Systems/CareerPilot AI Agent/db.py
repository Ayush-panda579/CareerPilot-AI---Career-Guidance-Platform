import os
from dataclasses import dataclass
from typing import Any

try:
    from supabase import create_client
except ImportError:
    create_client = None


class SupabaseConfigurationError(RuntimeError):
    """The Supabase URL, public key, or SDK is unavailable."""


class DuplicateUserError(RuntimeError):
    """Raised when Supabase rejects an account as already registered."""


@dataclass
class AuthSession:
    access_token: str
    refresh_token: str
    expires_in: int = 3600


@dataclass
class AuthResult:
    user: Any
    session: AuthSession | None


def get_client(access_token=None):
    if create_client is None:
        raise SupabaseConfigurationError("Install the Supabase Python SDK.")

    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    public_key = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not url or not public_key:
        raise SupabaseConfigurationError(
            "Supabase URL and publishable key must be configured."
        )

    client = create_client(url, public_key)
    if access_token:
        client.postgrest.auth(access_token)
    return client


def _normalize_session(session):
    if session is None:
        return None
    return AuthSession(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=int(getattr(session, "expires_in", 3600) or 3600),
    )


def _auth_result(response):
    return AuthResult(
        user=getattr(response, "user", None),
        session=_normalize_session(getattr(response, "session", None)),
    )


def sign_up(email, password, display_name, email_redirect_to):
    client = get_client()
    try:
        response = client.auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {
                    "data": {"display_name": display_name},
                    "email_redirect_to": email_redirect_to,
                },
            }
        )
    except Exception as error:
        message = str(error).lower()
        if "already registered" in message or "already been registered" in message:
            raise DuplicateUserError("Account already exists.") from error
        raise
    return _auth_result(response)


def sign_in(email, password):
    client = get_client()
    response = client.auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    result = _auth_result(response)
    if result.session:
        client.postgrest.auth(result.session.access_token)
    return result


def sign_out(access_token, refresh_token):
    client = get_client()
    if access_token and refresh_token:
        client.auth.set_session(access_token, refresh_token)
    client.auth.sign_out()


def update_password(client, access_token, refresh_token, password):
    if not access_token or not refresh_token:
        raise RuntimeError("An active account session is required to change the password.")
    client.auth.set_session(access_token, refresh_token)
    return client.auth.update_user({"password": password})


def verify_email_token(token_hash, token_type):
    client = get_client()
    response = client.auth.verify_otp(
        {"token_hash": token_hash, "type": token_type}
    )
    return _auth_result(response)


def exchange_auth_code(code):
    client = get_client()
    response = client.auth.exchange_code_for_session(code)
    return _auth_result(response)


def authenticate_session(access_token, refresh_token):
    if not access_token and not refresh_token:
        return None

    client = get_client()
    user = None
    session = None

    if access_token:
        try:
            response = client.auth.get_user(access_token)
            user = getattr(response, "user", None)
        except Exception:
            user = None

    if user and access_token:
        client.postgrest.auth(access_token)
        session = AuthSession(access_token, refresh_token, 3600)
    elif refresh_token:
        try:
            response = client.auth.refresh_session(refresh_token)
            session = _normalize_session(getattr(response, "session", None))
            user = getattr(response, "user", None)
            if session and not user:
                user_response = client.auth.get_user(session.access_token)
                user = getattr(user_response, "user", None)
            if session:
                client.postgrest.auth(session.access_token)
        except Exception:
            return None

    if not user or not session:
        return None

    return {"client": client, "user": user, "session": session}


def _rows(response):
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return data
    return []


def get_dashboard_data(client, user_id):
    profile_rows = _rows(
        client.table("profiles")
        .select("id, display_name, created_at, updated_at")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    resume_rows = _rows(
        client.table("resume_uploads")
        .select("id, original_filename, status, created_at, updated_at")
        .eq("owner_id", user_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    progress_rows = _rows(
        client.table("learning_progress")
        .select("id, goal, completed, created_at, updated_at")
        .eq("owner_id", user_id)
        .order("created_at", desc=False)
        .limit(50)
        .execute()
    )
    return {
        "profile": profile_rows[0] if profile_rows else None,
        "resumes": resume_rows,
        "progress": progress_rows,
    }


def create_learning_progress(client, user_id, goal):
    response = (
        client.table("learning_progress")
        .insert({"owner_id": user_id, "goal": goal})
        .select("id, goal, completed, created_at, updated_at")
        .execute()
    )
    rows = _rows(response)
    if not rows:
        raise RuntimeError("The learning goal was not returned after saving.")
    return rows[0]


def update_learning_progress(client, user_id, progress_id, completed):
    response = (
        client.table("learning_progress")
        .update({"completed": completed})
        .eq("id", progress_id)
        .eq("owner_id", user_id)
        .select("id, goal, completed, created_at, updated_at")
        .execute()
    )
    rows = _rows(response)
    if not rows:
        return None
    return rows[0]


def delete_learning_progress(client, user_id, progress_id):
    response = (
        client.table("learning_progress")
        .delete()
        .eq("id", progress_id)
        .eq("owner_id", user_id)
        .select("id")
        .execute()
    )
    return bool(getattr(response, "data", None))


def create_resume_upload(client, user_id, original_filename, storage_key):
    response = (
        client.table("resume_uploads")
        .insert(
            {
                "owner_id": user_id,
                "original_filename": original_filename,
                "storage_key": storage_key,
                "status": "uploading",
            }
        )
        .select("id, original_filename, status, created_at")
        .execute()
    )
    rows = _rows(response)
    if not rows:
        raise RuntimeError("The resume record was not returned after saving.")
    return rows[0]


def update_resume_upload_status(client, user_id, resume_id, status):
    response = (
        client.table("resume_uploads")
        .update({"status": status})
        .eq("id", resume_id)
        .eq("owner_id", user_id)
        .execute()
    )
    return bool(getattr(response, "data", None))


def create_contact_message(name, email, message):
    client = get_client()
    return (
        client.table("contact_messages")
        .insert({"name": name, "email": email, "message": message})
        .execute()
    )
