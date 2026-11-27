import hashlib
import hmac
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    g,
    jsonify,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

APP_ROOT = Path(__file__).resolve().parent
load_dotenv(APP_ROOT / ".env")
load_dotenv(APP_ROOT / ".env.development.local")
for parent in APP_ROOT.parents:
    load_dotenv(parent / ".env.development.local")

import db
from services.storage_service import (
    StorageConfigurationError,
    StorageError,
    save_upload,
)
from services.gemini_service import (
    GeminiConfigurationError,
    GeminiServiceError,
    generate_ai_response,
)
from services.resume_analysis_service import analyze_resume, extract_resume_text


app = Flask(__name__)
IS_VERCEL = os.getenv("VERCEL") == "1"
secret_key = os.getenv("SECRET_KEY")
if not secret_key and os.getenv("SUPABASE_JWT_SECRET"):
    secret_key = hmac.new(
        os.environ["SUPABASE_JWT_SECRET"].encode(),
        b"careerpilot-flask-session-v1",
        hashlib.sha256,
    ).hexdigest()
if IS_VERCEL and not secret_key:
    raise RuntimeError(
        "Configure SECRET_KEY or the Supabase JWT secret for Flask sessions."
    )

app.secret_key = secret_key or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_VERCEL,
)

UPLOAD_FOLDER = str(APP_ROOT / "uploads")
MAX_UPLOAD_MB = 4 if IS_VERCEL else 5
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}
ACCESS_COOKIE = "careerpilot_access"
REFRESH_COOKIE = "careerpilot_refresh"
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30
AUTH_RATE_LIMIT_WINDOW = 300
AUTH_RATE_LIMIT_MAX = 10
_AUTH_ATTEMPTS = {}
_AUTH_ATTEMPTS_LOCK = threading.Lock()
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

if not IS_VERCEL:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def _set_auth_cookies(response, auth_session):
    response.set_cookie(
        ACCESS_COOKIE,
        auth_session.access_token,
        max_age=max(60, int(auth_session.expires_in or 3600)),
        httponly=True,
        secure=IS_VERCEL,
        samesite="Lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        auth_session.refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        secure=IS_VERCEL,
        samesite="Lax",
        path="/",
    )
    return response


@app.before_request
def load_current_user():
    g.current_user = None
    g.is_admin = False
    g.supabase_client = None
    g.auth_session = None
    g.clear_auth_cookies = False

    if request.endpoint == "static":
        return None

    access_token = request.cookies.get(ACCESS_COOKIE)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not access_token and not refresh_token:
        return None

    try:
        context = db.authenticate_session(access_token, refresh_token)
    except db.SupabaseConfigurationError:
        current_app.logger.exception("Supabase auth is not configured")
        return jsonify({"error": "Authentication is temporarily unavailable."}), 503
    except Exception:
        current_app.logger.exception("Could not validate the Supabase session")
        return jsonify({"error": "Authentication is temporarily unavailable."}), 503

    if context is None:
        g.clear_auth_cookies = True
        return None

    g.current_user = context["user"]
    g.is_admin = _user_is_admin(g.current_user)
    g.supabase_client = context["client"]
    g.auth_session = context["session"]
    return None


@app.after_request
def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if IS_VERCEL:
        response.headers["Strict-Transport-Security"] = "max-age=63072000"

    if getattr(g, "clear_auth_cookies", False):
        response.delete_cookie(
            ACCESS_COOKIE, path="/", secure=IS_VERCEL, samesite="Lax"
        )
        response.delete_cookie(
            REFRESH_COOKIE, path="/", secure=IS_VERCEL, samesite="Lax"
        )
    elif getattr(g, "auth_session", None):
        _set_auth_cookies(response, g.auth_session)
    return response


def _configured_admin_emails():
    return {
        address.strip().lower()
        for address in os.getenv("PLACEMENTCARE_ADMIN_EMAILS", "").split(",")
        if address.strip()
    }


