import json
import os
import urllib.parse
import urllib.request
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


def start_oauth(provider, redirect_to):
    client = get_client()
    response = client.auth.sign_in_with_oauth(
        {
            "provider": provider,
            "options": {"redirect_to": redirect_to},
        }
    )
    auth_client = client.auth
    storage = getattr(auth_client, "_storage", None)
    storage_key = getattr(auth_client, "_storage_key", None)
    code_verifier = (
        storage.get_item(f"{storage_key}-code-verifier")
        if storage is not None and storage_key
        else None
    )
    oauth_url = getattr(response, "url", None)
    if not oauth_url or not code_verifier:
        raise RuntimeError("Supabase did not create a PKCE OAuth challenge.")
    return oauth_url, code_verifier


def exchange_auth_code(code, code_verifier=None):
    client = get_client()
    exchange_params = {"auth_code": code}
    if code_verifier:
        exchange_params["code_verifier"] = code_verifier
    response = client.auth.exchange_code_for_session(exchange_params)
    return _auth_result(response)


def get_admin_user_directory():
    base_url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECRET_KEY")
    if not base_url or not service_key:
        raise SupabaseConfigurationError("Supabase admin access is not configured.")

    accounts = []
    per_page = 1000
    max_pages = 10
    truncated = False
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }

    for page in range(1, max_pages + 1):
        query = urllib.parse.urlencode({"page": page, "per_page": per_page})
        request = urllib.request.Request(
            f"{base_url}/auth/v1/admin/users?{query}", headers=headers
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read())

        batch = payload.get("users", []) if isinstance(payload, dict) else []
        for user in batch:
            if not isinstance(user, dict):
                continue
            user_metadata = user.get("user_metadata") or {}
            app_metadata = user.get("app_metadata") or {}
            identities = user.get("identities") or []
            providers = app_metadata.get("providers") or []
            provider = app_metadata.get("provider")
            if not provider and providers:
                provider = providers[0]
            if not provider and identities and isinstance(identities[0], dict):
                provider = identities[0].get("provider")

            email = user.get("email") or ""
            verified = bool(user.get("email_confirmed_at") or user.get("confirmed_at"))
            allowed_admins = {
                address.strip().lower()
                for address in os.getenv("PLACEMENTCARE_ADMIN_EMAILS", "").split(",")
                if address.strip()
            }
            identity_providers = {
                identity.get("provider", "").lower()
                for identity in identities
                if isinstance(identity, dict) and isinstance(identity.get("provider"), str)
            }
            has_google_identity = (
                (isinstance(provider, str) and provider.lower() == "google")
                or "google" in providers
                or "google" in identity_providers
            )
            is_configured_admin = (
                email.strip().lower() in allowed_admins and verified and has_google_identity
            )
            accounts.append(
                {
                    "email": email,
                    "display_name": user_metadata.get("display_name")
                    or user_metadata.get("full_name")
                    or (email.split("@", 1)[0] if email else "CareerPilot AI member"),
                    "provider": provider or "email",
                    "verified": verified,
                    "role": "admin"
                    if app_metadata.get("role") == "admin" or is_configured_admin
                    else "member",
                    "created_at": user.get("created_at"),
                    "last_sign_in_at": user.get("last_sign_in_at"),
                }
            )

        if len(batch) < per_page:
            break
        if page == max_pages:
            truncated = True

    return {"accounts": accounts, "truncated": truncated}


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
        .select("id, original_filename, status, created_at, updated_at, analysis")
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


def update_resume_analysis(client, user_id, resume_id, analysis):
    response = (
        client.table("resume_uploads")
        .update({"analysis": analysis})
        .eq("id", resume_id)
        .eq("owner_id", user_id)
        .select("id")
        .execute()
    )
    return bool(getattr(response, "data", None))


def get_resume_upload(client, user_id, resume_id):
    rows = _rows(
        client.table("resume_uploads")
        .select("id, original_filename, status, created_at, analysis")
        .eq("id", resume_id)
        .eq("owner_id", user_id)
        .limit(1)
        .execute()
    )
    return rows[0] if rows else None


def create_contact_message(name, email, message):
    client = get_client()
    return (
        client.table("contact_messages")
        .insert({"name": name, "email": email, "message": message})
        .execute()
    )
