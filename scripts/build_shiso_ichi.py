#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""市の施設の場所（緯度経度）と、その最寄りのバス停を出す。
出力: shiso_ichi.json

なぜ作るか（2026-08-28のご指示）：
  「もし施設名を言われたら、出発のバス停を聞いて、
    そこから目的地の最寄りのバス停を案内しろ」

  市民は「山崎文化会館まで」と言う。バス停の名前では言わない。
  ところが山崎文化会館は山崎町鹿沢にあり、鹿沢という名前のバス停は無い。
  大字で結びつけようとすると、文化会館・防災センター・千種市民協働センターなど
  7件が「最寄りが分からない」で落ちていた。

  市の施設ページには「地図情報」があり、その中の地図リンクに
  **市自身が置いた緯度経度**が入っている（例：
  maps.google.co.jp/maps?q=35.0025033,134.5386003）。
  これと、しーたんバスGTFSの停留所の座標を突き合わせれば、
  推測せずに最寄りのバス停が出せる。

★こちらで座標を作らない。市のページに書いてある数字だけを使う。
★最寄りが遠い（1km超）時は「最寄り」と言わずに、そう分かるよう印を残す。
"""
import json, math, re, sys, time, pathlib, urllib.request, importlib.util

根 = pathlib.Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("kb", 根/'scripts'/'build_shiso_kb.py')
kb取り = importlib.util.module_from_spec(_s); _s.loader.exec_module(kb取り)

出力 = 根 / "shiso_ichi.json"
間 = 0.6
遠い = 1.0          # km。これを超えたら「最寄り」と言い切らない


def 距離km(y1, x1, y2, x2):
    return math.hypot((y1 - y2) * 111.0, (x1 - x2) * 91.0)


def 座標を拾う(生html):
    """市のページが置いている地図リンクから緯度経度を取る"""
    for 型 in (r"maps\.google\.co\.jp/maps\?q=(-?\d+\.\d+),(-?\d+\.\d+)",
               r"maps\.google\.co\.jp/\?ll=(-?\d+\.\d+),(-?\d+\.\d+)",
               r"[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)",
               r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)"):
        m = re.search(型, 生html)
        if m:
            y, x = float(m.group(1)), float(m.group(2))
            # 宍粟市のあたりから外れていたら使わない（別の地図の貼り間違い）
            if 34.8 <= y <= 35.4 and 134.3 <= x <= 134.8:
                return y, x
    return None


if __name__ == "__main__":
    kb = json.loads((根/'shiso_kb.json').read_text(encoding="utf-8"))["項目"]
    bus = json.loads((根/'shiso_bus.json').read_text(encoding="utf-8"))
    停座 = bus["停の座標"]
    便 = bus.get("停の便数", {})
    # ★施設のページだけに絞る（2026-08-28の検算で発覚）。
    #   「地図情報」は催しのお知らせにも付いていて、
    #   「10月30日食育講演会 参加者募集」まで施設として拾っていた
    催し = re.compile(r"募集|講座|セミナー|教室|申込|講演|開催|中止|参加者|"
                      r"イベント|フェス|まつり|祭|コンクール|大会|試験|説明会|"
                      r"バリアフリー情報|ご利用案内|^\d|検索|手続|証明|マップ|データ")
    候 = [x for x in kb
          if "地図情報" in x.get("文", "") and x.get("url")
          and not 催し.search(x.get("題", ""))
          and re.search(r"所在地|住所", x.get("文", ""))]
    print(f"地図情報を持つページ {len(候)}件を見る", file=sys.stderr)

    出, 取れず = [], []
    for i, x in enumerate(候):
        try:
            h = kb取り.取る(x["url"])
        except Exception as e:
            取れず.append((x["題"], str(e)[:40])); continue
        time.sleep(間)
        z = 座標を拾う(h)
        if not z:
            取れず.append((x["題"], "地図の座標が無い")); continue
        y, xx = z
        近 = sorted(((距離km(y, xx, a, b), s) for s, (a, b) in 停座.items()))[:4]
        住 = re.search(r"宍粟市[^\s、。]{2,24}", x.get("文", ""))
        出.append({
            "名": x["題"], "url": x["url"],
            "緯度": y, "経度": xx,
            "住所": 住.group(0) if 住 else "",
            "最寄りの停": 近[0][1],
            "最寄りまでm": round(近[0][0] * 1000),
            "近い停": [{"停": s, "m": round(d * 1000), "便": 便.get(s, 0)} for d, s in 近],
            "遠い": 近[0][0] > 遠い,
        })
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(候)}", file=sys.stderr)

    # ★同じ施設が複数のページに出る（スポニックパーク一宮・波賀B&G海洋センター）。
    #   名前でまとめ、最寄りが近い方を残す
    束 = {}
    for r in 出:
        if r["名"] not in 束 or r["最寄りまでm"] < 束[r["名"]]["最寄りまでm"]:
            束[r["名"]] = r
    出 = sorted(束.values(), key=lambda r: r["名"])
    遠 = [r for r in 出 if r["遠い"]]
    出力.write_text(json.dumps({
        "説明": "市の施設の場所と最寄りのバス停。座標は市の施設ページの地図リンクから",
        "出典": "宍粟市公式サイト（各施設ページの地図情報）＋ しーたんバスGTFSの停留所座標",
        "件数": len(出), "遠い件数": len(遠), "項目": 出,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"○ {len(出)}件（座標が取れなかった {len(取れず)}件）")
    print(f"  最寄りが1kmを超える施設 {len(遠)}件")
    for r in 出[:12]:
        print(f"   {r['名'][:26]:28s} → {r['最寄りの停']}（{r['最寄りまでm']}m）")
    if 取れず:
        print("  座標が取れなかった例:", [t for t, _ in 取れず[:5]])
