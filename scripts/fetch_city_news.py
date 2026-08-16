#!/usr/bin/env python3
# 宍粟市の「お知らせ・イベント」を集めて city_news.json を作る。
# GitHub Actions (.github/workflows/city-news.yml) が30分ごとに実行し、変化があればコミットする。
#
# 出典（2026-08-16 ユーザー承認。市内で行われる催しを多めに、行政の募集は少なめに）:
#   1. 宍粟市公式サイト 新着JSON      https://www.city.shiso.lg.jp/index.update.json
#   2. 宍粟市公式サイト カレンダー    https://www.city.shiso.lg.jp/calendar.json（開催日と会場つき）
#   3. 山崎文化会館                   http://www.yamabun.org/（投稿の日付＝開催日）
#   4. しそう森林王国観光協会         https://shiso.or.jp/ の「宍粟市のイベント情報！！」
#                                     ＝毎月の「宍粟市観光イベント情報」の表（祭り・花火・味覚）
#   5. 市内の小中学校（edumap）       各校の「主な年間行事」。誰でも見に行ける行事だけ
#
# 並び順は「開催日が近い催し」を最優先。次に市のくらし・重要、募集は最大2件まで。
import json
import os
import re
import unicodedata
import urllib.request
from datetime import datetime, timezone, timedelta

CITY = 'https://www.city.shiso.lg.jp'
HALL = 'http://www.yamabun.org'
KANKO = ('https://shiso.or.jp/recommended_spots/'
         '%E5%AE%8D%E7%B2%9F%E5%B8%82%E3%81%AE%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88%E6%83%85%E5%A0%B1%EF%BC%81%EF%BC%81-2')
HEADERS = {'User-Agent': 'ShisoChanNET-newsbot/1.0 (+https://shisochan.net)'}
JST = timezone(timedelta(hours=9))
MAX_ITEMS = 12
MAX_BOSHU = 2          # 行政の募集はここまで（多すぎると催しが埋もれる）

# 市の新着から拾う区分
SECTIONS = {'/kurashi/': 'くらし', '/event/': 'イベント',
            '/boshujoho/': '募集', '/important/': '重要'}
EXCLUDE_KEYWORDS = ['指定管理者']      # 事業者向けの調達は市民向けでないので出さない

# 市内の小中学校（2026-08-16 に実在を確認した14校）
SCHOOLS = ['yamasaki-es', 'yamasakinishi-es', 'yamasakiminami-es', 'harimaichinomiya-es',
           'ichinomiyakita-es', 'haga-es', 'chikusa-es',
           'yamasakinishi-jhs', 'yamasakiminami-jhs', 'yamasakihigashi-jhs',
           'ichinomiyakita-jhs', 'ichinomiyaminami-jhs', 'haga-jhs', 'chikusa-jhs']
# 学校の行事のうち、外の人が見に行ける・地域の話題になるものだけ
SCHOOL_OK = ['運動会', '体育大会', '体育祭', '文化祭', '学習発表会', '発表会',
             '音楽会', '合唱', '大会', 'オープンスクール']
SCHOOL_NG = ['テスト', '面談', '懇談', '家庭訪問', '健康診断', '身体測定', '集金',
             '引き渡し', '避難訓練', '始業式', '終業式', '入学式', '卒業式', '修了式',
             '参観', '進路説明', '内科検診', '歯科検診']
# 会館の催しのうち、内輪の会合は出さない（誰でも行けるものだけ）
HALL_NG = ['総会', '講習', '研修', '部会', '協議会', '連絡会', '会議', '説明会']


