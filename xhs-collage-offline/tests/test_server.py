import tempfile
import unittest
from pathlib import Path

from server import safe_image_extension, store_asset


class AssetStorageTest(unittest.TestCase):
    def test_rejects_non_image_content_type(self):
        with self.assertRaises(ValueError):
            safe_image_extension("notes.txt", "text/plain")

    def test_stores_duplicate_image_once_by_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            first = store_asset(b"fake-image", "photo.jpg", "image/jpeg", Path(directory))
            second = store_asset(b"fake-image", "copy.jpg", "image/jpeg", Path(directory))
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(len(list(Path(directory).iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
