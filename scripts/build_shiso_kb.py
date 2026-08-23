#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宍粟市公式サイトを網羅的に集めて、AIが答えるための資料を作る。
出力: shiso_kb.json

なぜ作るか（2026-08-21）：
  AIは宍粟市の手続き・窓口・料金を知らない。知らないまま答えさせると作り話になる。
  市のページには**必ず担当課と直通電話**が載っているので、それごと集めておけば
  「介護保険の申請は」に対して正確な課名と番号を答えられる。
  Googleの検索連携は無料枠で使えなかったため、自前で持つ形にした。

v2で直したこと（2026-08-22。「制度について細かく答えられるようにしろ」指示）：
  ・本文の700字打ち切りを廃止 → 全文を保存する。
    切っていたせいで、制度の説明・申請の持ち物・料金がデータに残っていなかった
  ・表(<table>)を構造のまま保存する（学校一覧・料金表・ごみの地区表はみんな表）
  ・添付(PDF等)への繋がりを保存する（ごみカレンダー・申請書・しおりはみんなPDF）
  ・入口をサイト全体に広げた（市政・観光・事業者。従来は暮らしの周辺だけ）
  ・課が無くても、表か添付を持つページは残す（一覧ページに実データがある）

行儀よく集めること：
  ・1ページごとに間をあける（市のサーバーに負担をかけない）
  ・名乗る（User-Agent）
  ・議事録・入札など、量が多く案内に使わないものは拾わない
