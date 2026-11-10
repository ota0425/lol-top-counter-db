"""Render trusted, locally cached game icons alongside escaped note text."""
import base64
import html
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def catalog():
    return json.loads((ROOT / 'data/icons.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=400)
def image_data(src):
    path = (ROOT / 'docs' / src).resolve()
    if not path.is_relative_to((ROOT / 'docs/assets/icons').resolve()):
        raise ValueError('Invalid icon path')
    return base64.b64encode(path.read_bytes()).decode('ascii')


def icon_markup(text, champion, include_skills=False):
    terms = dict(catalog()['terms'])
    if include_skills:
        skills = catalog()['champions'].get(champion, {})
        terms.update(skills)
        for key in 'QWER':
            if key in skills:
                for phase in '123':
                    terms[key + phase] = skills[key]
    pattern = re.compile('|'.join(re.escape(t) for t in sorted(terms, key=len, reverse=True)))
    result = []
    position = 0
    for match in pattern.finditer(text):
        name = match.group()
        result.append(html.escape(text[position:match.start()]))
        asset = terms[name]
        neighboring = (text[match.start()-1:match.start()] if match.start() else '') + text[match.end():match.end()+1]
        is_skill = bool(re.fullmatch(r'ULT|[QWER][123]?', name))
        if is_skill and re.search(r'[a-zA-Z]', neighboring):
            result.append(html.escape(name))
        else:
            result.append(f'<span title="{html.escape(asset["label"], quote=True)}"><img src="data:image/png;base64,{image_data(asset["src"])}" alt="" width="28" height="28" style="vertical-align:middle;object-fit:contain;border-radius:4px;margin:0 5px 2px 1px">{html.escape(name)}</span>')
        position = match.end()
    result.append(html.escape(text[position:]))
    return ''.join(result)
