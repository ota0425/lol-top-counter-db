import unittest
from pathlib import Path

from db import (VIDEO_URL, connect, import_chapters, parse_captions,
                restore_backup, search_key, seconds, install_dataset,
                matches_champion, search_tips, validate_source)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(':memory:')
        self.backup = {'video_url': VIDEO_URL, 'champions': [
            {'name': 'テスト', 'start_sec': 60, 'end_sec': 120, 'tips': [
                {'category': '基本対策', 'detail': 'テスト用データ',
                 'source_sec': 65, 'status': '確認済み'}]}]}

    def tearDown(self):
        self.conn.close()

    def test_search_normalizes_width_and_kana(self):
        self.assertEqual(search_key(' ｱｰｺﾞｯﾄ '), search_key('あーごっと'))

    def test_invalid_times_rejected(self):
        for value in ['-1', '1:99', 'nan', '1::20']:
            with self.assertRaises(ValueError):
                seconds(value)
        self.assertEqual(seconds('1:53:58'), 6838)

    def test_caption_formats(self):
        for time in ['00:01:02,500', '00:01:02.500']:
            rows = parse_captions(f'1\n{time} --> 00:01:04.000\n<b>字幕</b>\n')
            self.assertEqual(rows, [(62, 64, '字幕')])

    def test_restore_is_idempotent(self):
        self.assertEqual(restore_backup(self.conn, self.backup), 1)
        self.assertEqual(restore_backup(self.conn, self.backup), 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tips').fetchone()[0], 1)

    def test_invalid_backup_has_no_partial_writes(self):
        self.backup['champions'].append({'name': '不正', 'start_sec': -1})
        with self.assertRaises(ValueError):
            restore_backup(self.conn, self.backup)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM champions').fetchone()[0], 0)

    def test_conflicting_existing_chapter_rolls_back(self):
        import_chapters(self.conn, '0:00 テスト\n0:30 次')
        with self.assertRaises(ValueError):
            restore_backup(self.conn, self.backup)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tips').fetchone()[0], 0)

    def test_verified_tip_requires_evidence(self):
        self.backup['champions'][0]['tips'][0]['source_sec'] = None
        with self.assertRaises(ValueError):
            restore_backup(self.conn, self.backup)

    def test_chapters_reject_same_start(self):
        with self.assertRaises(ValueError):
            import_chapters(self.conn, '0:00 一\n0:00 二')

    def test_english_and_official_aliases(self):
        for query, name in [('Camille', 'カミール'), ('カ・サンテ', 'カサンテ'),
                            ("Cho'Gath", 'チョガス'), ('ドクター・ムンド', 'ムンド')]:
            self.assertTrue(matches_champion(query, name))

    def test_manual_drafts_stay_hidden(self):
        restore_backup(self.conn, self.backup)
        self.conn.execute("UPDATE tips SET status='未確認'")
        self.conn.commit()
        cid = self.conn.execute('SELECT id FROM champions').fetchone()[0]
        self.assertEqual(len(search_tips(self.conn, cid)), 0)
        self.conn.execute("UPDATE tips SET origin='subtitle_summary'")
        self.conn.commit()
        self.assertEqual(len(search_tips(self.conn, cid)), 1)
        self.assertEqual(len(search_tips(self.conn, cid, False)), 0)

    def test_restore_does_not_duplicate_after_approval(self):
        self.backup['champions'][0]['tips'][0]['status'] = '未確認'
        restore_backup(self.conn, self.backup)
        self.conn.execute("UPDATE tips SET status='確認済み'")
        self.conn.commit()
        self.assertEqual(restore_backup(self.conn, self.backup), 0)

    def test_bundled_data_has_all_champions_and_valid_sources(self):
        install_dataset(self.conn)
        champions = self.conn.execute('SELECT * FROM champions ORDER BY start_sec').fetchall()
        self.assertEqual(len(champions), 50)
        has_transcript = (Path(__file__).resolve().parents[1] / 'data/transcript.ja.json').exists()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM transcript').fetchone()[0], 12377 if has_transcript else 0)
        for champion in champions:
            tips = search_tips(self.conn, champion['id'])
            self.assertGreaterEqual(len(tips), 4)
            for tip in tips:
                validate_source(tip['source_sec'], champion)
                self.assertEqual(tip['status'], '未確認')
                evidence = self.conn.execute('SELECT 1 FROM transcript WHERE ABS(start_sec-?)<6 LIMIT 1', (tip['source_sec'],)).fetchone()
                if has_transcript:
                    self.assertIsNotNone(evidence)

    def test_initialization_preserves_edits_and_deletions(self):
        install_dataset(self.conn)
        self.conn.execute("UPDATE tips SET detail='自分の修正',status='確認済み' WHERE id=1")
        self.conn.execute('DELETE FROM tips WHERE id=2')
        self.conn.commit()
        install_dataset(self.conn)
        self.assertEqual(self.conn.execute('SELECT detail FROM tips WHERE id=1').fetchone()[0], '自分の修正')
        self.assertIsNone(self.conn.execute('SELECT id FROM tips WHERE id=2').fetchone())


if __name__ == '__main__':
    unittest.main()
