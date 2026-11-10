import json
import unittest
from pathlib import Path

from icons import icon_markup

ROOT = Path(__file__).resolve().parents[1]


class IconTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / 'data/icons.json').read_text(encoding='utf-8'))

    def test_all_champions_have_complete_skill_icons(self):
        self.assertEqual(len(self.catalog['champions']), 71)
        for skills in self.catalog['champions'].values():
            self.assertEqual(set(skills), {'Q', 'W', 'E', 'R', 'ULT', 'パッシブ'})
            self.assertEqual(skills['ULT'], skills['R'])

    def test_every_referenced_asset_is_a_local_png(self):
        references = list(self.catalog['terms'].values())
        references += [icon for skills in self.catalog['champions'].values() for icon in skills.values()]
        for icon in references:
            path = ROOT / 'docs' / icon['src']
            self.assertTrue(path.is_file(), icon['src'])
            self.assertTrue(path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))

    def test_skill_icons_belong_to_selected_champion(self):
        urgot = self.catalog['champions']['アーゴット']['E']['src']
        jax = self.catalog['champions']['ジャックス']['E']['src']
        self.assertNotEqual(urgot, jax)
        self.assertIn('ディスデイン', icon_markup('E使用後を叩く', 'アーゴット', True))

    def test_preserves_text_and_escapes_html(self):
        markup = icon_markup('<script>alert(1)</script> フラッシュ', 'アーゴット', True)
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)
        self.assertIn('フラッシュ', markup)
        self.assertIn('<img ', markup)

    def test_skills_are_not_confused_with_abbreviations(self):
        self.assertNotIn('<img ', icon_markup('MRとASを確認', 'アーゴット', True))
        self.assertNotIn('<img ', icon_markup('レネクトンWを使う', 'アンベッサ'))

    def test_urgot_items_and_rune_are_available(self):
        for name in ['プレスアタック', 'フラッシュ', 'ワーデンメイル', 'プレートスチールキャップ']:
            self.assertIn(name, self.catalog['terms'])


if __name__ == '__main__':
    unittest.main()
