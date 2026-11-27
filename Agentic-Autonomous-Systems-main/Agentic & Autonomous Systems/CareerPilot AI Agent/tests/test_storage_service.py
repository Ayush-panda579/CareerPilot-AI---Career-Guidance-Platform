import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.datastructures import FileStorage

from services.storage_service import (
    StorageConfigurationError,
    save_upload,
)


class StorageServiceTests(unittest.TestCase):
    def test_local_upload_is_saved_to_configured_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            upload = FileStorage(
                stream=io.BytesIO(b"resume bytes"),
                filename="resume.pdf",
            )

            with patch.dict(
                os.environ,
                {"VERCEL": "", "S3_BUCKET": ""},
            ):
                save_upload(upload, "unique_resume.pdf", temporary_directory)

            saved_file = Path(temporary_directory) / "unique_resume.pdf"
            self.assertEqual(saved_file.read_bytes(), b"resume bytes")

    def test_vercel_upload_requires_external_storage(self):
        with patch.dict(
            os.environ,
            {"VERCEL": "1", "S3_BUCKET": ""},
        ):
            with self.assertRaisesRegex(
                StorageConfigurationError,
                "S3_BUCKET",
            ):
                save_upload(
                    FileStorage(stream=io.BytesIO(b"resume bytes")),
                    "unique_resume.pdf",
                    "unused",
                )


if __name__ == "__main__":
    unittest.main()
