#!/usr/bin/env python3
# 宍粟市公式サイトの新着JSONから「くらし・イベント・募集情報・重要」を選別して city_news.json を生成する。
# GitHub Actions (.github/workflows/city-news.yml) が30分ごとに実行し、変化があればコミットする。
# 取得元（市のトップページ自身が新着欄の描画に使っている公開JSON）:
#   https://www.city.shiso.lg.jp/index.update.json      … サイト全体の新着(約100件)
#   https://www.city.shiso.lg.jp/event/index.tree.json  … イベント一覧（開催前の掲載の補完用）
# 選別: URLパスが /kurashi/(くらし) /event/(イベント) /boshujoho/(募集) /important/(重要) のものだけ。
#   入札(jigyosha)・統計等の組織事務(soshiki)・フォトニュース(photo)・観光(kanko)は対象外（2026-08-09ユーザー指示）。
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta

BASE = 'https://www.city.shiso.lg.jp'
HEADERS = {'User-Agent': 'ShisoChanNET-newsbot/1.0 (+https://shisochan.net)'}
SECTIONS = {
    '/kurashi/':   'くらし',
    '/event/':     'イベント',
    '/boshujoho/': '募集',
    '/important/': '重要',
}
MAX_ITEMS = 12
# 市民向け情報に絞る（指定管理者公募は事業者向け調達のため除外）
EXCLUDE_KEYWORDS = ['指定管理者']
JST = timezone(timedelta(hours=9))


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def section_of(url):
    for path, tag in SECTIONS.items():
        if path in url:
            return tag
    return None


def main():
    items = {}

    for it in get_json(BASE + '/index.update.json'):
        tag = section_of(it.get('url', ''))
        if not tag:
            continue
        if any(k in it['page_name'] for k in EXCLUDE_KEYWORDS):
            continue
        items[it['page_no']] = {'tag': tag, 'title': it['page_name'],
                                'url': it['url'], 'dt': it['publish_datetime']}

    # イベント一覧で補完（新着100件から漏れた開催前イベントを拾う）
    try:
        for it in get_json(BASE + '/event/index.tree.json'):
            if it.get('is_category_index'):
                continue
            items.setdefault(it['page_no'], {'tag': 'イベント', 'title': it['page_name'],
                                             'url': it['url'], 'dt': it['publish_datetime']})
    except Exception:
        pass  # イベント一覧が読めなくても新着分だけで続行

    latest = sorted(items.values(), key=lambda x: x['dt'], reverse=True)[:MAX_ITEMS]

    out = []
    for it in latest:
        d = datetime.fromisoformat(it['dt'])
        out.append({'tag': it['tag'], 'title': it['title'], 'url': it['url'],
                    'date': f'{d.month}月{d.day}日', 'ts': it['dt']})

    data = {
        'updated': datetime.now(JST).isoformat(timespec='seconds'),
        'source': '宍粟市公式サイト',
        'items': out,
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'city_news.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(f'wrote {len(out)} items -> city_news.json')


if __name__ == '__main__':
    main()
