#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宍粟市例規集（条例・規則）の索引を作る。
出力: shiso_reiki.json

なぜ作るか（2026-08-22指示「市の条例から制度から規約から全部把握しろ」）：
  例規集は市サイトと別の場所（www1.g-reiki.net/city.shiso/）にあり、
  体系目次 → 編・章のページ → 条例本文、という3段の作りになっている。
  全条例の「名前と本文の場所」を索引にしておけば、質問が条例に当たった時に
  アプリがその場で本文を1件だけ取りに行ける（実測: 組織条例で本文4185字）。
  ※本文まで全部溜めると数十MBになりテレビへ配れないので、索引だけ持つ。

作り（2026-08-22 実地調査）：
  reiki_taikei/taikei_default.html … 編・章の一覧（約80リンク）
  reiki_taikei/r_taikei_XX_YY.html … 章ごとの条例一覧
  reiki_honbun/rXXXRGXXXXXXXX.html … 条例の本文
"""
import time
import json, re, time, sys, html, urllib.request, urllib.parse, pathlib

元 = "https://www1.g-reiki.net/city.shiso/"
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app; contact via site)"
出力 = pathlib.Path(__file__).resolve().parent.parent / "shiso_reiki.json"
間 = 0.4


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
    # ★通信は1回で諦めない（2026-08-23）。GitHub Actionsの週1更新が
    #   1回のタイムアウトで丸ごと落ち、79分かけた他の収集まで捨てられた。
    #   相手のサイトに迷惑をかけないよう、間をあけて3回まで試す
    最後 = None
    for 再試行 in range(3):
        try:
            return 取る一回(url)
        except Exception as e:
            最後 = e
            if 再試行 < 2:
                time.sleep(3 * (再試行 + 1))
    raise 最後


def 取る一回(url):
    req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
    with urllib.request.urlopen(req, timeout=25, context=_文脈) as r:
        return r.read().decode("utf-8", "replace")


def リンク(h, 型):
    """href とリンク文字の対。型=正規表現でhrefを絞る"""
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', h, re.S):
        u = m.group(1)
        if not re.search(型, u):
            continue
        t = re.sub(r"<[^>]+>", "", m.group(2))
        t = re.sub(r"\s+", " ", html.unescape(t)).strip()
        if t:
            out.append((u, t))
    return out


if __name__ == "__main__":
    目次 = 取る(元 + "reiki_taikei/taikei_default.html")
    time.sleep(間)
    章たち = リンク(目次, r"r_taikei_[\d_]+\.html")
    if len(章たち) < 30:
        raise SystemExit(f"章の一覧が{len(章たち)}件しか取れない（例年80件。作りが変わった）")
    print(f"編・章 {len(章たち)}件", file=sys.stderr)

    # 編の名前を控える（r_taikei_03.html=編、r_taikei_03_01.html=章）
    編名 = {u.split("_")[2].split(".")[0]: t for u, t in 章たち if u.count("_") == 2}

    索引, 済 = [], set()
    for u, 章名 in 章たち:
        if u.count("_") == 2:      # 編そのもののページは章と中身が重複するので飛ばす
            continue
        try:
            h = 取る(元 + "reiki_taikei/" + u)
        except Exception as e:
            print(f"  読めない {u} {e}", file=sys.stderr)
            continue
        time.sleep(間)
        編番 = u.split("_")[2]
        for hu, 題 in リンク(h, r"reiki_honbun/.+\.html"):
            本url = urllib.parse.urljoin(元 + "reiki_taikei/", hu)
            if 本url in 済:
                continue
            済.add(本url)
            索引.append({"題": 題, "url": 本url,
                         "編": 編名.get(編番, ""), "章": 章名})
        if len(索引) % 100 < 5:
            print(f"  {len(索引)}件 … {章名}", file=sys.stderr)

    if len(索引) < 200:
        raise SystemExit(f"条例が{len(索引)}件しか取れない（作りが変わった疑い）")
    # ★ここで落ちると、1126件を集めきった苦労が全部無駄になる（2026-08-23）。
    #   「内容現在」は添え書きなので、取れなくても索引は保存する
    現在 = None
    try:
        現在 = re.search(r"内容現在\s*([^<）)]+)", 取る(元 + "reiki_menu.html"))
    except Exception as e:
        print(f"  内容現在が取れない（索引はそのまま保存する）: {e}", file=sys.stderr)
    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": 元 + "reiki_menu.html",
        "内容現在": 現在.group(1).strip() if 現在 else "",
        "件数": len(索引),
        "項目": 索引,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"条例・規則 {len(索引)}件 → {出力}（{出力.stat().st_size//1024}KB）")