def _user_is_admin(user):
    app_metadata = getattr(user, "app_metadata", None) or {}
    if isinstance(app_metadata, dict) and app_metadata.get("role") == "admin":
        return True

    email = (getattr(user, "email", None) or "").strip().lower()
    verified = bool(
        getattr(user, "email_confirmed_at", None)
        or getattr(user, "confirmed_at", None)
    )
    if not email or email not in _configured_admin_emails() or not verified:
        return False

    providers = set()
    if isinstance(app_metadata, dict):
        provider = app_metadata.get("provider")
        if isinstance(provider, str):
            providers.add(provider.lower())
        provider_list = app_metadata.get("providers") or []
        if isinstance(provider_list, (list, tuple, set)):
            providers.update(item.lower() for item in provider_list if isinstance(item, str))
    identities = getattr(user, "identities", None) or []
    for identity in identities:
        provider = (
            identity.get("provider")
            if isinstance(identity, dict)
            else getattr(identity, "provider", None)
        )
        if isinstance(provider, str):
            providers.add(provider.lower())
    return "google" in providers


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.current_user is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required."}), 401
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.current_user is None:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        if not g.is_admin:
            return "Forbidden", 403
        return view(*args, **kwargs)

    return wrapped_view


def _password_form_token():
    token = session.get("password_form_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["password_form_token"] = token
    return token


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _is_auth_rate_limited():
    now = time.monotonic()
    client_ip = request.remote_addr or "unknown"
    key = ("auth", client_ip)
    with _AUTH_ATTEMPTS_LOCK:
        attempts = [
            attempt
            for attempt in _AUTH_ATTEMPTS.get(key, [])
            if now - attempt < AUTH_RATE_LIMIT_WINDOW
        ]
        if len(attempts) >= AUTH_RATE_LIMIT_MAX:
            _AUTH_ATTEMPTS[key] = attempts
            return True
        attempts.append(now)
        _AUTH_ATTEMPTS[key] = attempts
        return False


def _friendly_auth_error(error, action):
    message = str(error).lower()
    if "email not confirmed" in message or "email_not_confirmed" in message:
        return "Please confirm your email address before signing in."
    if "password" in message and any(
        phrase in message for phrase in ("at least", "too short", "minimum")
    ):
        return "Choose a password with at least 8 characters."
    if "rate limit" in message or "too many" in message:
        return "Too many attempts. Please wait a moment and try again."
    if action == "register":
        return "We could not create the account. Check the information and try again."
    return "Unable to sign in with those credentials. Please check them and try again."


def _auth_redirect_url():
    if IS_VERCEL:
        production_host = os.getenv("VERCEL_PROJECT_PRODUCTION_URL")
        if os.getenv("VERCEL_ENV") == "production":
            deployment_host = production_host or os.getenv("VERCEL_URL")
        else:
            deployment_host = os.getenv("VERCEL_URL") or production_host
        return (
            f"https://{deployment_host}/auth/callback"
            if deployment_host
            else None
        )

    redirect_url = os.getenv("NEXT_PUBLIC_DEV_SUPABASE_REDIRECT_URL")
    if redirect_url:
        return redirect_url
    return url_for("auth_callback", _external=True)


def _current_user_id():
    return str(g.current_user.id)


def _empty_dashboard_data():
    return {"profile": None, "resumes": [], "progress": []}


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.svg"))


@app.route("/features")
def features():
    return render_template("features.html")


@app.route("/roadmap")
def roadmap():
    return render_template("roadmap.html")


@app.route("/careers")
def careers():
    return render_template("careers.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/<slug>")
def content_page(slug):
    pages = {
        "resume-analyzer": ("Resume Analyzer", "Turn your resume into a clearer story. Upload a PDF or document to keep it in your private workspace, then explore the analysis tools available to you.", "upload", "Analyze a resume", ["Private resume library", "ATS-ready structure guidance", "Actionable next steps"]),
        "skill-extractor": ("Skill Extractor", "Make your strengths easier to see. Start with your resume and build a clearer picture of the skills you can bring to your next role.", "upload", "Upload a resume", ["Surface core strengths", "Spot skills to develop", "Connect skills to career paths"]),
        "ai-mentor": ("AI Mentor", "Get thoughtful support for career decisions, interview practice, and your next professional move.", "chatbot", "Talk to your mentor", ["Career questions, answered", "Interview practice prompts", "Practical next steps"]),
        "job-matcher": ("Job Matcher", "Explore career directions that align with your interests and strengths. Start with the career paths library and use your roadmap to plan what comes next.", "careers", "Explore career paths", ["Browse role families", "Understand common skills", "Build a personal learning plan"]),
        "blog": ("The CareerPilot AI journal", "Ideas and practical guidance for building a career with intention.", "roadmap", "Start your roadmap", ["Career planning", "Job search strategies", "Learning habits"]),
        "learning-hub": ("Learning hub", "Turn a big goal into small, trackable steps. Your learning plan is saved to your account and updates live across sessions.", "dashboard", "Open your dashboard", ["Create learning goals", "Track completed milestones", "See progress update in real time"]),
        "interview-prep": ("Interview prep", "Practice the moments that matter, from your opening story to the questions you want to ask.", "chatbot", "Practice with your AI mentor", ["Structure concise answers", "Prepare thoughtful questions", "Build confidence through practice"]),
        "help-center": ("Help center", "Need a hand with your account or career workspace? Send a note and the CareerPilot AI team will get back to you.", "contact", "Contact support", ["Account and workspace help", "Resume upload guidance", "Product feedback"]),
    }
    page = pages.get(slug)
    if page is None:
        return render_template("404.html"), 404
    title, description, action, action_label, highlights = page
    return render_template(
        "hub.html",
        title=title,
        description=description,
        action_url=url_for(action),
        action_label=action_label,
        highlights=highlights,
    )


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        message = request.form.get("message", "").strip()
        valid_email = re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)

        if not name or len(name) > 120 or not valid_email or len(email) > 254:
            flash("Enter a name and valid email address.", "warning")
            return redirect(url_for("contact"))
        if not message or len(message) > 5000:
            flash("Keep your message between 1 and 5,000 characters.", "warning")
            return redirect(url_for("contact"))

        try:
            db.create_contact_message(name, email, message)
        except Exception:
            current_app.logger.exception("Could not save a contact message")
            flash("Your message could not be sent right now. Please try again.", "danger")
            return redirect(url_for("contact"))

        flash("Your message has been received. Thank you for contacting us.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.current_user is not None:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        if _is_auth_rate_limited():
            flash("Too many authentication attempts. Wait a few minutes and try again.", "warning")
            return render_template("register.html"), 429

        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        valid_email = re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)

        if not display_name or len(display_name) > 100 or not valid_email:
            flash("Enter your name and a valid email address.", "warning")
            return render_template("register.html"), 400
        if len(password) < 8:
            flash("Choose a password with at least 8 characters.", "warning")
            return render_template("register.html"), 400

        redirect_url = _auth_redirect_url()
        if not redirect_url:
            flash("Email confirmation is not configured for this deployment.", "danger")
            return render_template("register.html"), 503
        try:
            result = db.sign_up(email, password, display_name, redirect_url)
        except Exception as error:
            current_app.logger.warning("Supabase sign-up failed: %s", error)
            flash(_friendly_auth_error(error, "register"), "danger")
            return render_template("register.html"), 400

        if result.session:
            g.auth_session = result.session
            flash("Your account is ready.", "success")
            return redirect(url_for("dashboard"))

        flash(
            "Check your inbox for a confirmation link to finish creating your account.",
            "info",
        )
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.current_user is not None:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        if _is_auth_rate_limited():
            flash("Too many authentication attempts. Wait a few minutes and try again.", "warning")
            return render_template("login.html"), 429

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if email in _configured_admin_emails():
            return _begin_google_oauth(admin_email=email)
        if not email or not password:
            flash("Enter your email and password.", "warning")
            return render_template("login.html"), 400

        try:
            result = db.sign_in(email, password)
        except Exception as error:
            current_app.logger.info("Supabase sign-in was rejected: %s", error)
            flash(_friendly_auth_error(error, "login"), "danger")
            return render_template("login.html"), 401

        if not result.session:
            flash("Please confirm your email address before signing in.", "warning")
            return redirect(url_for("login"))

        g.auth_session = result.session
        flash("Welcome back.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


def _begin_google_oauth(admin_email=None):
    redirect_url = _auth_redirect_url()
    if not redirect_url:
        flash("Google sign-in is not configured for this deployment yet.", "warning")
        return redirect(url_for("login"))

    try:
        oauth_url, code_verifier = db.start_oauth("google", redirect_url)
    except Exception:
        current_app.logger.exception("Could not start Google sign-in")
        flash("Google sign-in is unavailable right now. Please try again later.", "warning")
        return redirect(url_for("login"))

    session["google_oauth_verifier"] = code_verifier
    session["google_oauth_started_at"] = int(time.time())
    session.pop("google_admin_email", None)
    if admin_email:
        session["google_admin_email"] = admin_email
    return redirect(oauth_url)


@app.route("/auth/google")
def google_login():
    if g.current_user is not None:
        return redirect(url_for("admin_profile" if g.is_admin else "dashboard"))
    if _is_auth_rate_limited():
        flash("Too many authentication attempts. Wait a few minutes and try again.", "warning")
        return redirect(url_for("login"))
    return _begin_google_oauth()


@app.route("/auth/callback")
def auth_callback():
    if request.args.get("error"):
        session.pop("google_oauth_verifier", None)
        session.pop("google_oauth_started_at", None)
        session.pop("google_admin_email", None)
        flash("Google sign-in could not be completed. Please try again.", "warning")
        return redirect(url_for("login"))

    token_hash = request.args.get("token_hash", "").strip()
    token_type = request.args.get("type", "signup").strip()
    code = request.args.get("code", "").strip()
    admin_email = None

    try:
        if token_hash:
            allowed_types = {
                "signup", "email", "magiclink", "recovery", "invite",
                "email_change", "sms", "phone_change", "reauthentication",
            }
            result = db.verify_email_token(
                token_hash,
                token_type if token_type in allowed_types else "signup",
            )
        elif code:
            admin_email = session.pop("google_admin_email", None)
            code_verifier = session.pop("google_oauth_verifier", None)
            started_at = session.pop("google_oauth_started_at", None)
            if code_verifier:
                try:
                    is_expired = not started_at or time.time() - int(started_at) > 600
                except (TypeError, ValueError):
                    is_expired = True
                if is_expired:
                    flash("That Google sign-in link expired. Please try again.", "warning")
                    return redirect(url_for("login"))
                result = db.exchange_auth_code(code, code_verifier)
            else:
                result = db.exchange_auth_code(code)
        else:
            flash("That confirmation link is invalid or expired.", "warning")
            return redirect(url_for("login"))
    except Exception:
        session.pop("google_admin_email", None)
        current_app.logger.exception("Supabase authentication callback failed")
        flash("Sign-in could not be completed. Please try again.", "warning")
        return redirect(url_for("login"))

    if not result.session:
        flash("Please sign in to continue.", "info")
        return redirect(url_for("login"))

    if admin_email:
        authenticated_email = (
            getattr(result.user, "email", "") or ""
        ).strip().lower()
        if authenticated_email != admin_email or not _user_is_admin(result.user):
            flash("That Google account is not authorized for administrator access.", "danger")
            return redirect(url_for("login"))
        g.auth_session = result.session
        flash("Welcome, administrator.", "success")
        return redirect(url_for("admin_profile"))

    g.auth_session = result.session
    if token_type in {"invite", "recovery"}:
        flash("Your email link is confirmed. Set a password to continue.", "success")
        return redirect(url_for("set_password"))
    flash("You are signed in. Your account is ready.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin")
@admin_required
def admin_profile():
    metadata = getattr(g.current_user, "user_metadata", None) or {}
    account_error = False
    directory = {"accounts": [], "truncated": False}
    try:
        directory = db.get_admin_user_directory()
    except Exception:
        current_app.logger.exception("Could not load the admin account directory")
        account_error = True

    accounts = directory.get("accounts", [])
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    active_count = 0
    for account in accounts:
        last_sign_in = account.get("last_sign_in_at")
        try:
            last_sign_in_at = datetime.fromisoformat(last_sign_in.replace("Z", "+00:00"))
            if last_sign_in_at.tzinfo is None:
                last_sign_in_at = last_sign_in_at.replace(tzinfo=timezone.utc)
            if last_sign_in_at >= recent_cutoff:
                active_count += 1
        except (AttributeError, TypeError, ValueError):
            continue

    return render_template(
        "admin.html",
        admin_email=getattr(g.current_user, "email", ""),
        admin_name=metadata.get("display_name") or "CareerPilot AI Administrator",
        accounts=accounts,
        account_count=len(accounts),
        verified_count=sum(1 for account in accounts if account.get("verified")),
        admin_count=sum(1 for account in accounts if account.get("role") == "admin"),
        active_count=active_count,
        account_error=account_error,
        account_truncated=directory.get("truncated", False),
    )


@app.route("/account/password", methods=["GET", "POST"])
@login_required
def set_password():
    if request.method == "POST":
        submitted_token = request.form.get("csrf_token", "")
        expected_token = session.get("password_form_token", "")
        if not expected_token or not hmac.compare_digest(submitted_token, expected_token):
            return "Invalid form submission", 400

        password = request.form.get("password", "")
        password_confirmation = request.form.get("password_confirmation", "")
        if len(password) < 8 or len(password) > 128:
            flash("Choose a password between 8 and 128 characters.", "warning")
            return render_template("set_password.html", csrf_token=_password_form_token()), 400
        if password != password_confirmation:
            flash("The passwords do not match. Try again.", "warning")
            return render_template("set_password.html", csrf_token=_password_form_token()), 400

        try:
            db.update_password(
                g.supabase_client,
                g.auth_session.access_token,
                g.auth_session.refresh_token,
                password,
            )
        except Exception:
            current_app.logger.exception("Could not update the account password")
            flash("Your password could not be updated. Please try again.", "danger")
            return render_template("set_password.html", csrf_token=_password_form_token()), 503

        session.pop("password_form_token", None)
        flash("Your password has been set.", "success")
        return redirect(url_for("admin_profile" if g.is_admin else "dashboard"))

    return render_template("set_password.html", csrf_token=_password_form_token())


@app.route("/dashboard")
@login_required
def dashboard():
    data_error = False
    data = _empty_dashboard_data()
    try:
        data = db.get_dashboard_data(g.supabase_client, _current_user_id())
    except Exception:
        current_app.logger.exception("Could not load the CareerPilot dashboard")
        data_error = True

    profile = data.get("profile") or {}
    metadata = getattr(g.current_user, "user_metadata", None) or {}
    display_name = (
        profile.get("display_name")
        or metadata.get("display_name")
        or getattr(g.current_user, "email", "CareerPilot AI member").split("@")[0]
    )
    progress = data.get("progress", [])
    return render_template(
        "dashboard.html",
        username=display_name,
        resumes=data.get("resumes", []),
        progress=progress,
        completed_count=sum(1 for item in progress if item.get("completed")),
        data_error=data_error,
        supabase_url=os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL"),
    )


@app.route("/api/dashboard/data")
@login_required
def dashboard_data_api():
    try:
        data = db.get_dashboard_data(g.supabase_client, _current_user_id())
    except Exception:
        current_app.logger.exception("Could not refresh the CareerPilot dashboard")
        return jsonify({"error": "Dashboard data is temporarily unavailable."}), 503

    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/dashboard/progress", methods=["POST"])
@login_required
def add_progress():
    goal = request.form.get("goal", "").strip()
    if not goal or len(goal) > 180:
        flash("Enter a learning goal between 1 and 180 characters.", "warning")
        return redirect(url_for("dashboard"))
    try:
        db.create_learning_progress(g.supabase_client, _current_user_id(), goal)
        flash("Learning goal added.", "success")
    except Exception:
        current_app.logger.exception("Could not save learning progress")
        flash("Your learning goal could not be saved. Please try again.", "danger")
    return redirect(url_for("dashboard"))


@app.route("/dashboard/progress/<progress_id>/toggle", methods=["POST"])
@login_required
def toggle_progress(progress_id):
    try:
        progress_id = str(uuid.UUID(progress_id))
    except (ValueError, TypeError):
        return "Not found", 404

    completed = request.form.get("completed") == "true"
    try:
        updated = db.update_learning_progress(
            g.supabase_client,
            _current_user_id(),
            progress_id,
            completed,
        )
    except Exception:
        current_app.logger.exception("Could not update learning progress")
        flash("Your learning progress could not be updated.", "danger")
        return redirect(url_for("dashboard"))
    if updated is None:
        return "Not found", 404
    return redirect(url_for("dashboard"))


@app.route("/dashboard/progress/<progress_id>/delete", methods=["POST"])
@login_required
def delete_progress(progress_id):
    try:
        progress_id = str(uuid.UUID(progress_id))
    except (ValueError, TypeError):
        return "Not found", 404
    try:
        deleted = db.delete_learning_progress(
            g.supabase_client,
            _current_user_id(),
            progress_id,
        )
    except Exception:
        current_app.logger.exception("Could not delete learning progress")
        flash("Your learning goal could not be removed.", "danger")
        return redirect(url_for("dashboard"))
    if not deleted:
        return "Not found", 404
    flash("Learning goal removed.", "info")
    return redirect(url_for("dashboard"))


@app.route("/api/realtime/session")
@login_required
def realtime_session():
    public_key = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not public_key or not g.auth_session:
        return jsonify({"error": "Live updates are unavailable."}), 503
    response = jsonify(
        {
            "access_token": g.auth_session.access_token,
            "user_id": _current_user_id(),
            "supabase_url": os.getenv("SUPABASE_URL")
            or os.getenv("NEXT_PUBLIC_SUPABASE_URL"),
            "publishable_key": public_key,
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        file = request.files.get("resume")
        if not file or not file.filename:
            flash("Choose a resume file to upload.", "warning")
            return redirect(url_for("upload"))
        if not allowed_file(file.filename):
            flash("Only PDF or DOCX resumes are supported for analysis.", "danger")
            return redirect(url_for("upload"))

        original_filename = secure_filename(file.filename)[:255]
        if not original_filename:
            flash("The selected filename is not valid.", "warning")
            return redirect(url_for("upload"))
        try:
            content = file.stream.read()
            resume_text = extract_resume_text(original_filename, content)
        except Exception:
            current_app.logger.info("Could not extract text from uploaded resume", exc_info=True)
            flash("We could not read this file. Please upload a text-based PDF or DOCX.", "warning")
            return redirect(url_for("upload"))
        finally:
            file.stream.seek(0)
        if len(resume_text.strip()) < 40:
            flash("This resume has too little readable text to analyze. Try a text-based PDF or DOCX.", "warning")
            return redirect(url_for("upload"))
        analysis = analyze_resume(resume_text)
        storage_key = f"{uuid.uuid4()}_{original_filename}"
        user_id = _current_user_id()

        try:
            resume = db.create_resume_upload(
                g.supabase_client,
                user_id,
                original_filename,
                storage_key,
            )
        except Exception:
            current_app.logger.exception("Could not create resume metadata")
            flash("Your resume could not be prepared for upload.", "danger")
            return redirect(url_for("upload"))

        try:
            save_upload(file, storage_key, app.config["UPLOAD_FOLDER"])
        except StorageConfigurationError as error:
            current_app.logger.error("Resume storage is not configured: %s", error)
            db.update_resume_upload_status(
                g.supabase_client, user_id, resume["id"], "failed"
            )
            flash("Resume uploads are not configured for this deployment.", "danger")
            return render_template("upload.html", max_upload_mb=MAX_UPLOAD_MB), 503
        except StorageError as error:
            current_app.logger.error("Resume upload failed: %s", error)
            db.update_resume_upload_status(
                g.supabase_client, user_id, resume["id"], "failed"
            )
            flash("Resume upload failed. Please try again later.", "danger")
            return render_template("upload.html", max_upload_mb=MAX_UPLOAD_MB), 502

        try:
            saved = db.update_resume_analysis(
                g.supabase_client, user_id, resume["id"], analysis
            )
            if not saved:
                raise RuntimeError("Resume analysis was not saved.")
            db.update_resume_upload_status(
                g.supabase_client, user_id, resume["id"], "ready"
            )
        except Exception:
            current_app.logger.exception("Could not persist resume analysis")
            db.update_resume_upload_status(
                g.supabase_client, user_id, resume["id"], "failed"
            )
            flash("The resume was uploaded, but its analysis could not be saved.", "warning")
            return redirect(url_for("dashboard"))

        flash("Resume analyzed successfully.", "success")
        return redirect(url_for("resume_result", resume_id=resume["id"]))

    return render_template("upload.html", max_upload_mb=MAX_UPLOAD_MB)


@app.route("/resumes/<resume_id>")
@login_required
def resume_result(resume_id):
    try:
        resume = db.get_resume_upload(g.supabase_client, _current_user_id(), resume_id)
    except Exception:
        current_app.logger.exception("Could not load private resume analysis")
        flash("Your resume analysis could not be loaded right now.", "warning")
        return redirect(url_for("dashboard"))
    if not resume:
        return render_template("404.html"), 404
    if not resume.get("analysis"):
        flash("An analysis is not available for this resume yet.", "info")
        return redirect(url_for("dashboard"))
    return render_template("result.html", resume=resume, analysis=resume["analysis"])


@app.route("/chatbot")
@login_required
def chatbot():
    return render_template(
        "chatbot.html",
        username=(getattr(g.current_user, "user_metadata", None) or {}).get(
            "display_name", "CareerPilot AI member"
        ),
    )


@app.route("/chatbot/ask", methods=["POST"])
@login_required
def chatbot_ask():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object with a message is required."}), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Message must be a non-empty string."}), 400
    message = message.strip()[:4000]

    prompt = (
        "You are CareerPilot AI, a helpful career guidance assistant. "
        "Answer accurately and directly in no more than 5 concise bullet points "
        "or short sentences. For career advice, tailor recommendations to the "
        "user's question and use Markdown. If unrelated to careers, answer "
        "briefly and politely.\n\n"
        f"User: {message}"
    )

    try:
        response = generate_ai_response(prompt)
    except GeminiConfigurationError as error:
        return jsonify({"error": str(error)}), 503
    except GeminiServiceError as error:
        current_app.logger.warning("Gemini request failed: %s", error)
        return jsonify({"error": str(error)}), 502

    return jsonify({"response": response})


@app.route("/logout", methods=["POST"])
def logout():
    if g.current_user is not None and g.auth_session:
        try:
            db.sign_out(g.auth_session.access_token, g.auth_session.refresh_token)
        except Exception:
            current_app.logger.info("Supabase sign-out cleanup failed")
    g.clear_auth_cookies = True
    flash("You have been signed out.", "info")
    return redirect(url_for("home"))


@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(413)
def file_too_large(error):
    flash(f"File size exceeds {MAX_UPLOAD_MB} MB.", "warning")
    return redirect(url_for("upload"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
