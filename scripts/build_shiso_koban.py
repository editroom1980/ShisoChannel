#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宍粟市の交番・駐在所を、兵庫県警察の公式一覧から作る。
出力: shiso_koban.json

なぜ作るか（2026-08-27）：
  「駐在所はどこ」「交番はどこ」に答えられなかった。
  市のサイトは自前の施設しか載せておらず、警察の施設は資料に無かった。
  困っている人が最初に聞くかもしれない場所なので、押さえておく。

出典：兵庫県警察「交番・駐在所一覧」
  https://www.police.pref.hyogo.lg.jp/shokai/koban/index2.htm
★110番が必要な時は迷わず110番。答えにその旨を添える。
"""
import json, re, sys, time, html, pathlib, urllib.request

出力 = pathlib.Path(__file__).resolve().parent.parent / "shiso_koban.json"
名乗り = "ShisochanNET-KB/1.0 (+https://shisochan.net/; citizen broadcast app)"
元 = "https://www.police.pref.hyogo.lg.jp/shokai/koban/index2.htm"


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


def 取る(url):
    最後 = None
    for 再 in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
            with urllib.request.urlopen(req, timeout=30, context=_ssl文脈()) as r:
                return r.read()
        except Exception as e:
            最後 = e
            if 再 < 2:
                time.sleep(3 * (再 + 1))
    raise 最後


if __name__ == "__main__":
    生 = 取る(元)
    for enc in ("utf-8", "shift_jis", "cp932", "euc_jp"):
        try:
            s = 生.decode(enc); break
        except Exception:
            continue
    else:
        s = 生.decode("utf-8", "ignore")

    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    t = re.sub(r"</t[dh]>", "\t", t)
    t = re.sub(r"</tr>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    行 = [re.sub(r"[ 　]+", " ", x).strip() for x in html.unescape(t).split("\n")]

    # ★宍粟市の住所を持つ行だけを拾う（警察署のブロックの切り出しに頼らない）。
    #   一覧は「名前」と「所在地」が別の行に分かれて出てくる形なので、
    #   直前の行を名前として組にする
    出 = []
    署電話 = ""
    for i, x in enumerate(行):
        if "宍粟警察署" in x:
            m = re.search(r"[(（]?0\d{3}[)）]?\s*[-－]?\s*\d{2}[-－]\d{4}", "".join(行[i:i+3]))
            if m:
                署電話 = re.sub(r"[()（）\s]", "", m.group(0)).replace("－", "-")
                if not 署電話.startswith("0"):
                    署電話 = "0" + 署電話.lstrip("0")
        if not x.startswith("宍粟市"):
            continue
        名 = 行[i - 1].strip() if i > 0 else ""
        if not re.search(r"(交番|駐在所)$", 名):
            continue
        住 = x.replace("１", "1").replace("２", "2").replace("３", "3").replace("４", "4") \
              .replace("５", "5").replace("６", "6").replace("７", "7").replace("８", "8") \
              .replace("９", "9").replace("０", "0").replace("－", "-")
        出.append({
            "名": 名,
            "住所": 住,
            "地区": next((g for g in ("山崎町", "一宮町", "波賀町", "千種町") if g in 住), ""),
            "種類": "交番" if 名.endswith("交番") else "駐在所",
        })

    見, 一覧 = set(), []
    for x in 出:
        if x["名"] in 見:
            continue
        見.add(x["名"]); 一覧.append(x)
    一覧.sort(key=lambda x: (x["種類"] != "交番", x["地区"], x["名"]))

    if len(一覧) < 5:
        print(f"★{len(一覧)}件しか取れていない。一覧の作りが変わった可能性", file=sys.stderr)
        sys.exit(1)
    地区あり = sum(1 for x in 一覧 if x["地区"])
    if 地区あり < len(一覧) * 0.9:
        print(f"★地区が分からないものが多い（{len(一覧)-地区あり}件）", file=sys.stderr)
        sys.exit(1)

    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "兵庫県警察「交番・駐在所一覧」 " + 元,
        "警察署": {"名": "宍粟警察署", "電話": 署電話 or "0790-62-0110",
                   "住所": "宍粟市山崎町今宿5番地"},
        "注意": "事件・事故で急ぐときは110番。駐在所は不在のことがあります",
        "件数": len(一覧),
        "項目": 一覧,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    from collections import Counter
    print(f"{len(一覧)}か所 → {出力}（{出力.stat().st_size//1024}KB）")
    for k, v in Counter(x["種類"] for x in 一覧).most_common():
        print(f"  {k}: {v}か所")
    for k, v in Counter(x["地区"] or "(不明)" for x in 一覧).most_common():
        print(f"  {k}: {v}")
