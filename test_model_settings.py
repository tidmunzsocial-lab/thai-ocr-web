import unittest
import base64
from io import BytesIO
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

import web_app
import typhoon_fast_worker
from PIL import Image


class ModelSettingsTest(unittest.TestCase):
    def test_mac_fast_settings_reduce_memory(self):
        self.assertEqual(typhoon_fast_worker.runtime_settings("darwin"), (4096, 1600, "30s"))
        self.assertEqual(typhoon_fast_worker.runtime_settings("win32"), (8192, None, "2m"))

    def test_mac_image_is_resized_before_ocr(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "large.png"
            Image.new("RGB", (2400, 1200), "white").save(path)
            encoded = typhoon_fast_worker.encode_image(path, 1600)
            with Image.open(BytesIO(base64.b64decode(encoded))) as resized:
                self.assertEqual(resized.size, (1600, 800))

    def test_small_model_size_uses_mb(self):
        self.assertEqual(web_app._format_size(42 * 1024**2), "42 MB")

    def test_status_reports_installed_size(self):
        with patch.object(web_app, "_fast_model_info", return_value={"size": 4 * 1024**3}):
            self.assertIn("4.0 GB", web_app.fast_model_status())

    def test_status_reports_missing_model(self):
        with patch.object(web_app, "_fast_model_info", return_value=None):
            self.assertIn("ยังไม่ได้ติดตั้ง", web_app.fast_model_status())

    def test_clear_saved_jobs_only_clears_output_folder(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "outputs" / "web"
            (output / "old-job").mkdir(parents=True)
            (output / "old-job" / "result.md").write_text("old", encoding="utf-8")
            keep = root / "keep.txt"
            keep.write_text("keep", encoding="utf-8")
            with patch.object(web_app, "ROOT", root), patch.object(web_app, "OUTPUT_ROOT", output):
                message, confirmed, _ = web_app.clear_saved_jobs(True)
            self.assertIn("1 รายการ", message)
            self.assertFalse(confirmed)
            self.assertEqual(list(output.iterdir()), [])
            self.assertTrue(keep.exists())

    def test_remove_selected_model_leaves_other_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            unlimited = root / "models" / "Unlimited-OCR"
            unlimited.mkdir(parents=True)
            (unlimited / "model.bin").write_bytes(b"model")
            keep = root / "keep.txt"
            keep.write_text("keep", encoding="utf-8")
            with patch.object(web_app, "MODEL_PATH", unlimited):
                message, selected, confirmed = web_app.remove_selected_models(["Unlimited-OCR"], True)
            self.assertIn("Unlimited-OCR", message)
            self.assertEqual(selected, [])
            self.assertFalse(confirmed)
            self.assertFalse(unlimited.exists())
            self.assertTrue(keep.exists())

    def test_uninstalled_models_are_hidden_from_engine_choices(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            with (
                patch.object(web_app, "MODEL_PATH", missing / "unlimited"),
                patch.object(web_app, "TYPHOON_MODEL_PATH", missing / "typhoon"),
                patch.object(web_app, "PADDLE_MODEL_PATHS", [missing / "det", missing / "rec"]),
                patch.object(web_app, "_fast_model_info", return_value=None),
            ):
                self.assertEqual(web_app.available_engines(), [])


if __name__ == "__main__":
    unittest.main()
