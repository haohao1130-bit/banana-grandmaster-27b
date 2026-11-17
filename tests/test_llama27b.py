"""27B-only transport tests; no model download, GPU, or HTTP server needed."""
import json
import unittest
from unittest.mock import patch
from PIL import Image
from banana_mv import llama27b


class Llama27BTests(unittest.TestCase):
    def test_multimodal_part_order_and_image_separation(self):
        a = Image.new("RGB", (16, 16), "red")
        b = Image.new("RGB", (16, 16), "blue")
        messages = llama27b._messages("system", [
            ("text", "<Picture 1>"),
            ("image", a),
            ("text", "<Picture 2>"),
            ("image", b),
        ])
        self.assertEqual([piece["type"] for piece in messages[1]["content"]],
                         ["text", "image_url", "text", "image_url"])
        self.assertNotEqual(messages[1]["content"][1]["image_url"]["url"],
                            messages[1]["content"][3]["image_url"]["url"])
        self.assertTrue(messages[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_thinking_does_not_leak_to_h3(self):
        self.assertEqual(llama27b._clean_output("<think>private analysis</think>subject_definitions: ok"),
                         "subject_definitions: ok")
        self.assertEqual(llama27b._clean_output("<think>unfinished"), "")

    def test_director_27b_settings_are_local(self):
        settings = llama27b._settings({"rewriter": {"port": 8217, "gpu_layers": 12}})
        self.assertEqual(settings["host"], "127.0.0.1")
        self.assertEqual(settings["gpu_layers"], 12)
        self.assertEqual(settings["port"], 8217)
        with self.assertRaisesRegex(ValueError, "port"):
            llama27b._settings({"rewriter": {"port": 80}})

    def test_no_implicit_provider_fallback(self):
        with patch.object(llama27b, "ensure_running", side_effect=FileNotFoundError("missing GGUF")):
            with self.assertRaisesRegex(FileNotFoundError, "missing GGUF"):
                llama27b.generate({}, "system", [("text", "story")], "job")


if __name__ == "__main__":
    unittest.main()
