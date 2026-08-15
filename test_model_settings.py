import unittest
from unittest.mock import patch

import web_app


class ModelSettingsTest(unittest.TestCase):
    def test_status_reports_installed_size(self):
        with patch.object(web_app, "_fast_model_info", return_value={"size": 4 * 1024**3}):
            self.assertIn("4.0 GB", web_app.fast_model_status())

    def test_status_reports_missing_model(self):
        with patch.object(web_app, "_fast_model_info", return_value=None):
            self.assertIn("ยังไม่ได้ติดตั้ง", web_app.fast_model_status())


if __name__ == "__main__":
    unittest.main()
