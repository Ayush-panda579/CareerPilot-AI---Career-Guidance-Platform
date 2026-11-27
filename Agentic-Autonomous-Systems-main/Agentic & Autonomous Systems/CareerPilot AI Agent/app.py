import os
import secrets
import uuid
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    current_app
)
from werkzeug.utils import secure_filename
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parent
load_dotenv(APP_ROOT / ".env")

from db import (
    init_db,
    create_user,
    get_user,
    create_contact_message,
    DuplicateUserError,
)
from services.storage_service import (
    StorageConfigurationError,
    StorageError,
    save_upload,
)
from services.gemini_service import (
    generate_ai_response,
    GeminiConfigurationError,
    GeminiServiceError
)

# ==================================================
# APP CONFIG
# ==================================================

app = Flask(__name__)

IS_VERCEL = os.getenv("VERCEL") == "1"
secret_key = os.getenv("SECRET_KEY")
if IS_VERCEL and not secret_key:
    raise RuntimeError("Set SECRET_KEY in the Vercel project environment variables.")

app.secret_key = secret_key or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_VERCEL,
)

UPLOAD_FOLDER = str(APP_ROOT / "uploads")
MAX_UPLOAD_MB = 4 if IS_VERCEL else 5

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

if not IS_VERCEL:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================================================
# DATABASE INIT
# ==================================================

init_db()

# ==================================================
# HELPERS
# ==================================================

def allowed_file(filename):

    return (
        "." in filename and
        filename.rsplit(
            ".", 1
        )[1].lower() in ALLOWED_EXTENSIONS
    )


def generate_dashboard_data():

    return {

        "ats_score": 82,

        "job_readiness": 85,

        "skills": [
            "Python",
            "Flask",
            "SQL",
            "HTML",
            "CSS",
            "Bootstrap"
        ],

        "gaps": [
            "Git",
            "GitHub",
            "Docker",
            "AWS"
        ],

        "career": [
            "Python Developer",
            "Full Stack Developer",
            "Data Analyst",
            "Cloud Engineer",
            "AI Engineer"
        ],

        "roadmap": [

            {
                "topic": "Python Fundamentals",
                "youtube":
                "https://www.youtube.com/results?search_query=python+full+course"
            },

            {
                "topic": "Object Oriented Programming",
                "youtube":
                "https://www.youtube.com/results?search_query=python+oop"
            },

            {
                "topic": "Flask Development",
                "youtube":
                "https://www.youtube.com/results?search_query=flask+tutorial"
            },

            {
                "topic": "SQL Database",
                "youtube":
                "https://www.youtube.com/results?search_query=sql+course"
            }
        ],

        "certifications": [

            "Google Data Analytics",

            "AWS Cloud Practitioner",

            "Meta Backend Developer",

            "IBM Python Certificate",

            "Microsoft Azure Fundamentals"
        ],

        "projects": [

            "CareerPilot AI",

            "Job Portal",

            "Hospital Management System",

            "Online Examination System",

            "E-Library Management"
        ],

        "technical_questions": [

            "What is Flask?",

            "What is REST API?",

            "Difference between List and Tuple?",

            "Explain OOP Concepts.",

            "What is SQL JOIN?"
        ],

        "hr_questions": [

            "Tell me about yourself.",

            "Why should we hire you?",

            "What are your strengths?",

            "What are your weaknesses?",

            "Where do you see yourself in 5 years?"
        ]
    }

# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/favicon.ico")
def favicon():
    return redirect(
        url_for("static", filename="favicon.svg")
    )

# ==================================================
# FEATURES
# ==================================================

@app.route("/features")
def features():
    return render_template("features.html")

# ==================================================
# ROADMAP
# ==================================================

@app.route("/roadmap")
def roadmap():
    return render_template("roadmap.html")

# ==================================================
# CAREERS
# ==================================================

@app.route("/careers")
def careers():
    return render_template("careers.html")

# ==================================================
# CONTACT
# ==================================================

