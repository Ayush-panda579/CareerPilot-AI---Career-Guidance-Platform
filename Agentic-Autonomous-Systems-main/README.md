# 🚀 CareerPilot AI Agent

### An Autonomous Multi-Agent Career Intelligence & Learning Ecosystem

![Project Banner](docs/screenshots/dashboard.png)

> AI-Powered Career Guidance Platform built using Agentic & Autonomous AI Architecture

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Flask](https://img.shields.io/badge/Flask-Web%20Framework-black)
![Gemini](https://img.shields.io/badge/Google-Gemini%20AI-orange)
![SQLite](https://img.shields.io/badge/Database-SQLite-green)
![License](https://img.shields.io/badge/License-Educational-blue)

---

## 📌 Project Overview

CareerPilot AI Agent is an intelligent **multi-agent AI system** that acts as a virtual career mentor for students, freshers, and job seekers.

The platform utilizes specialized autonomous AI agents coordinated through a central **Orchestrator Agent** to provide:

* Resume Analysis
* ATS Optimization
* Career Recommendations
* Skill Gap Detection
* Personalized Learning Roadmaps
* Resource Recommendations
* Interview Preparation
* Progress Tracking
* AI Career Mentoring

Unlike traditional career guidance platforms, CareerPilot AI continuously adapts recommendations based on user skills, goals, progress, and interactions.

---

## ❗ Problem Statement

Many students and freshers struggle with:

* Choosing the right career path
* Creating ATS-friendly resumes
* Understanding industry skill requirements
* Finding structured learning plans
* Preparing for interviews
* Tracking career growth

Most existing solutions provide static recommendations and fail to offer personalized career development support.

---

## ✨ Proposed Solution

CareerPilot AI Agent addresses these challenges using a collaborative multi-agent architecture powered by Google Gemini.

The system:

✅ Analyzes resumes automatically

✅ Calculates ATS compatibility scores

✅ Identifies missing skills

✅ Recommends suitable career paths

✅ Generates adaptive learning roadmaps

✅ Suggests learning resources

✅ Conducts interview preparation

✅ Tracks progress continuously

✅ Provides real-time career mentoring through AI

---

## 🤖 Core AI Agents

### 📄 Resume Analysis Agent

* Resume parsing
* Skill extraction
* Education analysis
* Experience analysis

### 🎯 ATS Optimization Agent

* ATS score generation
* Missing keyword detection
* Resume improvement suggestions

### 🧭 Career Recommendation Agent

* Role suitability analysis
* Career path prediction
* Personalized recommendations

### 📊 Skill Gap Analysis Agent

* Current skill assessment
* Industry requirement comparison
* Missing skill identification

### 🛣️ Learning Roadmap Agent

* Personalized learning plans
* Dynamic technology roadmaps
* Goal-based progression

### 📚 Resource Recommendation Agent

* Courses
* Documentation
* Tutorials
* GitHub repositories
* Learning resources

### 🎤 Interview Preparation Agent

* Technical questions
* HR questions
* Mock interview preparation

### 📈 Progress Tracking Agent

* Skill progress monitoring
* Roadmap completion tracking
* Learning analytics

### 💬 AI Career Mentor Chatbot

* Career guidance
* Technology recommendations
* Resume advice
* Learning support
* Continuous mentoring

---

## 🧠 Multi-Agent System Architecture

```mermaid
graph TD
    User[User] --> O[Orchestrator Agent]

    O --> R[Resume Analysis Agent]
    O --> A[ATS Optimization Agent]
    O --> C[Career Recommendation Agent]
    O --> S[Skill Gap Analysis Agent]
    O --> L[Learning Roadmap Agent]
    O --> RR[Resource Recommendation Agent]
    O --> I[Interview Preparation Agent]
    O --> P[Progress Tracking Agent]
    O --> B[AI Career Mentor Chatbot]

    R --> G[Gemini AI]
    A --> G
    C --> G
    S --> G
    L --> G
    RR --> G
    I --> G
    P --> G
    B --> G

    G --> D[Interactive Career Dashboard]
```

---

## 🔄 Agent Collaboration Workflow

```text
Resume Upload
      │
      ▼
Resume Analysis Agent
      │
      ▼
ATS Optimization Agent
      │
      ▼
Career Recommendation Agent
      │
      ▼
Skill Gap Analysis Agent
      │
      ▼
Learning Roadmap Agent
      │
      ▼
Resource Recommendation Agent
      │
      ▼
Interview Preparation Agent
      │
      ▼
Progress Tracking Agent
      │
      ▼
AI Career Mentor Chatbot
```

This workflow demonstrates how agents communicate and collaborate to provide personalized recommendations.

---

## 🧠 AI Memory Layer

CareerPilot AI maintains user-specific context through:

* Career Goals
* Skills Profile
* Resume History
* Learning Progress
* Interview Performance
* Chat History

This enables adaptive recommendations and personalized career mentoring.

---

## 🛠️ Technology Stack

### Frontend

* HTML5
* CSS3
* Bootstrap 5
* JavaScript

### Backend

* Python
* Flask

### Database

* SQLite
* SQLAlchemy

### Artificial Intelligence

* Google Gemini API

### Libraries

* PyPDF2
* pdfplumber
* Flask-Login
* Werkzeug
* python-dotenv

---

## 📁 Project Structure

```text
Agentic-Autonomous-Systems/

├── app.py
├── config.py
├── requirements.txt
├── .env.example

├── agents/
│   ├── orchestrator_agent.py
│   ├── resume_agent.py
│   ├── ats_agent.py
│   ├── career_agent.py
│   ├── skill_gap_agent.py
│   ├── roadmap_agent.py
│   ├── resource_agent.py
│   ├── interview_agent.py
│   ├── progress_agent.py
│   └── chatbot_agent.py

├── services/
│   ├── gemini_service.py
│   ├── pdf_service.py
│   └── resume_parser.py

├── database/
│   ├── db.py
│   └── models.py

├── routes/
├── templates/
├── static/
├── uploads/
└── docs/
```

---

## 🗄️ Database Schema

### Users

Stores user account information.

### Resumes

Stores uploaded resume files.

### Skills

Stores identified user skills.

### Career Recommendations

Stores generated career suggestions.

### Roadmaps

Stores personalized learning roadmaps.

### Progress Tracker

Stores milestone completion data.

### Interview Sessions

Stores interview evaluation results.

### Chat History

Stores chatbot conversations.

---

## 📊 Expected Outcomes

* Improved ATS Resume Scores
* Faster Skill Gap Identification
* Personalized Learning Plans
* Better Interview Readiness
* Continuous Career Development Support

---

## 📸 Screenshots

Add screenshots here:

* Dashboard Overview
* Resume Upload Page
* Resume Analysis Results
* Learning Roadmap
* Career Recommendations
* AI Career Mentor Chatbot

---

## 🧪 Installation

```bash
git clone https://github.com/yourusername/Agentic-Autonomous-Systems.git

cd "Agentic-Autonomous-Systems/Agentic & Autonomous Systems/CareerPilot AI Agent"

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt

# Windows PowerShell
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env

# Set SECRET_KEY in .env. Set GEMINI_API_KEY when you want to enable AI chat.

python app.py
```

## 🚀 Deploying to Vercel

The Flask app is configured for Vercel. When importing the repository, set the
Vercel project root directory to:

```text
Agentic & Autonomous Systems/CareerPilot AI Agent
```

Before deploying, add these environment variables in the Vercel project
settings:

| Variable | Required | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | Yes | Flask session signing; generate a unique random value |
| `DATABASE_URL` | Yes | Connection string for a managed PostgreSQL database |
| `S3_BUCKET` | Yes for resume uploads | Private S3-compatible object-storage bucket |
| `AWS_ACCESS_KEY_ID` | Yes for resume uploads | Object-storage access key |
| `AWS_SECRET_ACCESS_KEY` | Yes for resume uploads | Object-storage secret key |
| `GEMINI_API_KEY` | No | Enables Gemini-powered chatbot responses |
| `GEMINI_MODEL` | No | Overrides the default Gemini model |
| `S3_REGION` | No | Object-storage region; use `auto` if required by the provider |
| `S3_ENDPOINT_URL` | No | Endpoint for S3-compatible providers such as Cloudflare R2 |

Use the database provider's pooled PostgreSQL connection string when available.
Keep the object-storage bucket private and restrict its credentials to writing
objects under the `resumes/` prefix. Do not commit `.env` files, database files,
or uploaded resumes. The app keeps SQLite and local uploads for development,
but requires PostgreSQL on Vercel and requires S3-compatible storage when a
resume is uploaded there. Vercel uploads are limited to 4 MB to stay within
serverless request-size limits.

The site can deploy before `GEMINI_API_KEY` is set; AI chat will remain
unavailable until the key is added. Copy `.env.example` to `.env` for local
development and set a separate local `SECRET_KEY`.

---

## 🔬 Research Contribution

CareerPilot AI introduces a collaborative multi-agent framework where autonomous AI agents communicate through an Orchestrator Agent to continuously analyze user progress, adapt learning pathways, and provide intelligent career guidance.

This architecture combines:

* Agentic AI
* Personalized Learning
* Career Intelligence
* Resume Analytics
* Conversational AI

within a unified platform.

---

## 🚀 Future Enhancements

* Voice-Based Career Assistant
* Mobile Application
* Real-Time Job API Integration
* Advanced RAG Implementation
* Multi-Language Support
* Industry-Specific AI Models

---

## 👨‍💻 Author

**Ayush Panda**

M.Sc. Information Technology(Artificial Intelligence) (2026)

CareerPilot AI Project

---

## ⭐ Support

If you found this project useful, consider giving it a star on GitHub.

---

## 📄 License

This project is developed for educational and research purposes.
