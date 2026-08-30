#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宍粟市の逸話・民話・伝説を集める（宍粟市山崎文化協会「しそうの逸話」）。
出力: shiso_bunka.json

なぜ作るか（2026-08-27）：
  「宍粟市の民話を教えて」に、AIが『波賀町の伊和神社』と答えた。
  伊和神社は一宮町。資料が7件しか無かったので、AIが記憶で埋めて外した。
  10月に市の関係者へ見せる場で同じことが起きれば、その場で信用が終わる。
  民話・逸話は「宍粟にしかないネタ」であり、説得の本体でもある。

出典：宍粟市山崎文化協会「しそうの逸話」 https://www.yamasaki-bunka.org/?cat=89
  各話は「サンホールやまさきニュース」の連載『郷土の伝説と民話』が元。
  記事中に、取材相手や元の調査報告（例：昭和47年 兵庫県教育委員会
  「西播奥地民俗資料緊急調査報告」）まで明記されている一次情報。
  ★答える時は必ず出典を添える。丸ごとの読み上げはしない。

行儀よく集めること：1ページごとに間をあけ、名乗る。
"""
import json, re, time, sys, html, urllib.request, pathlib
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from kensan import 件数を守る

元 = "https://www.yamasaki-bunka.org"
名乗り = "ShisochanNET-KB/1.0 (+https://shisochan.net/; citizen broadcast app)"
出力 = pathlib.Path(__file__).resolve().parent.parent / "shiso_bunka.json"
間 = 0.6
# ★取り込むカテゴリ（2026-08-27にサイトのプルダウンから実測した番号と件数）。
#   「お知らせ」(cat=1) は時事なので入れない。文化・芸能の記録だけを集める
カテゴリら = {
    89: "しそうの逸話",        # 65話。郷土の伝説と民話の連載
    28: "山崎民謡連合会",      # 山崎小唄・さつき音頭など
    4:  "やまさき文化",        # 機関誌
    5:  "春の芸能祭",
    6:  "秋のふれあい文化祭",
    7:  "美術展・展覧会",
    26: "宍粟和太鼓アーツ",
    33: "宍粟市吹奏楽団",
    91: "しそうの森合唱祭",
}
上限 = 600                          # 辿る記事数の上限（暴走よけ）

町ら = ["山崎町", "一宮町", "波賀町", "千種町"]


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
    # 通信は1回で諦めない（相手に迷惑をかけないよう間をあけて3回まで）
    最後 = None
    for 再 in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
            with urllib.request.urlopen(req, timeout=25, context=_文脈) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            最後 = e
            if 再 < 2:
                time.sleep(3 * (再 + 1))
    raise 最後


def 文字だけ(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"[ \t　]+", " ", html.unescape(h)).strip()


def 分類を当てる(h):
    """この記事がどのカテゴリか。記事ページのカテゴリ表示から読む。
       どれにも当たらなければ空（＝資料にしない）"""
    for 番, 名 in カテゴリら.items():
        if f"?cat={番}" in h and 名 in h:
            return 名
    return ""


def 本文を取る(h):
    """★entry-content を </div> で切ってはいけない（2026-08-27の失敗）。
       中に画像の <div> が入っているため、最初の写真だけ拾って
       「本文は8文字」と誤判定した。footer か </article> まで通しで取る"""
    m = re.search(r'<div[^>]+class="[^"]*entry-content[^"]*"[^>]*>(.*?)(?=<footer|</article)', h, re.S)
    if not m:
        return ""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", m.group(1), flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t　]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    return re.sub(r"\n{2,}", "\n", t).strip()


def 題を取る(h):
    m = re.search(r"<title>([^<|]+)", h)
    return html.unescape(m.group(1)).strip() if m else ""


def 地区を当てる(題, 文):
    """どの町の話か。題に町名があればそれ。無ければ本文の冒頭から探す。
       ★本文の後ろの方まで見ない（取材の道すがら別の町名が出てくる）"""
    for t in 町ら:
        if t in 題:
            return t
    頭 = 文[:300]
    出た = [t for t in 町ら if t in 頭]
    return 出た[0] if len(出た) == 1 else ""


# ★連載の番号は3通りの書き方が混在する（2026-08-27の実測）。
#   (64) / （８１） / ①  … 丸数字を見落として「番号なし9話」と誤判定した
丸 = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚"


def 番号を取る(題):
    t = 題.strip()
    if t and t[0] in 丸:
        return 丸.index(t[0]) + 1
    m = re.match(r"\s*[（(]?\s*([0-9０-９]{1,3})\s*[）)]", t)
    if not m:
        return 0
    return int(m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))


def 一覧を集める():
    """カテゴリごとにページを辿って記事のURLを集める。
       ★空振りが続いたらそのカテゴリを打ち切る（2026-08-27：
         全カテゴリで30ページまで試して10分を超えた）"""
    urlら = []
    見 = set()
    for カ, 名 in カテゴリら.items():
        取れた = 0
        for p in range(1, 30):
            u = f"{元}/?cat={カ}" + ("" if p == 1 else f"&paged={p}")
            try:
                h = 取る(u)
            except Exception:
                break                     # そのページが無い＝このカテゴリは終わり
            time.sleep(間)
            出 = re.findall(r'href="(https://www\.yamasaki-bunka\.org/\?p=\d+)"', h)
            新規 = [x for x in 出 if x not in 見]
            if not 新規:
                break
            for x in 新規:
                見.add(x); urlら.append(x)
            取れた += len(新規)
        print(f"  {名}(cat={カ}): {取れた}件（累計 {len(urlら)}）", file=sys.stderr)
    return urlら


def 走る():
    待ち = 一覧を集める()
    見た = set()
    集めた = []
    while 待ち and len(見た) < 上限:
        u = 待ち.pop(0)
        if u in 見た:
            continue
        見た.add(u)
        try:
            h = 取る(u)
        except Exception as e:
            print(f"  読めない {u} {e}", file=sys.stderr)
            continue
        time.sleep(間)
        # 前後の記事も辿る（一覧から漏れた話を拾うため）
        for m in re.finditer(r'<a[^>]+href="(https://www\.yamasaki-bunka\.org/\?p=\d+)"[^>]*rel="(?:prev|next)"', h):
            if m.group(1) not in 見た and m.group(1) not in 待ち:
                待ち.append(m.group(1))
        分類 = 分類を当てる(h)
        if not 分類:
            continue
        題 = 題を取る(h)
        文 = 本文を取る(h)
        if len(文) < 150:                      # 中身の無い記事は資料にしない
            continue
        集めた.append({
            "題": 題,
            "分類": 分類,
            "番": 番号を取る(題),
            "地区": 地区を当てる(題, 文),
            "文": 文[:6000],
            "url": u,
        })
        if len(集めた) % 20 == 0:
            print(f"  {len(集めた)}話 … {題[:26]}", file=sys.stderr)
    集めた.sort(key=lambda r: (r["番"] or 999, r["題"]))
    return 集めた


if __name__ == "__main__":
    集めた = 走る()
    件数を守る("逸話・文化", len(集めた))
    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市山崎文化協会「しそうの逸話」 https://www.yamasaki-bunka.org/?cat=89"
                "（元：サンホールやまさきニュース『郷土の伝説と民話』）",
        "件数": len(集めた),
        "項目": 集めた,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    地区あり = sum(1 for x in 集めた if x["地区"])
    字 = sum(len(x["文"]) for x in 集めた)
    print(f"{len(集めた)}話（地区が分かるもの {地区あり}話・本文 計{字:,}字）"
          f" → {出力}（{出力.stat().st_size//1024}KB）")
