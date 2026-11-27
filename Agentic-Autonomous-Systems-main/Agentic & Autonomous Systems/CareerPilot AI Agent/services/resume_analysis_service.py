import io
import re
import zipfile
from urllib.parse import quote_plus
from xml.etree import ElementTree

import pdfplumber


SKILL_LABELS = {
    "python": "Python",
    "java": "Java",
    "c++": "C++",
    "c#": "C#",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "react": "React",
    "node.js": "Node.js",
    "flask": "Flask",
    "django": "Django",
    "aws": "AWS",
    "azure": "Azure",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "git": "Git",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "power bi": "Power BI",
    "tableau": "Tableau",
    "excel": "Excel",
    "data analysis": "Data Analysis",
    "marketing": "Marketing",
    "sales": "Sales",
    "finance": "Finance",
    "accounting": "Accounting",
    "communication": "Communication",
    "leadership": "Leadership",
    "figma": "Figma",
    "photoshop": "Photoshop",
    "illustrator": "Illustrator",
    "patient care": "Patient Care",
    "clinical research": "Clinical Research",
    "pharmacology": "Pharmacology",
    "legal research": "Legal Research",
    "agronomy": "Agronomy",
    "project management": "Project Management",
}

ROLE_REQUIREMENTS = {
    "Python Developer": ["Python", "SQL", "Git", "Flask"],
    "Full Stack Developer": ["HTML", "CSS", "JavaScript", "React", "Node.js", "SQL"],
    "Data Analyst": ["Excel", "SQL", "Power BI", "Python", "Data Analysis"],
    "Data Scientist": ["Python", "Machine Learning", "Pandas", "NumPy", "SQL"],
    "AI / ML Engineer": ["Python", "Machine Learning", "TensorFlow", "PyTorch"],
    "Cloud / DevOps Engineer": ["AWS", "Docker", "Kubernetes", "Git", "Python"],
    "Marketing Specialist": ["Marketing", "Data Analysis", "Communication", "Excel"],
    "Financial Analyst": ["Finance", "Accounting", "Excel", "SQL"],
    "Product Designer": ["Figma", "Communication", "Project Management"],
    "Healthcare Research Associate": ["Clinical Research", "Patient Care", "Communication"],
    "Legal Research Associate": ["Legal Research", "Communication", "Project Management"],
    "Agriculture Specialist": ["Agronomy", "Data Analysis", "Project Management"],
}

LEARNING_SEARCHES = {
    "Python": "Python programming course",
    "SQL": "SQL for beginners course",
    "Git": "Git and GitHub tutorial",
    "Flask": "Flask web development tutorial",
    "HTML": "HTML tutorial for beginners",
    "CSS": "CSS tutorial for beginners",
    "JavaScript": "JavaScript full course",
    "React": "React course for beginners",
    "Node.js": "Node.js tutorial",
    "Excel": "Excel skills course",
    "Power BI": "Power BI beginner tutorial",
    "Data Analysis": "data analysis course",
    "Machine Learning": "machine learning course",
    "Pandas": "Python Pandas tutorial",
    "NumPy": "NumPy tutorial",
    "TensorFlow": "TensorFlow tutorial",
    "PyTorch": "PyTorch tutorial",
    "AWS": "AWS cloud practitioner course",
    "Docker": "Docker course for beginners",
    "Kubernetes": "Kubernetes fundamentals course",
    "Marketing": "digital marketing course",
    "Finance": "financial analysis course",
    "Accounting": "accounting fundamentals course",
    "Figma": "Figma UI UX course",
    "Communication": "professional communication skills course",
    "Project Management": "project management fundamentals course",
    "Clinical Research": "clinical research fundamentals course",
    "Patient Care": "patient care fundamentals course",
    "Legal Research": "legal research skills course",
    "Agronomy": "agronomy course",
}


def extract_resume_text(filename, content):
    suffix = filename.rsplit(".", 1)[-1].lower()
    stream = io.BytesIO(content)
    if suffix == "pdf":
        with pdfplumber.open(stream) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
    if suffix == "docx":
        with zipfile.ZipFile(stream) as archive:
            document = ElementTree.fromstring(archive.read("word/document.xml"))
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        return "\n".join(
            " ".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
            for paragraph in document.iter(f"{namespace}p")
        ).strip()
    return ""


def _contains(text, term):
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", text))


def _contact_details(text):
    email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    phone_match = re.search(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)", text)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return {
        "name_or_heading": first_line[:120] if first_line else None,
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0).strip() if phone_match else None,
    }


def analyze_resume(text):
    normalized = text.lower()
    skills = sorted(
        (label for keyword, label in SKILL_LABELS.items() if _contains(normalized, keyword)),
        key=str.casefold,
    )
    skill_set = set(skills)
    role_matches = []
    for role, required in ROLE_REQUIREMENTS.items():
        matched = [skill for skill in required if skill in skill_set]
        if not matched:
            continue
        missing = [skill for skill in required if skill not in skill_set]
        role_matches.append({
            "title": role,
            "match_percent": round(100 * len(matched) / len(required)),
            "matched_skills": matched,
            "missing_skills": missing,
            "jobs_url": "https://www.google.com/search?ibp=htl;jobs&q=" + quote_plus(role + " jobs"),
            "indeed_url": "https://www.indeed.com/jobs?q=" + quote_plus(role),
        })
    role_matches.sort(key=lambda item: (-item["match_percent"], item["title"]))
    role_matches = role_matches[:5]

    missing_skills = sorted(
        {skill for role in role_matches for skill in role["missing_skills"]},
        key=str.casefold,
    )
    learning = [
        {
            "skill": skill,
            "youtube_url": "https://www.youtube.com/results?search_query=" + quote_plus(LEARNING_SEARCHES.get(skill, skill + " course tutorial")),
            "coursera_url": "https://www.coursera.org/search?query=" + quote_plus(skill),
        }
        for skill in missing_skills[:10]
    ]
    text_words = re.findall(r"\b\w+\b", text)
    return {
        "summary": {
            "word_count": len(text_words),
            "skills_found": len(skills),
            "contact_details": _contact_details(text),
            "sections_found": [
                section for section, pattern in (
                    ("Experience", r"\b(experience|employment|work history)\b"),
                    ("Education", r"\b(education|academic|degree)\b"),
                    ("Projects", r"\b(projects|portfolio)\b"),
                ) if re.search(pattern, text, re.I)
            ],
        },
        "skills": skills,
        "job_matches": role_matches,
        "learning_resources": learning,
        "notice": "Role fit is an indicative keyword match, not a hiring decision. Job links open live search results; availability and eligibility can change.",
    }
