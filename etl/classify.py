"""Indicator descriptors used by the gold and release layers: clean name, topic and
measure type.

measure_type
  index      composite indices and their clusters / ranks (SES, peripherality, ...)
  rate       shares, rates, averages, per-capita values: comparable across authorities
  count      absolute quantities (people, NIS, m3, settlements): grow with size
  attribute  identifiers and descriptive fields (codes, district, status, names)
The label decides first; then the data checks it: a measure called a rate whose values
track population almost perfectly across authorities (Spearman >= 0.85, e.g.
"מקבלי דמי אבטלה (ממוצע חודשי)") is reclassified as a count, and every
reclassification is recorded in measure_type_basis.
"""

import os
import re

import pandas as pd
import yaml

from .common import norm_label, strip_period

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')

_ATTRIBUTE = re.compile(r'סמל|שנת קבלת|שם ועדת|מעמד מוניציפלי|^כללי › מחוז$|^מחוז$')
_INDEX = re.compile(r'מדד חברתי|חברתי-כלכלי|חברתית-כלכלית|פריפריאל|קומפקטיות|טופוגרפי|ציון תקן|אשכול|דירוג|ערך מדד')
_EXPLICIT_RATE = re.compile(r'אחוז|%|שיעור|ל-1,000|ל-100,000|לאלף|לנפש|לקמ"ר|למ"ר|לתלמיד|לכיתה|יחס')
_RATE = re.compile(_EXPLICIT_RATE.pattern + r'|ממוצע|ממוצעים|חציון|צפיפות|תוחלת|גיל |ציון|שכר|מרחק|'
                   r'פריון|ג\'יני|סטיית|הכנסה ממוצעת|טמפ|גובה|במעלות|ק"ג ליום')


def clean_name(label):
    """Latest label without period tokens and footnote digits, levels joined by ' › '."""
    parts = [norm_label(strip_period(p)) for p in str(label).split(' › ')]
    return ' › '.join(p for p in parts if p)


def load_topics():
    with open(os.path.join(CONFIG, 'topics.yaml'), encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    rules = [(t['key'], t['name'], set(t.get('domains') or []), re.compile(t['regex'])) for t in cfg['topics']]
    return rules, cfg.get('strip_prefixes') or []


def topic_of(name, domain, rules, strip):
    text = name
    for p in strip:
        if text.startswith(p):
            text = text[len(p):]
    for key, _, domains, rx in rules:
        if domains and domain not in domains:
            continue
        if rx.search(text):
            return key
    return 'other'


def label_measure_type(name, value_kind):
    if value_kind == 'text' or _ATTRIBUTE.search(name):
        return 'attribute'
    leaf = name.split(' › ')[-1]
    if _INDEX.search(name) and not _EXPLICIT_RATE.search(leaf):
        return 'index'
    return 'rate' if _RATE.search(name) else 'count'


def classify(catalog, facts, pop_id):
    """Add name, topic, topic_name, measure_type, measure_type_basis to the catalog."""
    rules, strip = load_topics()
    names = dict((k, n) for k, n, _, _ in rules)
    cat = catalog.copy()
    cat['name'] = cat['label_latest'].map(clean_name)
    cat['topic'] = [topic_of(n, d, rules, strip) for n, d in zip(cat['name'], cat['domain'])]
    cat['topic_name'] = cat['topic'].map(names).fillna('אחר')
    cat['measure_type'] = [label_measure_type(n, k) for n, k in zip(cat['name'], cat['value_kind'])]
    cat['measure_type_basis'] = 'label'

    # data check: how closely each indicator tracks population, in its latest year
    a = facts[(facts['row_type'] == 'authority') & facts['is_primary'] & facts['value'].notna()]
    pop = a[a['indicator_id'] == pop_id].set_index(['muni_code', 'period_year'])['value']
    rho = {}
    for iid, g in a[a['indicator_id'] != pop_id].groupby('indicator_id'):
        y = g['period_year'].max()
        s = g[g['period_year'] == y].set_index(['muni_code', 'period_year'])['value']
        j = pd.concat([s, pop], axis=1, keys=['v', 'p']).dropna()
        if len(j) >= 30 and j['v'].nunique() > 5:
            r = j.rank()
            rho[iid] = float(r['v'].corr(r['p']))
    cat['rho_with_population'] = cat['indicator_id'].map(rho).round(3)
    to_count = (cat['measure_type'] == 'rate') & (cat['rho_with_population'] >= 0.85) \
        & ~cat['name'].map(lambda n: bool(_EXPLICIT_RATE.search(n)))
    cat.loc[to_count, 'measure_type'] = 'count'
    cat.loc[to_count, 'measure_type_basis'] = 'data: tracks population (rho>=0.85) although the label reads as a rate'
    cat.loc[cat['indicator_id'] == pop_id, 'measure_type'] = 'count'
    return cat