"""
import json, re, time, sys, html, urllib.request, urllib.parse, pathlib
from collections import deque

元 = "https://www.city.shiso.lg.jp"
# ★HTTPヘッダーは英数字しか送れない（日本語を入れると latin-1 のエラーで全滅する）
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app; contact via site)"
出力 = pathlib.Path(__file__).resolve().parent.parent / "shiso_kb.json"

# 集める入口。トップから全部辿るのが基本。個別の入口は「トップから深くて
# 辿り着きにくい所」を確実に拾うための保険
入口 = [
    "/",
    "/kurashi/index.html",
    "/kosodadekyoiku/index.html",
    "/kenkofukushi/index.html",
    "/bosai/index.html",
    "/shisei/index.html",
    "/kanko/index.html",
    "/jigyosha/index.html",
    "/soshiki/index.html",
    "/kurashi/fukushi/index.html",
    "/kurashi/kaigo/index.html",
    "/kurashi/kenkoiryo/index.html",
    "/kurashi/nenkinhoken/index.html",
    "/kurashi/zeikin/index.html",
    "/kurashi/gomishinyokankyo/index.html",
    "/kurashi/kosekijumintoroku/index.html",
]

# 辿らないもの（量が多い・案内に使わない）。
# ※.pdf は「辿らない」だけで、ページからの繋がり（添付）としては保存する
除外 = re.compile(
    r"(\.pdf|\.doc|\.xls|\.zip|\.jpg|\.png|/gikai/|/nyusatsu/|/kouhou/|"
    r"/photo|/movie|/koho|/shingikai|/pubcome|/jinji/|/kekka|/nyusatu)", re.I)

集め上限 = int(sys.argv[1]) if len(sys.argv) > 1 else 3000  # 残すページ数の上限
見上限 = 集め上限 * 3                                        # 訪ねるページ数の上限（暴走止め）
間 = 0.4                                                     # 1ページごとの待ち（秒）
本文上限 = 20000                                             # 1ページの本文の上限（異常に長い頁の保険）


# ★手元のMacのPythonは証明書の一覧を持っておらずSSLで落ちる（2026-08-21）。
#   certifi があればそれを使う。GitHub Actions(Linux)では素で通るので影響しない。
def _ssl文脈():
    try:
        import ssl, certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            import ssl
            return ssl.create_default_context()
        except Exception:
            return None

_文脈 = _ssl文脈()


def 取る(url):
    req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
    with urllib.request.urlopen(req, timeout=20, context=_文脈) as r:
        b = r.read()
    for enc in ("utf-8", "cp932", "euc-jp"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", "ignore")


def 文字だけ(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def 問い合わせ先(生html):
    """『この記事に関するお問い合わせ先』の塊から、課名・電話・住所を取り出す"""
    i = 生html.find("お問い合わせ先")
    if i < 0:
        return {}
    塊 = 文字だけ(生html[i:i + 1500])
    課 = re.search(r"((?:[^\s]{0,8}部\s*)?[^\s]{2,14}(?:課|室|センター|事務所|支所))", 塊)
    電話 = re.findall(r"0790[-−－]?\d{2,3}[-−－]?\d{3,4}", 塊)
    住所 = re.search(r"(宍粟市[^\s]{4,40})", 塊)
    r = {}
    if 課:   r["課"] = 課.group(1).strip()
    if 電話: r["電話"] = list(dict.fromkeys(電話))[:2]
    if 住所: r["住所"] = 住所.group(1)
    return r


def 本文(生html):
    """記事の中身。v2: 打ち切らない（700字で切ると制度の中身が消える）"""
    t = 文字だけ(生html)
    # 共通のヘッダ・メニューを落とす（本文は「現在の位置」より後ろに来る）
    for 目印 in ["現在の位置", "ホーム >", "トップページ"]:
        j = t.find(目印)
        if j > 0:
            t = t[j + len(目印):]
            break
    j = t.find("この記事に関するお問い合わせ先")
    if j > 0:
        t = t[:j]
    t = re.sub(r"(PC版を表示|スマートフォン版を表示|メニュー|検索|文字サイズ|背景色|"
               r"発酵のふるさと宍粟|Tweet|新着情報 NEW!|現在、新着情報はございません。)", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:本文上限]


def 表を取る(生html):
    """<table> を行×マスの構造のまま取り出す。
       学校一覧・料金表・ごみの収集地区は全部これに入っている"""
    表たち = []
    for tb in re.findall(r"(?is)<table[^>]*>.*?</table>", 生html)[:30]:
        行たち = []
        for tr in re.findall(r"(?is)<tr[^>]*>.*?</tr>", tb)[:80]:
            マス = [文字だけ(c)[:200]
                    for c in re.findall(r"(?is)<t[hd][^>]*>.*?</t[hd]>", tr)]
            if any(マス):
                行たち.append(マス)
        # 1行だけの表はレイアウト用の枠。データではないので拾わない
        if len(行たち) >= 2:
            表たち.append(行たち)
    return 表たち


def 添付を取る(生html, 基url):
    """ページから繋がるPDF等（カレンダー・申請書・しおり）。名前と場所を保存"""
    out, 済 = [], set()
    for m in re.finditer(r'(?is)<a[^>]+href=["\']([^"\']+\.(?:pdf|xlsx?|docx?))["\'][^>]*>(.*?)</a>',
                         生html):
        u = urllib.parse.urljoin(基url, m.group(1)).split("#")[0]
        if u in 済:
            continue
        済.add(u)
        名 = 文字だけ(m.group(2))[:80]
        out.append({"名": 名 or u.rsplit("/", 1)[-1], "url": u})
        if len(out) >= 40:
            break
    return out


def 更新日を取る(生html):
    m = re.search(r"更新日[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", 生html)
    if not m:
        return ""
    return "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def 走る():
    見た, 待ち, 集めた = set(), deque(), []
    for p in 入口:
        待ち.append(元 + p)
    始め = time.time()
    while 待ち and len(集めた) < 集め上限 and len(見た) < 見上限:
        u = 待ち.popleft()
        u = u.split("#")[0]
        if u in 見た or 除外.search(u):
            continue
        見た.add(u)
        try:
            h = 取る(u)
        except Exception as e:
            print(f"  読めない {u} {e}", file=sys.stderr)
            continue
        time.sleep(間)

        題 = re.search(r"<title>([^<]+)</title>", h)
        題 = html.unescape(題.group(1)).replace("／宍粟市", "").strip() if 題 else ""
        本 = 本文(h)
        先 = 問い合わせ先(h)
        表 = 表を取る(h)
        添 = 添付を取る(h, u)
        日 = 更新日を取る(h)
        # 残す基準（v2）：
        #  ・担当課が載っている記事は全部（行政案内の本体）
        #  ・課が無くても、表か添付を持つページは残す（一覧に実データがある）
        #  ・どちらも無いページは案内でなくメニューなので残さない
        if 題 and ((len(本) >= 60 and 先.get("課")) or 表 or 添):
            o = {"題": 題, "url": u, "文": 本, **先}
            if 表: o["表"] = 表
            if 添: o["添付"] = 添
            if 日: o["日"] = 日
            集めた.append(o)
            if len(集めた) % 50 == 0:
                print(f"  {len(集めた)}件 … {題[:24]}", file=sys.stderr)

        # 同じサイトの .html だけ辿る
        for m in re.findall(r'href=["\']([^"\']+)["\']', h):
            v = urllib.parse.urljoin(u, m).split("#")[0]
            if not v.startswith(元):
                continue
            if not (v.endswith(".html") or v.rstrip("/") == 元) or 除外.search(v) or v in 見た:
                continue
            待ち.append(v)

    return 集めた, len(見た), time.time() - 始め


if __name__ == "__main__":
    集めた, 見た数, 秒 = 走る()
    # 同じ記事が別の道から二重三重に入ることがある。題と課で1つにまとめる
    _見た = set(); _残す = []
    for _o in 集めた:
        _k = (_o.get("題", ""), _o.get("課", ""))
        if _k in _見た:
            continue
        _見た.add(_k); _残す.append(_o)
    集めた = _残す
    # 課ごとの電話帳も作っておく（「◯◯課の電話は」に即答できる）
    # ★鍵の選別（2026-08-23の点検で発覚：本文に出た外部機関の名前と市の課の
    #   番号が組になり、「動物愛護センター＝警察署の番号」等の誤案内をしていた。
    #   番号の正規表現が0790限定なので、市外の機関には市の番号しか組めない＝毒）
    電話帳 = {}
    for it in 集めた:
        if not (it.get("課") and it.get("電話")):
            continue
        k = it["課"]
        # 頭の飾り・切れ端を掃除（「わせ先】」「〇」「◯◯詳しくは、」等）
        k = re.sub(r"^(〇|○|◯|お?問い?合わせ先|わせ先)】?", "", k)
        k = re.sub(r"^.{0,8}詳しくは、?", "", k)
        # 「事務局（地域創生課」のような入れ子は、括弧の中の課名を採る
        m = re.search(r"[（(]([^（()）]{2,14}(?:課|室|センター|事務所|支所))$", k)
        if m: k = m.group(1)
        k = k.strip()
        # 市の外の機関（県・労働局・消防・警察・動物愛護・農林振興）には
        # 0790の市の番号しか付かないので、電話帳に載せない
        if re.search(r"兵庫県|労働局|消防本部|警察|愛護センター|農林振興事務所", k):
            continue
        # まだ括弧や切れ端が残る鍵は捨てる（正しい対応の保証が無い）。
        # ★ひらがな始まり＝壊れ、としてはいけない（まちづくり部・こども未来課・
        #   はがてらす図書室は本物。2026-08-23の自分の検査ミスから）
        if re.search(r"[（()）【】]", k) or len(k) < 3:
            continue
        電話帳.setdefault(k, it["電話"][0])
    本文字数 = sorted(len(x.get("文", "")) for x in 集めた)
    出力.write_text(json.dumps({
        "版": "2",
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市公式サイト https://www.city.shiso.lg.jp/",
        "件数": len(集めた),
        "電話帳": 電話帳,
        "項目": 集めた,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    表数 = sum(1 for x in 集めた if x.get("表"))
    添数 = sum(1 for x in 集めた if x.get("添付"))
    print(f"{len(集めた)}件を残した（訪ねた{見た数}頁・{秒:.0f}秒）／課の電話帳 {len(電話帳)}件")
    print(f"表を持つ頁 {表数}件／添付を持つ頁 {添数}件")
    if 本文字数:
        print(f"本文の長さ: 最小{本文字数[0]} 中央{本文字数[len(本文字数)//2]} 最大{本文字数[-1]}")
    print(f"→ {出力}（{出力.stat().st_size//1024}KB）")
