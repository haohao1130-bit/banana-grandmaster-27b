"""Gemma 3 12B Q5 director transport and CUDA args; no GPU or network required."""
import unittest
from unittest.mock import patch
from PIL import Image
from banana_mv import llama27b


class Gemma12BTests(unittest.TestCase):
    def test_multimodal_order_and_no_system_role(self):
        a = Image.new("RGB", (16, 16), "red")
        b = Image.new("RGB", (16, 16), "blue")
        messages = llama27b._messages("identity and current event rules", [
            ("text", "<Picture 1>"), ("image", a),
            ("text", "<Picture 2>"), ("image", b),
        ])
        self.assertEqual([m["role"] for m in messages], ["user"])
        content = messages[0]["content"]
        self.assertEqual([p["type"] for p in content],
                         ["text", "text", "image_url", "text", "image_url"])
        self.assertIn("identity and current event rules", content[0]["text"])
        self.assertNotEqual(content[2]["image_url"]["url"], content[4]["image_url"]["url"])
        self.assertTrue(content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_thinking_filtered(self):
        self.assertEqual(llama27b._clean_output("<think>private</think>subject_definitions: yes"),
                         "subject_definitions: yes")
        self.assertEqual(llama27b._clean_output("<think>unfinished"), "")

    def test_default_12b_q5_multimodal_gpu_budget(self):
        s = llama27b._settings({"rewriter": {"port": 8217}})
        self.assertEqual(s["host"], "127.0.0.1")
        self.assertEqual(s["context"], 16384)
        self.assertEqual(s["gpu_layers"], 99)
        self.assertEqual(s["max_tokens"], 8192)
        self.assertIn("gemma-3-12b-it-Q5_K_M.gguf", str(s["model"]))
        self.assertIn("mmproj-google_gemma-3-12b-it-f16.gguf", str(s["mmproj"]))
        argv = llama27b._launch_args(s)
        for flag, expected in [
            ("-c", "16384"), ("-ngl", "99"), ("-fit", "on"),
            ("-fitt", "512"), ("-ctk", "q8_0"), ("-ctv", "q8_0"),
            ("-np", "1"), ("-fa", "auto")]:
            self.assertEqual(argv[argv.index(flag)+1], expected)
        self.assertIn("--no-mmproj-offload", argv)
        self.assertNotIn("--mmproj-offload", argv)

    def test_custom_numeric_layers_and_port_guard(self):
        self.assertEqual(llama27b._gpu_layers(25), 25)
        self.assertEqual(llama27b._gpu_layers("auto"), "auto")
        self.assertEqual(llama27b._gpu_layers("all"), 99)
        self.assertRaisesRegex(ValueError, "gpu_layers", llama27b._gpu_layers, -1)
        self.assertRaisesRegex(ValueError, "gpu_layers", llama27b._gpu_layers, "bad")
        self.assertRaisesRegex(ValueError, "port",
                               llama27b._settings, {"rewriter": {"port": 80}})

    def test_no_remote_provider_fallback(self):
        with patch.object(llama27b, "ensure_running", side_effect=FileNotFoundError("missing GGUF")):
            self.assertRaisesRegex(FileNotFoundError, "missing GGUF",
                                   llama27b.generate, {}, "system", [("text", "story")], "job")


if __name__ == "__main__":
    unittest.main()
