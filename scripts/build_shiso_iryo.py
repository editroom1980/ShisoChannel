#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宍粟市の医療情報（休日当番医・加盟医療機関）を集める。
出力: shiso_iryo.json

なぜ作るか（2026-08-27）：
  資料に「当番医」「休日診療」が0件だった。テレビの前の高齢者が
  日曜に具合を悪くしたとき、一番聞きたいのは「今日どこが開いているか」。
  命に関わる情報が丸ごと抜けていた。

出典：一般社団法人 宍粟市医師会 https://shiso-med.jp/
  ・日曜・休日在宅当番医  https://shiso-med.jp/duty-doctor/
  ・加盟医療機関一覧      https://shiso-med.jp/clinic-lis/
  市の公式ページ「日曜休日当直医」も、当番医の一覧はここへ案内している。

★当番医は毎月変わる。定期的に取り直すこと。
★重症・救急は 119番 か 公立宍粟総合病院（0790-62-2410）。
  当番医は「軽症患者の診察」と医師会が明記している。答える時に必ず添える。
"""
import json, re, time, sys, html, urllib.request, pathlib

元 = "https://shiso-med.jp"
名乗り = "ShisochanNET-KB/1.0 (+https://shisochan.net/; citizen broadcast app)"
出力 = pathlib.Path(__file__).resolve().parent.parent / "shiso_iryo.json"
間 = 0.8


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


def 電話を正す(t):
    """全角ハイフン等をそろえ、番号の形だけを残す"""
    t = t.replace("‐", "-").replace("－", "-").replace("−", "-").replace("―", "-")
    m = re.search(r"0\d{1,4}-\d{1,4}-\d{3,4}", t)
    return m.group(0) if m else ""


def 当番医を取る():
    """日曜・休日在宅当番医。月ごとの見出し→その中の（日付・医院・電話）を拾う"""
    h = 取る(元 + "/duty-doctor/")
    出 = []
    # 「📅 2026年8月 当番医」で月ごとに切る
    区切り = [(m.start(), int(m.group(1)), int(m.group(2)))
              for m in re.finditer(r"(\d{4})年\s*(\d{1,2})月\s*当番医", h)]
    if not 区切り:
        print("  当番医の見出しが見つからない（ページの作りが変わった可能性）", file=sys.stderr)
        return 出
    for i, (位置, 年, 月) in enumerate(区切り):
        終 = 区切り[i + 1][0] if i + 1 < len(区切り) else len(h)
        塊 = h[位置:終]
        # 日付 … 医院名 … 電話 の並び
        for m in re.finditer(
                r'>(\d{1,2})月(\d{1,2})日（([日月火水木金土祝])）</span>.*?'
                r"font-family:'Noto Serif JP',serif;[^\"]*\">([^<]+)</div>.*?"
                r"📞\s*([0-9\-‐－−]+)", 塊, re.S):
            月2, 日, 曜, 名, 電 = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            出.append({
                "日": f"{年:04d}-{int(月2):02d}-{int(日):02d}",
                "曜": 曜,
                "医院": html.unescape(名).strip(),
                "電話": 電話を正す(電),
            })
    # 同じ日に複数の当番医がある（実データで確認済み）。重複だけ落とす
    見, 一覧 = set(), []
    for x in 出:
        鍵 = (x["日"], x["医院"])
        if 鍵 in 見:
            continue
        見.add(鍵); 一覧.append(x)
    一覧.sort(key=lambda x: (x["日"], x["医院"]))
    return 一覧


def 医療機関を取る():
    """加盟医療機関一覧。data-属性に名前・住所・診療科が入っている"""
    h = 取る(元 + "/clinic-lis/")
    出 = []
    for m in re.finditer(
            r'data-name="([^"]+)"\s*data-addr="([^"]*)"\s*data-types="([^"]*)"(.*?)(?=<div class="cl-card"|</div>\s*</div>\s*$)',
            h, re.S):
        名, 住, 科, 後 = (html.unescape(m.group(i)).strip() for i in (1, 2, 3, 4))
        電 = ""
        t = re.search(r'href="tel:([0-9\-‐－−]+)"', 後)
        if t:
            電 = 電話を正す(t.group(1))
        出.append({
            "名": 名,
            "住所": 住,
            "科": [x for x in 科.split(",") if x],
            "電話": 電,
        })
    return 出


if __name__ == "__main__":
    当番 = 当番医を取る()
    time.sleep(間)
    機関 = 医療機関を取る()

    # ── 検算（件数だけ見て合格にしない）──
    電話あり = sum(1 for x in 機関 if x["電話"])
    住所あり = sum(1 for x in 機関 if x["住所"])
    当番電話 = sum(1 for x in 当番 if x["電話"])
    print(f"当番医 {len(当番)}件（電話あり {当番電話}件）／"
          f"医療機関 {len(機関)}件（電話 {電話あり}件・住所 {住所あり}件）", file=sys.stderr)
    if not 当番 or not 機関:
        print("★取れていない。ページの作りが変わった可能性がある", file=sys.stderr)
        sys.exit(1)
    if 当番電話 < len(当番) or 電話あり < len(機関) * 0.9:
        print("★電話番号の取りこぼしが多い。取り出し方を見直すこと", file=sys.stderr)
        sys.exit(1)

    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "一般社団法人 宍粟市医師会 https://shiso-med.jp/"
                "（当番医 /duty-doctor/・医療機関一覧 /clinic-lis/）",
        "注意": "休日当番医は軽症の診察。重症・救急は119番か公立宍粟総合病院"
                "（0790-62-2410）。救急の相談は#7119（24時間365日）",
        "当番医": 当番,
        "医療機関": 機関,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"当番医 {len(当番)}件・医療機関 {len(機関)}件 → {出力}"
          f"（{出力.stat().st_size//1024}KB）")
