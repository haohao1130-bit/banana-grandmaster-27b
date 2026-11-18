"""27B regression: cast references never become early on-screen performers."""
import unittest
from unittest.mock import patch

from banana_mv.clip_cast import (
    explicit_bindings, first_appearances, clip_visibility,
    visibility_lines, premature_cast_errors,
)
from banana_mv.shoot_plan import write_shoot_prompt


WHITE_SNAKE = """
@圖片1＝蕉大師，S1，成年男性
@圖片2＝白素貞，S2，成年女性
00:16.600–00:17.813
古寺木魚特寫。只有木魚與木槌，沒有和尚身體。
00:17.813–00:22.800
S1 蕉大師首次入鏡，開口演唱。
"""


class ExplicitCastTests(unittest.TestCase):
    def test_single_line_role_mapping(self):
        self.assertEqual(explicit_bindings(WHITE_SNAKE, 2),
                         {"S1": "<Picture 1>", "S2": "<Picture 2>"})

    def test_separate_name_lines_and_extra_stage_image(self):
        brief = ("@圖片1 蕉大師\nS1 蕉大師\n"
                 "@圖片2 白素貞\nS2 白素貞\n"
                 "@圖片3 古寺舞台")
        self.assertEqual(explicit_bindings(brief, 3),
                         {"S1": "<Picture 1>", "S2": "<Picture 2>"})

    def test_does_not_guess_identity_from_picture_order(self):
        self.assertEqual(explicit_bindings(
            "@圖片1 男性\n@圖片2 女性\nS1 主唱\nS2 主唱", 2), {})

    def test_first_appearance_uses_own_time_header(self):
        self.assertAlmostEqual(first_appearances(WHITE_SNAKE)["S1"], 17.813)

    def test_first_clip_has_no_monk_and_next_clip_has_timed_entry(self):
        roles = {"S1": "<Picture 1>", "S2": "<Picture 2>"}
        cues = [{"subjects": ["S2"]}]
        first = clip_visibility(
            "<Picture 2> 白素貞獨自走上雷峰塔", WHITE_SNAKE,
            {"start": 0, "seconds": 10}, roles, cues)
        self.assertEqual(first["S1"]["status"], "absent")
        self.assertEqual(first["S2"]["status"], "available")
        self.assertIn("REFERENCE ONLY", "\n".join(visibility_lines(first)))
        self.assertIn(1, premature_cast_errors(
            {1: "<Subject 1> watches from behind <Subject 2>."}, first))
        self.assertNotIn(2, premature_cast_errors(
            {2: "<Subject 2> travels along the stones."}, first))
        second = clip_visibility(
            "<Picture 2> 白素貞向古寺滑行", WHITE_SNAKE,
            {"start": 10, "seconds": 10}, roles, cues)
        self.assertEqual(second["S1"]["status"], "entry")
        self.assertAlmostEqual(second["S1"]["at"], 7.813)

    def test_no_inferred_debut_without_author_instruction(self):
        policy = clip_visibility(
            "<Picture 2> alone on stage", "S1 = <Picture 1>\nS2 = <Picture 2>",
            {"start": 0, "seconds": 10},
            {"S1": "<Picture 1>", "S2": "<Picture 2>"},
            [{"subjects": ["S2"]}])
        self.assertEqual(policy["S1"]["status"], "absent")


class RouteTests(unittest.TestCase):
    def test_three_image_srt_uses_python_owned_camera_with_no_false_tail(self):
        brief = (
            "S1 蕉大師\n@圖片1 蕉大師\n"
            "S2 白素貞\n@圖片2 白素貞\n"
            "@圖片3 古寺舞台\n"
            "00:17.813–00:22.800\nS1 蕉大師首次入鏡")
        req = {
            "prompt": brief, "director_schema": 6, "story_plan": True,
            "project_scope": "full", "srt_cues": [
                {"start": 1.205, "end": 3.300, "text": "[S2] 千年劫"}
            ]
        }
        clip = {
            "index": 0, "start": 0, "seconds": 10,
            "director_plan": {
                "handoff_version": 1, "mode": "performance",
                "event": "<Picture 2> 白素貞獨自出現在雷峰塔前。"
            },
            "fixed_reference_settings": ""
        }
        called = []
        def camera(*args, **kwargs):
            called.append((args, kwargs))
            return "subject_definitions:\nValid test response."
        with patch("banana_mv.shoot_plan._pictures", return_value=[]), \
             patch("banana_mv.shoot_plan.write_director_shoot_prompt",
                   side_effect=camera):
            output = write_shoot_prompt(
                {}, req, clip, ["photo1", "photo2", "stage3"], None,
                lambda *a: self.fail("Generic director called"))
        self.assertIn("Valid test response", output)
        self.assertEqual(len(called), 1)
        self.assertFalse(called[0][1]["continuation"])
        self.assertEqual(called[0][1]["visibility"]["S1"]["status"], "absent")
        self.assertEqual(clip["director_mode"], "performance")


if __name__ == "__main__":
    unittest.main()
