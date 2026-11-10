import json
import re
import sqlite3
from pathlib import Path
import math
import unicodedata


DB = Path(__file__).with_name('counters.sqlite3')
VIDEO_ID = 'gmuF58MD3ts'
VIDEO_URL = f'https://www.youtube.com/watch?v={VIDEO_ID}'
CATEGORIES = ['基本対策', 'スキル対策', '序盤', 'トレード', 'アイテム', 'カウンターピック', '注意点', 'その他']


def connect(path=DB):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS champions (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, start_sec INTEGER NOT NULL DEFAULT 0,
      end_sec INTEGER, notes TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS tips (
      id INTEGER PRIMARY KEY, champion_id INTEGER NOT NULL REFERENCES champions(id) ON DELETE CASCADE,
      category TEXT NOT NULL, detail TEXT NOT NULL, source_sec INTEGER,
      status TEXT NOT NULL DEFAULT '未確認' CHECK(status IN ('未確認','確認済み')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS transcript (
      id INTEGER PRIMARY KEY, start_sec REAL NOT NULL, end_sec REAL NOT NULL, content TEXT NOT NULL,
      UNIQUE(start_sec,end_sec,content)
    );
    CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')
    # Add provenance without changing existing records or their review status.
    columns = {r['name'] for r in conn.execute('PRAGMA table_info(tips)')}
    if 'origin' not in columns:
        conn.execute("ALTER TABLE tips ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'")
        conn.commit()
    return conn


def seconds(value):
    value = value.strip().replace(',', '.')
    if not re.fullmatch(r'\d+(?::\d{1,2}){0,2}(?:\.\d+)?', value):
        raise ValueError(f'時刻の形式が不正です: {value}')
    parts = [float(p) for p in value.split(':')]
    if any(p >= 60 for p in parts[1:]):
        raise ValueError(f'時刻の形式が不正です: {value}')
    total = 0
    for part in parts:
        total = total * 60 + part
    if not math.isfinite(total):
        raise ValueError('時刻が大きすぎます')
    return int(total)


def search_key(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    value = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in value)
    return re.sub(r'[\s・･.\-ー＝=\u0027’]', '', value)


CHAMPION_ALIASES = {
    'アーゴット': ['Urgot'], 'アカリ': ['Akali'], 'アンベッサ': ['Ambessa'],
    'イラオイ': ['Illaoi'], 'ヴェイン': ['Vayne', 'ベイン'], 'ウディア': ['Udyr'],
    'エイトロックス': ['Aatrox', 'エイトロ'], 'オーン': ['Ornn'], 'オラフ': ['Olaf'],
    'カサンテ': ["K’Sante", 'Ksante', 'カ・サンテ'], 'カミール': ['Camille'],
    'ガレン': ['Garen'], 'ガングプランク': ['Gangplank', 'ガンプラ', 'GP'],
    'クイン': ['Quinn'], 'グウェン': ['Gwen'], 'クレッド': ['Kled'],
    'ケイル': ['Kayle'], 'ケネン': ['Kennen'], 'サイオン': ['Sion'],
    'ザック': ['Zac'], 'ジェイス': ['Jayce'], 'シェン': ['Shen'],
    'ジャックス': ['Jax'], 'シンジド': ['Singed'], 'スカーナー': ['Skarner'],
    'セト': ['Sett'], 'ダリウス': ['Darius'], 'チョガス': ["Cho’Gath", 'Chogath', 'チョ＝ガス'],
    'ティーモ': ['Teemo'], 'トランドル': ['Trundle'], 'トリンダメア': ['Tryndamere'],
    'ナー': ['Gnar'], 'ナサス': ['Nasus'], 'パンテオン': ['Pantheon'],
    'フィオラ': ['Fiora'], 'ブラッドミア': ['Vladimir', 'ブラッド', 'ブラミ'],
    'ポッピー': ['Poppy'], 'ボリベア': ['Volibear'], 'マルファイト': ['Malphite'],
    'ムンド': ['Dr. Mundo', 'Mundo', 'ドクター・ムンド'],
    'モルデカイザー': ['Mordekaiser', 'モルデ'], 'ヤスオ': ['Yasuo'],
    'ヨネ': ['Yone'], 'ヨリック': ['Yorick'], 'ランブル': ['Rumble'],
    'リヴェン': ['Riven', 'リベン'], 'リリア': ['Lillia'], 'レネクトン': ['Renekton'],
    'レンガー': ['Rengar'], 'ワーウィック': ['Warwick', 'ワーウィック'],
}


def matches_champion(keyword, name):
    key = search_key(keyword)
    return any(key in search_key(alias) for alias in [name, *CHAMPION_ALIASES.get(name, [])])


def search_tips(conn, champion_id, include_summaries=True):
    return conn.execute('''SELECT * FROM tips WHERE champion_id=? AND
        (status='確認済み' OR (? AND origin='subtitle_summary'))
        ORDER BY source_sec,id''', (champion_id, include_summaries)).fetchall()


def validate_source(sec, champion):
    if sec is None:
        raise ValueError('根拠の時刻を入力してください。')
    if sec < champion['start_sec'] or (champion['end_sec'] is not None and sec >= champion['end_sec']):
        raise ValueError('根拠の時刻はこのチャンピオンのチャプター内を指定してください。')


def timestamp(s):
    s = int(s)
    return f'{s//3600}:{s%3600//60:02d}:{s%60:02d}'


def video_link(s):
    return f'{VIDEO_URL}&t={int(s)}s'


def parse_captions(text):
    text = text.lstrip('\ufeff').replace('\r\n', '\n')
    blocks = re.split(r'\n\s*\n', text)
    rows = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        idx = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if idx is None:
            continue
        m = re.search(r'(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d+\s*-->\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d+', lines[idx])
        if not m:
            continue
        a, b = [x.strip() for x in m.group().split('-->')]
        content = ' '.join(re.sub(r'<[^>]*>', '', x) for x in lines[idx+1:]).strip()
        if content:
            rows.append((seconds(a), seconds(b), content))
    return rows


def import_chapters(conn, text):
    chapters = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$', line)
        if not m:
            raise ValueError(f'チャプター形式が不正です: {line}')
        chapters.append((seconds(m.group(1)), m.group(2).strip()))
    if len(set(n for _, n in chapters)) != len(chapters):
        raise ValueError('同じチャンピオン名が重複しています')
    if any(a[0] >= b[0] for a, b in zip(chapters, chapters[1:])):
        raise ValueError('チャプターは時刻順に並べてください')
    for i, (start, name) in enumerate(chapters):
        end = chapters[i+1][0] if i+1 < len(chapters) else None
        conn.execute('''INSERT INTO champions(name,start_sec,end_sec) VALUES(?,?,?)
        ON CONFLICT(name) DO UPDATE SET start_sec=excluded.start_sec,end_sec=excluded.end_sec''', (name, start, end))
    conn.commit()
    return len(chapters)




def restore_backup(conn, data):
    """Validate the full backup before applying an atomic, additive restore."""
    if not isinstance(data, dict) or data.get('video_url') != VIDEO_URL:
        raise ValueError('この動画のバックアップJSONを指定してください。')
    champions = data.get('champions')
    if not isinstance(champions, list) or not champions:
        raise ValueError('champions にチャンピオン一覧が必要です。')
    names = set()
    def valid_sec(value):
        return type(value) is int and value >= 0
    for champ in champions:
        if not isinstance(champ, dict):
            raise ValueError('チャンピオンの形式が不正です。')
        name = champ.get('name')
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('チャンピオン名が空または重複しています。')
        names.add(name)
        start, end = champ.get('start_sec'), champ.get('end_sec')
        if not valid_sec(start) or (end is not None and (not valid_sec(end) or end <= start)):
            raise ValueError('チャプターの時刻が不正です。')
        tips = champ.get('tips', [])
        if not isinstance(tips, list):
            raise ValueError('tips は配列で指定してください。')
        for tip in tips:
            if not isinstance(tip, dict) or tip.get('category') not in CATEGORIES:
                raise ValueError('対策の分類が不正です。')
            if not isinstance(tip.get('detail'), str) or not tip['detail'].strip():
                raise ValueError('対策内容が空です。')
            if tip.get('status') not in ['未確認', '確認済み']:
                raise ValueError('確認状況が不正です。')
            if tip.get('origin', 'manual') not in ['manual', 'subtitle_summary']:
                raise ValueError('対策の作成元が不正です。')
            sec = tip.get('source_sec')
            if sec is not None and not valid_sec(sec):
                raise ValueError('根拠の時刻が不正です。')
            if tip['status'] == '確認済み' or tip.get('origin') == 'subtitle_summary':
                validate_source(sec, champ)
    count = 0
    with conn:
        for champ in champions:
            # Keep existing chapter boundaries when merging a backup.
            conn.execute('INSERT OR IGNORE INTO champions(name,start_sec,end_sec) VALUES(?,?,?)',
                         (champ['name'], champ['start_sec'], champ.get('end_sec')))
            current = conn.execute('SELECT * FROM champions WHERE name=?', (champ['name'],)).fetchone()
            for tip in champ.get('tips', []):
                if tip['status'] == '確認済み' or tip.get('origin') == 'subtitle_summary':
                    validate_source(tip.get('source_sec'), current)
                values = (current['id'], tip['category'], tip['detail'], tip.get('source_sec'))
                exists = conn.execute('SELECT 1 FROM tips WHERE champion_id=? AND category=? AND detail=? AND source_sec IS ?', values).fetchone()
                if not exists:
                    conn.execute('INSERT INTO tips(champion_id,category,detail,source_sec,status,origin) VALUES(?,?,?,?,?,?)',
                                 (*values, tip['status'], tip.get('origin', 'manual')))
                    count += 1
    return count


def install_dataset(conn):
    """Install the bundled source dataset once; preserve later edits and deletions."""
    if conn.execute("SELECT 1 FROM app_meta WHERE key='bundled_dataset_v1'").fetchone():
        return
    data_dir = Path(__file__).with_name('data')
    backup = json.loads((data_dir / 'counters.json').read_text(encoding='utf-8'))
    transcript_file = data_dir / 'transcript.ja.json'
    transcript = json.loads(transcript_file.read_text(encoding='utf-8')) if transcript_file.exists() else []
    rows = [(r['start'], r['start'] + r['duration'], r['text']) for r in transcript]
    restore_backup(conn, backup)
    with conn:
        conn.executemany('INSERT OR IGNORE INTO transcript(start_sec,end_sec,content) VALUES(?,?,?)', rows)
        conn.execute("INSERT INTO app_meta(key,value) VALUES('bundled_dataset_v1','1')")
