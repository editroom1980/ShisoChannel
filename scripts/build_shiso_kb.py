#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宍粟市公式サイトから「暮らしの案内」を集めて、AIが答えるための資料を作る。
出力: shiso_kb.json

なぜ作るか（2026-08-21）：
  AIは宍粟市の手続き・窓口・料金を知らない。知らないまま答えさせると作り話になる。
  市のページには**必ず担当課と直通電話**が載っているので、それごと集めておけば
  「介護保険の申請は」に対して正確な課名と番号を答えられる。
  Googleの検索連携は無料枠で使えなかったため、自前で持つ形にした。

行儀よく集めること：
  ・1ページごとに間をあける（市のサーバーに負担をかけない）
  ・名乗る（User-Agent）
  ・議事録やPDFなど、量が多く案内に使わないものは拾わない
"""
import json, re, time, sys, html, urllib.request, urllib.parse, pathlib
from collections import deque

元 = "https://www.city.shiso.lg.jp"
# ★HTTPヘッダーは英数字しか送れない（日本語を入れると latin-1 のエラーで全滅する）
名乗り = "ShisochanNET-KB/1.0 (+https://shisochan.net/; citizen broadcast app; contact via site)"
出力 = pathlib.Path(__file__).resolve().parent.parent / "shiso_kb.json"

# 集める入口（暮らしに関わる案内が並んでいるところ）
入口 = [
    "/kurashi/index.html",
    "/kosodadekyoiku/index.html",
    "/kenkofukushi/index.html",
    "/bosai/index.html",
    # ★組織（課）から辿る入口。2026-08-21に「介護保険」の記事が1件も
    #   集まっていないことが分かったため追加した。暮らしの分類だけでは
    #   拾いきれない担当課のページがある
    "/soshiki/index.html",
    "/kurashi/fukushi/index.html",
    "/kurashi/kaigo/index.html",
    "/kurashi/kenkoiryo/index.html",
    "/kurashi/nenkinhoken/index.html",
    "/kurashi/zeikin/index.html",
    "/kurashi/gomishinyokankyo/index.html",
    "/kurashi/kosekijumintoroku/index.html",
]

# 拾わないもの（量が多い・案内に使わない）
除外 = re.compile(
    r"(\.pdf|\.doc|\.xls|\.zip|\.jpg|\.png|/gikai/|/nyusatsu/|/kouhou/|"
    r"/photo|/movie|/koho|/shingikai|/pubcome|/jinji/|/kekka|/nyusatu)", re.I)

上限 = int(sys.argv[1]) if len(sys.argv) > 1 else 700   # 集めるページ数の上限
間 = 0.4                                                 # 1ページごとの待ち（秒）


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
    """記事の中身。長すぎると資料が膨らむので頭のほうだけ"""
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
    return re.sub(r"\s+", " ", t).strip()[:700]


def 走る():
    見た, 待ち, 集めた = set(), deque(), []
    for p in 入口:
        待ち.append(元 + p)
    始め = time.time()
    while 待ち and len(集めた) < 上限:
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
        # ★担当課が載っているページだけ残す（2026-08-21）。
        #   一覧・メニューのページには問い合わせ先が無い＝案内の中身も無い。
        #   これで絞ると「行政の案内として使えるページ」だけが残る
        if 題 and len(本) >= 60 and 先.get("課"):
            集めた.append({"題": 題, "url": u, "文": 本, **先})
            if len(集めた) % 25 == 0:
                print(f"  {len(集めた)}件 … {題[:24]}", file=sys.stderr)

        # 同じサイトの .html だけ辿る
        for m in re.findall(r'href=["\']([^"\']+)["\']', h):
            v = urllib.parse.urljoin(u, m).split("#")[0]
            if not v.startswith(元):
                continue
            if not v.endswith(".html") or 除外.search(v) or v in 見た:
                continue
            待ち.append(v)

    return 集めた, time.time() - 始め


if __name__ == "__main__":
    集めた, 秒 = 走る()
    # 同じ記事が別の道から二重三重に入ることがある。題と課で1つにまとめる
    _見た = set(); _残す = []
    for _o in 集めた:
        _k = (_o.get("題", ""), _o.get("課", ""))
        if _k in _見た:
            continue
        _見た.add(_k); _残す.append(_o)
    集めた = _残す
    # 課ごとの電話帳も作っておく（「◯◯課の電話は」に即答できる）
    電話帳 = {}
    for it in 集めた:
        if it.get("課") and it.get("電話"):
            電話帳.setdefault(it["課"], it["電話"][0])
    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市公式サイト https://www.city.shiso.lg.jp/",
        "件数": len(集めた),
        "電話帳": 電話帳,
        "項目": 集めた,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(集めた)}件を集めました（{秒:.0f}秒）／課の電話帳 {len(電話帳)}件")
    print(f"→ {出力}（{出力.stat().st_size//1024}KB）")
