import unittest
from pathlib import Path
import json

from db import (VIDEO_URL, connect, import_chapters, parse_captions,
                restore_backup, search_key, seconds, install_dataset,
                matches_champion, search_tips, validate_source, video_link)


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
        self.assertEqual(len(champions), 71)
        has_transcript = (Path(__file__).resolve().parents[1] / 'data/transcript.ja.json').exists()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM transcript WHERE video_url=?', (VIDEO_URL,)).fetchone()[0], 12377 if has_transcript else 0)
        for champion in champions:
            tips = search_tips(self.conn, champion['id'])
            self.assertGreaterEqual(len(tips), 4)
            for tip in tips:
                validate_source(tip['source_sec'], champion)
                self.assertEqual(tip['status'], '未確認')
                evidence = self.conn.execute('SELECT 1 FROM transcript WHERE video_url=? AND ABS(start_sec-?)<6 LIMIT 1', (champion['video_url'],tip['source_sec'])).fetchone()
                if champion['video_url'] == VIDEO_URL and has_transcript:
                    self.assertIsNotNone(evidence)

    def test_initialization_preserves_edits_and_deletions(self):
        install_dataset(self.conn)
        self.conn.execute("UPDATE tips SET detail='自分の修正',status='確認済み' WHERE id=1")
        self.conn.execute('DELETE FROM tips WHERE id=2')
        self.conn.commit()
        install_dataset(self.conn)
        self.assertEqual(self.conn.execute('SELECT detail FROM tips WHERE id=1').fetchone()[0], '自分の修正')
        self.assertIsNone(self.conn.execute('SELECT id FROM tips WHERE id=2').fetchone())

    def test_all_checklists_are_installed(self):
        install_dataset(self.conn)
        champions = self.conn.execute('SELECT * FROM champions').fetchall()
        self.assertEqual(sum(len(json.loads(c['checklist_json'])) for c in champions), 355)
        self.assertEqual(sum(len(json.loads(c['supplements_json'])) for c in champions), 58)
        for champion in champions:
            self.assertEqual(len(json.loads(champion['checklist_json'])), 5)
            for item in json.loads(champion['supplements_json']):
                validate_source(item['source_sec'], champion)

    def test_guides_upgrade_preserves_existing_tips(self):
        # Simulate an installed v1 DB before the guide migration existed.
        self.conn.execute("INSERT INTO champions(name,start_sec,end_sec) VALUES('アーゴット',0,944)")
        self.conn.execute("INSERT INTO tips(champion_id,category,detail,status) VALUES(1,'基本対策','手動で修正したノート','未確認')")
        self.conn.execute("INSERT INTO app_meta VALUES('bundled_dataset_v1','1')")
        self.conn.commit()
        install_dataset(self.conn)
        install_dataset(self.conn)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tips WHERE champion_id=1').fetchone()[0], 1)
        self.assertEqual(self.conn.execute('SELECT detail FROM tips WHERE champion_id=1').fetchone()[0], '手動で修正したノート')
        self.assertEqual(len(json.loads(self.conn.execute('SELECT checklist_json FROM champions').fetchone()[0])), 5)

    def test_malformed_checklist_is_rejected_atomically(self):
        self.backup['champions'][0]['checklist'] = ['一つだけ']
        with self.assertRaises(ValueError):
            restore_backup(self.conn, self.backup)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM champions').fetchone()[0], 0)

    def test_guides_restore_with_backup(self):
        champion = self.backup['champions'][0]
        champion['checklist'] = [f'項目{i}' for i in range(5)]
        champion['supplements'] = [{'detail': '追加の対策', 'source_sec': 65}]
        restore_backup(self.conn, self.backup)
        row = self.conn.execute('SELECT * FROM champions').fetchone()
        self.assertEqual(json.loads(row['checklist_json']), champion['checklist'])
        self.assertEqual(json.loads(row['supplements_json']), champion['supplements'])

    def test_additional_sources_and_english_search(self):
        install_dataset(self.conn)
        for query, name in [('Gragas', 'グラガス'), ('TF', 'ツイステッド・フェイト'),
                            ('Heimerdinger', 'ハイマー'), ('Zaahen', 'ザーヘン')]:
            self.assertTrue(matches_champion(query, name))
            row = self.conn.execute('SELECT * FROM champions WHERE name=?', (name,)).fetchone()
            self.assertNotEqual(row['video_url'], VIDEO_URL)
            self.assertEqual(row['start_sec'], 0)
            self.assertTrue(video_link(30, row['video_url']).startswith(row['video_url']))

    def test_transcripts_keep_video_identity(self):
        second_url = 'https://www.youtube.com/watch?v=oY68nJ8BMrs'
        for url in [VIDEO_URL, second_url]:
            self.conn.execute('INSERT INTO transcript(start_sec,end_sec,content,video_url) VALUES(1,2,?,?)', ('同じ字幕', url))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM transcript').fetchone()[0], 2)

    def test_expansion_preserves_original_edits_and_deletions(self):
        data = json.loads((Path(__file__).resolve().parents[1] / 'data/counters.json').read_text(encoding='utf-8'))
        original = {'video_url': VIDEO_URL, 'champions': data['champions'][:50]}
        restore_backup(self.conn, original)
        self.conn.execute("UPDATE tips SET detail='編集済み',status='確認済み' WHERE id=1")
        self.conn.execute('DELETE FROM tips WHERE id=2')
        self.conn.executemany('INSERT INTO app_meta VALUES(?,?)', [('bundled_dataset_v1','1'), ('bundled_guides_v2','1')])
        self.conn.commit()
        install_dataset(self.conn)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM champions').fetchone()[0], 71)
        self.assertEqual(self.conn.execute('SELECT detail FROM tips WHERE id=1').fetchone()[0], '編集済み')
        self.assertIsNone(self.conn.execute('SELECT id FROM tips WHERE id=2').fetchone())
        count = self.conn.execute('SELECT COUNT(*) FROM tips').fetchone()[0]
        install_dataset(self.conn)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tips').fetchone()[0], count)

    def test_wrong_video_cannot_merge_into_existing_champion(self):
        restore_backup(self.conn, self.backup)
        self.backup['champions'][0]['video_url'] = 'https://www.youtube.com/watch?v=oY68nJ8BMrs'
        with self.assertRaises(ValueError):
            restore_backup(self.conn, self.backup)


if __name__ == '__main__':
    unittest.main()
