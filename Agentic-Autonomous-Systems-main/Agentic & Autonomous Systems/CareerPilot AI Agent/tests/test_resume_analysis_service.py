import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from services.resume_analysis_service import analyze_resume, extract_resume_text


class ResumeAnalysisTests(unittest.TestCase):
    def test_detects_skills_and_generates_role_and_learning_links(self):
        result = analyze_resume(
            "Jordan Lee\nEmail jordan@example.test\nExperience\n"
            "Python developer using Python, SQL, Git and Flask."
        )

        self.assertEqual(result["summary"]["contact_details"]["email"], "jordan@example.test")
        self.assertIn("Experience", result["summary"]["sections_found"])
        self.assertEqual(result["skills"], ["Flask", "Git", "Python", "SQL"])
        self.assertEqual(result["job_matches"][0]["title"], "Python Developer")
        self.assertIn("jobs", result["job_matches"][0]["jobs_url"])
        self.assertTrue(result["learning_resources"])
        self.assertIn("youtube.com", result["learning_resources"][0]["youtube_url"])

    def test_skill_detection_does_not_match_single_letters_inside_words(self):
        result = analyze_resume("A professional candidate with varied experience.")
        self.assertNotIn("Python", result["skills"])
        self.assertNotIn("Java", result["skills"])

    def test_unsupported_legacy_word_format_is_not_misread(self):
        self.assertEqual(extract_resume_text("resume.doc", b"legacy binary"), "")


if __name__ == "__main__":
    unittest.main()
