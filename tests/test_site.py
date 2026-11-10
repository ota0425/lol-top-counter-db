import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicSiteTests(unittest.TestCase):
    def test_public_data_matches_visible_counter_notes(self):
        html = (ROOT / 'docs/index.html').read_text(encoding='utf-8')
        payload = re.search(r'<script id="counter-data" type="application/json">(.*?)</script>', html, re.S)[1]
        data = json.loads(payload)
        self.assertEqual(len(data), 50)
        self.assertEqual(sum(len(c['tips']) for c in data), 202)
        self.assertEqual(sum(len(c['checklist']) for c in data), 250)
        self.assertEqual(sum(len(c['supplements']) for c in data), 37)
        self.assertEqual(set(data[0]), {'name', 'aliases', 'tips', 'checklist', 'supplements'})
        source = json.loads((ROOT / 'data/counters.json').read_text(encoding='utf-8'))['champions']
        for champion in data:
            self.assertEqual(len(champion['checklist']), 5)
            original = next(c for c in source if c['name'] == champion['name'])
            self.assertEqual(champion['checklist'], original['checklist'])
            self.assertEqual(champion['supplements'], [s['detail'] for s in original['supplements']])
            for tip in champion['tips']:
                self.assertEqual(set(tip), {'category', 'detail'})
        self.assertNotIn('__COUNTER_DATA__', html)
        self.assertNotIn('根拠付近の自動字幕', html)
        self.assertNotIn('source_sec', payload)

    def test_search_script_is_valid_javascript(self):
        import shutil
        if not shutil.which('node'):
            self.skipTest('Node.js is only needed for this development check')
        html = (ROOT / 'docs/index.html').read_text(encoding='utf-8')
        script = re.findall(r'<script>(.*?)</script>', html, re.S)[0]
        result = subprocess.run(['node', '--check'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
