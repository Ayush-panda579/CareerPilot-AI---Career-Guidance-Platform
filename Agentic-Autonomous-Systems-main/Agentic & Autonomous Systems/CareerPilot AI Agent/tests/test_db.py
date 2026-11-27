import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "DATABASE_URL": "",
                "POSTGRES_URL": "",
                "VERCEL": "",
                "SQLITE_PATH": str(
                    Path(self.temporary_directory.name) / "test.db"
                ),
            },
        )
        self.environment.start()
        db.init_db()

    def tearDown(self):
        self.environment.stop()
        self.temporary_directory.cleanup()

    def test_sqlite_user_creation_and_duplicate_handling(self):
        db.create_user("alice", "alice@example.test", "hashed-password")

        self.assertEqual(db.get_user("alice")["email"], "alice@example.test")
        with self.assertRaises(db.DuplicateUserError):
            db.create_user("alice", "another@example.test", "hashed-password")
        with self.assertRaises(db.DuplicateUserError):
            db.create_user("bob", "alice@example.test", "hashed-password")

    def test_vercel_requires_managed_database(self):
        with patch.dict(os.environ, {"VERCEL": "1"}):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                db.get_conn()


if __name__ == "__main__":
    unittest.main()
