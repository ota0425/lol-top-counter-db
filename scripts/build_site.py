"""Build the GitHub Pages search site from the maintained counter dataset."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db import CHAMPION_ALIASES, connect, search_tips


def build(database=None):
    if database:
        conn = connect(database)
        champions = []
        try:
            for row in conn.execute('SELECT * FROM champions ORDER BY start_sec'):
                champions.append({'name': row['name'], 'checklist': json.loads(row['checklist_json']),
                                  'supplements': json.loads(row['supplements_json']),
                                  'tips': [dict(t) for t in search_tips(conn, row['id'])]})
        finally:
            conn.close()
    else:
        champions = json.loads((ROOT / 'data/counters.json').read_text(encoding='utf-8'))['champions']
    public = []
    for champ in champions:
        tips = [{'category': t['category'], 'detail': t['detail']} for t in champ['tips']
                if t.get('status') == '確認済み' or t.get('origin') == 'subtitle_summary']
        checklist = champ.get('checklist', [])
        if len(checklist) != 5:
            raise ValueError(f"{champ['name']}: チェックリストが5項目揃っていません")
        public.append({'name': champ['name'], 'aliases': CHAMPION_ALIASES.get(champ['name'], []),
                       'checklist': checklist,
                       'supplements': [s['detail'] for s in champ.get('supplements', [])], 'tips': tips})
    payload = json.dumps(public, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (ROOT / 'scripts/site_template.html').read_text(encoding='utf-8')
    (ROOT / 'docs/index.html').write_text(template.replace('__COUNTER_DATA__', payload), encoding='utf-8')
    (ROOT / 'docs/.nojekyll').touch()
    print(f"Built {len(public)} champions, {sum(len(c['checklist']) for c in public)} checklist items, "
          f"{sum(len(c['supplements']) for c in public)} additions, {sum(len(c['tips']) for c in public)} detailed notes")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, help='Publish current visible tips from a local database')
    args = parser.parse_args()
    build(args.database)