@app.route("/contact", methods=["GET", "POST"])
def contact():

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash("Please complete all contact form fields.", "warning")
            return redirect(url_for("contact"))

        create_contact_message(name, email, message)
        flash("Your message has been received. Thank you for contacting us.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")

# ==================================================
# REGISTER
# ==================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Please complete all registration fields.", "warning")
            return redirect(url_for("register"))

        hashed_password = (
            generate_password_hash(
                password
            )
        )

        try:

            create_user(
                username,
                email,
                hashed_password
            )

            flash(
                "Registration Successful!",
                "success"
            )

            return redirect(
                url_for("login")
            )

        except DuplicateUserError:

            flash(
                "Username or Email already exists",
                "danger"
            )

    return render_template(
        "register.html"
    )

# ==================================================
# LOGIN
# ==================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_user(username) if username else None

        if user and password and check_password_hash(
            user["password"],
            password
        ):

            session["user"] = username

            flash(
                "Login Successful",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Invalid Username or Password",
            "danger"
        )

    return render_template(
        "login.html"
    )

# ==================================================
# DASHBOARD
# ==================================================

@app.route("/dashboard")
def dashboard():

    if "user" not in session:

        flash(
            "Please login first",
            "warning"
        )

        return redirect(
            url_for("login")
        )

    result = generate_dashboard_data()

    return render_template(
        "dashboard.html",
        username=session["user"],
        result=result
    )

# ==================================================
# RESUME UPLOAD
# ==================================================

@app.route(
    "/upload",
    methods=["GET", "POST"]
)
def upload():

    if "user" not in session:

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        file = request.files.get(
            "resume"
        )

        if not file:

            flash(
                "Please select a file",
                "warning"
            )

            return redirect(
                request.url
            )

        if file.filename == "":

            flash(
                "No file selected",
                "warning"
            )

            return redirect(
                request.url
            )

        if not allowed_file(
            file.filename
        ):

            flash(
                "Only PDF, DOC, or DOCX files are allowed",
                "danger"
            )

            return redirect(
                request.url
            )

        filename = (
            f"{uuid.uuid4()}_"
            f"{secure_filename(file.filename)}"
        )

        try:
            save_upload(
                file,
                filename,
                app.config["UPLOAD_FOLDER"],
            )
        except StorageConfigurationError as error:
            current_app.logger.error("Resume storage is not configured: %s", error)
            flash(
                "Resume uploads are not configured for this deployment.",
                "danger",
            )
            return render_template(
                "upload.html",
                max_upload_mb=MAX_UPLOAD_MB,
            ), 503
        except StorageError as error:
            current_app.logger.error("Resume upload failed: %s", error)
            flash(
                "Resume upload failed. Please try again later.",
                "danger",
            )
            return render_template(
                "upload.html",
                max_upload_mb=MAX_UPLOAD_MB,
            ), 502

        flash(
            "Resume uploaded successfully",
            "success"
        )

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "upload.html",
        max_upload_mb=MAX_UPLOAD_MB,
    )

# ==================================================
# CHATBOT PAGE
# ==================================================

@app.route("/chatbot")
def chatbot():

    if "user" not in session:

        flash(
            "Please login first",
            "warning"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "chatbot.html",
        username=session["user"]
    )


# ==================================================
# CHATBOT AI API
# ==================================================

@app.route(
    "/chatbot/ask",
    methods=["POST"]
)
def chatbot_ask():

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object with a message is required."}), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Message must be a non-empty string."}), 400

    message = message.strip()

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

    return jsonify({
        "response": response
    })

# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "Logged out successfully",
        "info"
    )

    return redirect(
        url_for("home")
    )

# ==================================================
# ERROR HANDLERS
# ==================================================

@app.errorhandler(404)
def page_not_found(error):

    return (
        render_template(
            "404.html"
        ),
        404
    )


@app.errorhandler(413)
def file_too_large(error):

    flash(
        f"File size exceeds {MAX_UPLOAD_MB} MB",
        "danger"
    )

    return redirect(
        url_for("upload")
    )

# ==================================================
# RUN APP
# ==================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )