"""Cache the official Data Dragon assets used by the matchup notes."""
import concurrent.futures
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db import CHAMPION_ALIASES, search_key

VERSION = '15.17.1'  # Video publication period; keep icon appearance reproducible.
CDN = 'https://ddragon.leagueoflegends.com'
ASSETS = ROOT / 'docs/assets/icons'


def get_json(path, version=VERSION):
    with urllib.request.urlopen(f'{CDN}/cdn/{version}/data/ja_JP/{path}.json', timeout=30) as response:
        return json.load(response)


def sync():
    ASSETS.mkdir(parents=True, exist_ok=True)
    champions = json.loads((ROOT / 'data/counters.json').read_text(encoding='utf-8'))['champions']
    jobs = [('champion',), ('item',), ('summoner',), ('runesReforged',)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        champion_index, items, summoners, trees = list(pool.map(lambda job: get_json(job[0]), jobs))
    ids = {}
    versions = {}
    fallback_index = None
    fallback_version = None
    for champion in champions:
        aliases = [champion['name'], *CHAMPION_ALIASES.get(champion['name'], [])]
        found = [c for c in champion_index['data'].values() if any(search_key(alias) in [search_key(c['id']), search_key(c['name'])] for alias in aliases)]
        version = VERSION
        if not found:
            if fallback_index is None:
                with urllib.request.urlopen(f'{CDN}/api/versions.json', timeout=30) as response:
                    fallback_version = json.load(response)[0]
                fallback_index = get_json('champion', fallback_version)
            found = [c for c in fallback_index['data'].values() if any(search_key(alias) in [search_key(c['id']), search_key(c['name'])] for alias in aliases)]
            version = fallback_version
        if len(found) != 1:
            raise ValueError(f"Cannot resolve champion: {champion['name']}")
        ids[champion['name']] = found[0]['id']
        versions[champion['name']] = version
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        champion_details = dict(zip(ids, pool.map(lambda name: get_json('champion/' + ids[name], versions[name]), ids)))
    downloads = {}

    def asset(kind, filename, label, rune=False, version=VERSION):
        name = f"{kind}-{Path(filename).stem}.png"
        path = 'assets/icons/' + name
        url = f'{CDN}/cdn/img/{filename}' if rune else f'{CDN}/cdn/{version}/img/{kind}/{filename}'
        downloads[name] = url
        return {'src': path, 'label': label}

    catalog = {'version': VERSION, 'source': 'https://developer.riotgames.com/docs/lol#data-dragon', 'champions': {}, 'terms': {}}
    catalog['champion_versions'] = versions
    for name, detail in champion_details.items():
        info = detail['data'][ids[name]]
        skills = {key: asset('spell', spell['image']['full'], f"{key}：{spell['name']}", version=versions[name]) for key, spell in zip('QWER', info['spells'])}
        skills['ULT'] = skills['R']
        skills['パッシブ'] = asset('passive', info['passive']['image']['full'], f"パッシブ：{info['passive']['name']}", version=versions[name])
        catalog['champions'][name] = skills

    text = json.dumps(champions, ensure_ascii=False)
    for item_id, item in items['data'].items():
        name = re.sub(r'<[^>]+>', '', item['name']).replace(' ', '')
        # Prefer Summoner's Rift item IDs over arena variants.
        if len(item_id) > 4 or not name or name not in text:
            continue
        catalog['terms'][name] = asset('item', item['image']['full'], name)
    for spell in summoners['data'].values():
        name = spell['name'].replace(' ', '')
        if name in text:
            catalog['terms'][name] = asset('spell', spell['image']['full'], name)
    for tree in trees:
        for slot in tree['slots']:
            for rune in slot['runes']:
                name = rune['name'].replace(' ', '')
                if name in text:
                    catalog['terms'][name] = asset('rune', rune['icon'], name, rune=True)
    aliases = {'靴': 'ブーツ', 'サンファイア': 'サンファイアイージス', 'ビスケット': 'ビスケットデリバリー'}
    for alias, original in aliases.items():
        if alias in text and original not in catalog['terms']:
            info = next((i for i, item in items['data'].items() if len(i) <= 4 and item['name'].replace(' ', '') == original), None)
            if info:
                catalog['terms'][original] = asset('item', items['data'][info]['image']['full'], original)
        if original in catalog['terms']:
            catalog['terms'][alias] = catalog['terms'][original]
        elif alias == 'ビスケット':
            rune = next(r for tree in trees for slot in tree['slots'] for r in slot['runes'] if r['name'] == original)
            catalog['terms'][alias] = asset('rune', rune['icon'], alias, rune=True)
    for name, icon in [('攻撃速度シャード', 'StatModsAttackSpeedIcon'), ('魔法防御シャード', 'StatModsMagicResIcon')]:
        catalog['terms'][name] = asset('stat', f'perk-images/StatMods/{icon}.png', name, rune=True)

    def download(pair):
        name, url = pair
        target = ASSETS / name
        if target.exists():
            return
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError(f'Not a PNG asset: {name}')
        target.write_bytes(data)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(download, downloads.items()))
    (ROOT / 'data/icons.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Saved {len(downloads)} official icons for {len(ids)} champions and {len(catalog['terms'])} named terms (Data Dragon {VERSION})")


if __name__ == '__main__':
    sync()