def 取る(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')


def 取るJSON(url):
    return json.loads(取る(url))


def 平文(s):
    """HTMLのタグを外して、全角の数字や記号を半角に揃える"""
    s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = (s.replace('&nbsp;', ' ').replace('&amp;', '&')
          .replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"'))
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', s)).strip()


def 題を整える(題, 開催日):
    """題の中の日付は、前に付ける開催日と重なるので落とす（画面が読みやすくなる）"""
    題 = re.sub(r'^\s*\d{1,2}\s*[/月]\s*\d{1,2}日?\s*[:：]?\s*', '', 題)
    題 = re.sub(r'\s*\d{1,2}月\d{1,2}日\s*$', '', 題)
    題 = re.sub(r'\s+', ' ', 題).strip()
    return '%d/%d %s' % (開催日.month, 開催日.day, 題)


def 年度の年(月, 今日):
    """4月始まりの年度で、その月が何年になるかを決める"""
    年度 = 今日.year if 今日.month >= 4 else 今日.year - 1
    return 年度 if 月 >= 4 else 年度 + 1


# ── 1. 市の新着 ────────────────────────────────────────────────
def 市の新着():
    出 = []
    for it in 取るJSON(CITY + '/index.update.json'):
        url = it.get('url', '')
        区分 = next((v for k, v in SECTIONS.items() if k in url), None)
        if not 区分:
            continue
        if any(k in it['page_name'] for k in EXCLUDE_KEYWORDS):
            continue
        出.append({'tag': 区分, 'title': it['page_name'], 'url': url, 'src': '宍粟市公式サイト',
                   'ts': it['publish_datetime'], 'when': None, 'no': it['page_no']})
    return 出


# ── 2. 市のカレンダー（開催日と会場つき）──────────────────────
def 市のカレンダー(今日):
    出 = []
    for it in 取るJSON(CITY + '/calendar.json'):
        次 = None
        for 期間 in it.get('date_list') or []:
            try:
                d = datetime.strptime(期間[0], '%Y-%m-%d').date()
            except Exception:
                continue
            if d >= 今日 and (次 is None or d < 次):
                次 = d
        if not 次:
            continue
        場所 = (it.get('event') or {}).get('event_place') or ''
        出.append({'tag': 'イベント', 'title': it['page_name'], 'url': it['url'],
                   'ts': None, 'when': 次.isoformat(), 'place': 場所, 'src': '宍粟市公式サイト',
                   'no': 'cal%s' % it['page_no']})
    return 出


# ── 3. 山崎文化会館（投稿の日付＝開催日）──────────────────────
def 文化会館(今日):
    出 = []
    投稿 = 取るJSON(HALL + '/wp-json/wp/v2/posts?per_page=30&_fields=id,date,title,link')
    for p in 投稿:
        題 = 平文(p['title']['rendered'])
        if '(終了)' in 題 or '（終了）' in 題:
            continue
        if any(k in 題 for k in HALL_NG):
            continue
        try:
            d = datetime.fromisoformat(p['date']).date()
        except Exception:
            continue
        if d < 今日:
            continue
        出.append({'tag': '催し', 'title': 題, 'url': p['link'],
                   'ts': None, 'when': d.isoformat(), 'place': '山崎文化会館',
                   'src': '山崎文化会館',
                   'no': 'hall%s' % p['id']})
    return 出


# ── 4. 観光協会の月ごとのイベント表（祭り・花火・味覚）────────
def 観光協会(今日):
    """「宍粟市のイベント情報！！」の表から 行事名・日時・場所 を取り出す"""
    html = 取る(KANKO)
    出 = []
    for 行 in re.findall(r'(?is)<tr[^>]*>(.*?)</tr>', html):
        欄 = [平文(c) for c in re.findall(r'(?is)<t[dh][^>]*>(.*?)</t[dh]>', 行)]
        if len(欄) < 3 or 欄[0] in ('行事等名称', ''):
            continue
        名, 日時, 場所 = 欄[0], 欄[1], 欄[2]
        m = re.search(r'(\d{1,2})月\s*(\d{1,2})日', 日時)
        if not m:
            continue                      # 「7月中旬～」のように日が決まらないものは出さない
        月, 日 = int(m.group(1)), int(m.group(2))
        try:
            d = datetime(年度の年(月, 今日), 月, 日).date()
        except ValueError:
            continue
        if d < 今日:
            continue
        名 = re.sub(r'^【[^】]*】\s*', '', 名)          # 先頭の【波賀】などは外す
        出.append({'tag': 'イベント', 'title': 名, 'url': KANKO, 'src': 'しそう森林王国観光協会',
                   'ts': None, 'when': d.isoformat(),
                   'place': 場所.split('(')[0].strip(), 'no': 'k%s%s' % (月, 日) + 名[:6]})
    return 出


# ── 5. 市内の小中学校の年間行事 ────────────────────────────────
def 学校の控え(path=None):
    return path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'school_events.json')


def 学校(今日):
    """年間行事は年に数回しか変わらないので、12時間に1回だけ取りに行き、
    ふだんは控え(school_events.json)を使う。30分ごとに14校を叩かないための配慮"""
    控え = 学校の控え()
    try:
        前 = json.load(open(控え, encoding='utf-8'))
        経過 = datetime.now(JST) - datetime.fromisoformat(前['updated'])
        if 経過 < timedelta(hours=12):
            return [x for x in 前['items'] if x['when'] >= 今日.isoformat()]
    except Exception:
        pass
    出 = 学校を取りに行く(今日)
    try:
        with open(控え, 'w', encoding='utf-8') as f:
            json.dump({'updated': datetime.now(JST).isoformat(timespec='seconds'),
                       'items': 出}, f, ensure_ascii=False, indent=1)
            f.write('\n')
    except Exception as e:
        print('  ! 学校の控えを書けず: %s' % e)
    return 出


def 学校を取りに行く(今日):
    出 = []
    for 校 in SCHOOLS:
        基 = 'https://city-shiso-%s.edumap.jp' % 校
        try:
            html = 取る(基 + '/event', timeout=15)
        except Exception:
            continue
        m = re.search(r'<title>([^<]*)', html)
        校名 = re.sub(r'^[^宍]*', '', (m.group(1) if m else '')).split(' - ')[0].strip()
        校名 = 校名.replace('宍粟市立', '').replace('　', '').strip() or 校
        本文 = 平文(html)
        # 書き方は学校ごとに違う。「行事名(5/23)」と「4/18(土)行事名」の両方を拾う
        候補 = [(m.group(2), m.group(3), m.group(1)) for m in
                re.finditer(r'([^|・\s][^|・]{1,22}?)\s*[(（](\d{1,2})[/／](\d{1,2})[)）]', 本文)]
        候補 += [(m.group(1), m.group(2), m.group(4)) for m in
                 re.finditer(r'(\d{1,2})\s*[/／]\s*(\d{1,2})\s*[(（][日月火水木金土][)）]\s*([~〜～\d\s(（）)日月火水木金土/／]*)([^|\d]{2,24})', 本文)]
        for 月, 日, 名 in 候補:
            名 = re.sub(r'[(（][^)）]*$', '', 名)        # 閉じていない括弧の切れ端を落とす
            名 = 名.strip(' 、・,()（）~〜～-')
            if not any(k in 名 for k in SCHOOL_OK):
                continue
            if any(k in 名 for k in SCHOOL_NG):
                continue
            try:
                d = datetime(年度の年(int(月), 今日), int(月), int(日)).date()
            except ValueError:
                continue
            if d < 今日:
                continue
            # 市や地区の大会は複数の学校が同じ予定を書くので、1件にまとめて校名を付けない
            共通 = 名.startswith(('宍粟市', '西播', '兵庫県', '県'))
            出.append({'tag': '学校', 'title': 名 if 共通 else '%s %s' % (校名, 名),
                       'url': 基 + '/event', 'src': 校名, 'ts': None, 'when': d.isoformat(),
                       'place': '' if 共通 else 校名,
                       'no': ('t%s%s%s' % (月, 日, 名) if 共通 else 's%s%s%s' % (校, 月, 日))})
    return 出


def main():
    今 = datetime.now(JST)
    今日 = 今.date()
    集め = {}

    題名 = set()

    def 足す(名, 関数, *引数):
        """1つの出典が落ちても、他の出典だけで作り続ける（取得もこの中で行う）"""
        try:
            取得 = 関数(*引数)
        except Exception as e:
            print('  ! %s は取得できず: %s' % (名, e))
            return
        for it in 取得:
            # 出典違い・書き方違いの同じ催しは1回だけ（学校ごとに
            # 「宍粟市中学校新人大会」「宍粟市新人大会」と書き方が割れるため揃える）
            鍵 = re.sub(r'[\s　]|中学校|中学|小学校|競走', '', it['title'])[:18]
            if 鍵 in 題名:
                continue
            題名.add(鍵)
            集め.setdefault(it['no'], it)

    # 開催日が分かる出典を先に。市の新着は日付が無いので最後（同じ催しなら日付つきを残す）
    足す('観光協会', 観光協会, 今日)
    足す('山崎文化会館', 文化会館, 今日)
    足す('市のカレンダー', 市のカレンダー, 今日)
    足す('学校', 学校, 今日)
    足す('市の新着', 市の新着)

    催し = [x for x in 集め.values() if x.get('when')]
    催し.sort(key=lambda x: x['when'])                       # 開催が近い順
    その他 = [x for x in 集め.values() if not x.get('when')]
    その他.sort(key=lambda x: x['ts'] or '', reverse=True)    # 新しい順
    くらし = [x for x in その他 if x['tag'] in ('くらし', '重要', 'イベント')]
    募集 = [x for x in その他 if x['tag'] == '募集'][:MAX_BOSHU]

    並び = (催し + くらし + 募集)[:MAX_ITEMS]

    出 = []
    for it in 並び:
        if it.get('when'):
            d = datetime.fromisoformat(it['when'])
            表示 = '%d月%d日' % (d.month, d.day)
            ts = it['when'] + 'T00:00:00+09:00'
            題 = 題を整える(it['title'], d)      # 「8/30 桂吉弥独演会」の形にする
        else:
            d = datetime.fromisoformat(it['ts'])
            表示 = '%d月%d日' % (d.month, d.day)
            ts = it['ts']
            題 = it['title']
        欄 = {'tag': it['tag'], 'title': 題, 'url': it['url'],
              'date': 表示, 'ts': ts, 'src': it.get('src', '宍粟市公式サイト')}
        if it.get('when'):
            欄['when'] = it['when']                 # 開催日（アプリで「開催」と出せる）
        if it.get('place'):
            欄['place'] = it['place']
        出.append(欄)

    data = {
        'updated': 今.isoformat(timespec='seconds'),
        'source': '宍粟市公式サイト／山崎文化会館／しそう森林王国観光協会／市内の小中学校',
        'items': 出,
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'city_news.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print('wrote %d items -> city_news.json （催し%d件）' % (len(出), len(催し)))


if __name__ == '__main__':
    main()
