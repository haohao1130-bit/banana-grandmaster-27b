"""12B authored Chinese actor/SRT bindings and one-time entrances."""
import unittest

from banana_mv.clip_cast import explicit_bindings, first_appearances, clip_visibility


class AuthoredCastBindingTests(unittest.TestCase):
    def test_full_song_inline_identity_handoff(self):
        brief = "身份交棒：S1＝蕉大師＝@圖片1；S2＝白素貞＝@圖片2。"
        self.assertEqual(explicit_bindings(brief, 2),
                         {"S1": "<Picture 1>", "S2": "<Picture 2>"})

    def test_character_heading_with_slash_role_and_description(self):
        brief = (
            "【角色設定】\n"
            "@圖片1 蕉大師／S1：成年東亞男性，掌持木魚，僧衣。\n"
            "@圖片2 白素貞／S2：成年女性，長蛇尾。\n"
        )
        self.assertEqual(explicit_bindings(brief, 2),
                         {"S1": "<Picture 1>", "S2": "<Picture 2>"})

    def test_independent_name_alias_lines(self):
        brief = "@圖片1 蕉大師\nS1 蕉大師\n@圖片2 白素貞\nS2 白素貞"
        self.assertEqual(explicit_bindings(brief, 2),
                         {"S1": "<Picture 1>", "S2": "<Picture 2>"})

    def test_reversed_reference_order_is_explicit_not_assumed(self):
        brief = "身份交棒：S1＝蕉大師＝@圖片2；S2＝白素貞＝@圖片1"
        self.assertEqual(explicit_bindings(brief, 2),
                         {"S1": "<Picture 2>", "S2": "<Picture 1>"})

    def test_naked_srt_role_labels_do_not_infer_picture_order(self):
        self.assertEqual(explicit_bindings("[S1] 一句歌詞\n[S2] 下一句歌詞", 2), {})

    def test_chinese_chuci_lumian_is_a_time_locked_first_entrance(self):
        brief = (
            "00:00.000–00:01.205 白素貞初次現身，S1 不出場。\n"
            "00:16.600–00:17.813 木魚特寫，蕉大師仍未出場。\n"
            "00:17.813–00:18.979 S1 初次露面唱阿彌陀蕉。\n"
        )
        self.assertEqual(first_appearances(brief)["S1"], 17.813)
        bindings = {"S1": "<Picture 1>", "S2": "<Picture 2>"}
        absent = clip_visibility("白素貞演唱。", brief,
                                 {"start": 0, "seconds": 10}, bindings,
                                 [{"subjects": ["S2"]}])
        self.assertEqual(absent["S1"]["status"], "absent")
        arrival = clip_visibility("木魚特寫後蕉大師入鏡。", brief,
                                  {"start": 10, "seconds": 10}, bindings, [])
        self.assertEqual(arrival["S1"]["status"], "entry")
        self.assertAlmostEqual(arrival["S1"]["at"], 7.813)

    def test_untimed_first_entrance_is_not_invented(self):
        self.assertEqual(first_appearances("S1 初次露面。"), {})


if __name__ == "__main__":
    unittest.main()
