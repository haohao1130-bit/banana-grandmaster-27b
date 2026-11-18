"""Regression for the actual authored 【ACT ...】 format (no new allocator)."""
import tempfile
import unittest
from pathlib import Path

from banana_mv.core import map_image_mentions
from banana_mv.python_slots import (
    _normalize_authored_act_notation, ensure_python_slot_plan,
)
from banana_mv.timed_slots import parse_timed_source
from banana_mv.commission_guard import role_pictures


BRIEF = (
    "身份交棒：S1＝蕉大師＝@圖片1；S2＝白素貞＝@圖片2。\n"
    "【角色設定】\n"
    "@圖片1 蕉大師／S1：持木魚；演唱時主動入鏡。\n"
    "@圖片2 白素貞／S2：真正承重的蛇身與蛇尾。\n"
    "【世界與場景】\n"
    "A 雷峰塔遺址：暴雨夜。\n"
    "B 荒廢古寺：木魚。\n"
    "【ACT 01｜00:00.000–00:22.800｜SRT 1–6｜千年殺劫】\n"
    "00:00.000–00:01.205 純器樂：雷峰塔暴雨；蕉大師未出場。\n"
    "00:01.205–00:03.300 S2 唱千年劫：白素貞昂起蛇軀。\n"
    "00:03.300–00:06.064 無人聲：蛇身推進石階。\n"
    "00:06.064–00:08.260 S2 唱雷峰塔影：白素貞沿石階滑行。\n"
    "00:08.260–00:09.656 無人聲：水柱升起。\n"
    "00:09.656–00:12.970 S2 唱法海：白素貞正面近景。\n"
    "00:16.600–00:17.813 無人聲：木魚獨立特寫，不見蕉大師。\n"
    "00:17.813–00:18.979 S1 初次露面：蕉大師正面出場。\n"
    "00:19.764–00:22.800 S1 澄清誤會。\n"
    "【ACT 02｜00:22.800–00:30.000｜SRT 7–10｜白蛇開戰】\n"
    "00:22.800–00:30.000 S2 白素貞與蕉大師交鋒。\n"
    "【H3 攝影與交稿規則】\n"
    "1. 只能拍當段事件，不要提前出場。\n"
)


class Test12BBracketedACT(unittest.TestCase):
    def test_bracketed_act_uses_original_timed_allocator(self):
        source = map_image_mentions(BRIEF, 2)
        adapted = _normalize_authored_act_notation(source)
        fixed, chapters = parse_timed_source(adapted)
        self.assertEqual(len(chapters), 2)
        self.assertEqual([(c['start'], c['end']) for c in chapters],
                         [(0.0, 22.8), (22.8, 30.0)])
        self.assertEqual(role_pictures(fixed),
                         {'S1': '<Picture 1>', 'S2': '<Picture 2>'})
        self.assertIn('1. 只能拍當段事件', fixed)
        self.assertNotIn('1. 只能拍當段事件', str(chapters))

    def test_first_10_seconds_are_the_snake_not_project_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = {
                'prompt': BRIEF, 'director': 'auto', 'story_plan': True,
                'project_scope': 'full', 'director_schema': 6,
                'ending_policy_version': 2, 'mode': 'independent',
                'srt_cues': [{'start': 1.205, 'end': 3.3,
                              'text': '[S2] 千年劫'}],
            }
            segments = [
                {'index': i, 'start': i * 10.0, 'seconds': 10.0,
                 'song_seconds': 30.0, 'segment_count': 3}
                for i in range(3)
            ]
            plan = ensure_python_slot_plan(
                req, segments,
                [Path(tmp) / 'snake_role1.png', Path(tmp) / 'snake_role2.png'],
                tmp)
            opening = plan['segments'][0]['event']
            second = plan['segments'][1]['event']
            self.assertEqual(plan['source_timing'], 'explicit_markdown')
            self.assertIn('雷峰塔暴雨', opening)
            self.assertIn('白素貞昂起蛇軀', opening)
            self.assertIn('蕉大師未出場', opening)
            self.assertNotIn('S1 初次露面', opening)
            self.assertNotIn('S1 澄清誤會', opening)
            self.assertNotIn('持木魚；演唱時主動入鏡', opening)
            self.assertIn('S1 初次露面', second)


if __name__ == '__main__':
    unittest.main()
