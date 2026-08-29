#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ごみの50音順分別早見表を取り込む。
出力: shiso_bunbetsu.json

なぜ作るか（2026-08-28）：
  市民がいちばん多く聞くのは「これは何ごみ？」。
  ところが資料には収集日の地区表（34地区）しか無く、
  **品目ごとの分別が1件も入っていなかった**。
  「アイロンは何ごみ」「網戸は」「油は」に答えられない。

  市は「家庭ごみの分け方と出し方ガイドブック」の
  50音順早見表をあ行〜わ行の9つのPDFで出している。
  品名・ごみの種類・出し方のワンポイント・出し方（指定袋/シール）の
  4つが表になっている。これを取り込めば、そのまま答えになる。

★市のPDFに書いてある言葉だけを使う。こちらで分別を決めない。
★取り込んだ品目数を検算して出す（検収三原則②）。
"""
import json, re, sys, time, subprocess, shutil, pathlib, urllib.request

根 = pathlib.Path(__file__).resolve().parent.parent
出力 = 根 / "shiso_bunbetsu.json"
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app)"
元 = "https://www.city.shiso.lg.jp/material/files/group/58/"
親 = "https://www.city.shiso.lg.jp/mokuteki/gomi/21485.html"

行ら = [("あ行", "a_gomiguidebook.pdf"), ("か行", "ka_gomiguidebook.pdf"),
        ("さ行", "sa_gomiguidebook.pdf"), ("た行", "ta_gomiguidebook.pdf"),
        ("な行", "na_gomiguidebook.pdf"), ("は行", "ha_gomiguidebook.pdf"),
        ("ま行", "ma_gomiguidebook.pdf"), ("や・ら・わ行", "ya_ra_wa_gomiguidebook.pdf")]

# PDFに実際に書かれている「ごみの種類」。ここに無い言葉が出たら知らせる
種類 = ["燃やさない", "燃やす", "粗大", "資源", "特殊", "小型家電",
        "取り扱わない", "拠点回収", "集団回収", "危険", "販売店"]


def _ssl():
    try:
        import ssl, certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        import ssl
        return ssl.create_default_context()


def 取る(url):
    req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
    with urllib.request.urlopen(req, timeout=90, context=_ssl()) as r:
        return r.read()


def 取り出し係():
    if shutil.which("pdftotext"):
        return lambda p: subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(p), "-"],
                                        capture_output=True, timeout=180
                                        ).stdout.decode("utf-8", "replace")
    元s = 根 / "scripts" / "pdf2txt.swift"
    道具 = pathlib.Path("/tmp/shiso_pdf2txt")
    if shutil.which("swiftc"):
        if (not 道具.exists()) or 道具.stat().st_mtime < 元s.stat().st_mtime:
            subprocess.run(["swiftc", "-O", str(元s), "-o", str(道具)], check=True)
        return lambda p: subprocess.run([str(道具), str(p)], capture_output=True,
                                        timeout=180).stdout.decode("utf-8", "replace")
    raise SystemExit("PDFの文章を取り出す道具が無い")


def 品目に分ける(文, 行名):
    """使わない（座標で読む方式に置き換えた。下の 表を読む を使う）"""
    return []


def 語を読む(pdf, 頁):
    """PDFの文字を座標つきで取り出す（1語1行のTSV）"""
    r = subprocess.run([str(道具), str(pdf), str(頁)], capture_output=True, timeout=120)
    出 = []
    for l in r.stdout.decode("utf-8", "replace").split("\n"):
        c = l.split("\t")
        if len(c) < 5: continue
        try: 出.append((c[0], float(c[1]), float(c[2])))
        except ValueError: pass
    return 出


def 表を読む(pdf, 行名):
    """★列の位置（x座標）で分ける（2026-08-28）。
       文字の並び順だけで読むと、品名の欄にワンポイントが混ざる
       （「凝固剤固めて出してください 指定袋油（機械•燃料系）」）。
       紙の上の位置なら、どの列の文字かが確実に分かる。
       列のx：品名47／種類164／ワンポイント241／出し方478（実測）"""
    出, 頁 = [], 1
    while 頁 <= 12:
        語 = 語を読む(pdf, 頁)
        if not 語: break
        頁 += 1
        # 見出しの行（品名/ごみの種類/…）のyを見つけ、その下だけを読む
        頭 = [y for w, x, y in 語 if w == "品名"]
        始 = min(頭) + 8 if 頭 else 0
        # 同じ品目に属する語をまとめる：品名の列(x<150)に文字が現れたら新しい品目
        今 = None
        for w, x, y in sorted(語, key=lambda t: (t[2], t[1])):
            if y < 始: continue
            if re.fullmatch(r"\d+/\d+", w): continue
            if x < 150:
                if len(w) == 1 and re.fullmatch(r"[ぁ-んァ-ン]", w):
                    continue                       # 行の見出し文字（あ・か…）
                if 今 is None or abs(y - 今["y"]) > 14:
                    今 = {"品名": w, "種類": "", "ワンポイント": "", "出し方": "",
                          "行": 行名, "y": y}
                    出.append(今)
                else:
                    今["品名"] += w                # 折り返した品名
            elif 今 is None:
                continue
            elif x < 230:
                # ★種類は「燃やす」「資源（びん）」のような短い語しか入らない。
                #   長い説明が混ざるのは、隣の品目の行を拾っているため（実測7件）。
                #   すでに種類が入っていて、次に来た語が説明なら足さない
                if 今["種類"] and (len(w) > 8 or not w.startswith(("燃", "粗", "資", "特",
                                                                   "小", "取", "拠", "集",
                                                                   "危", "販"))):
                    今["ワンポイント"] = (今["ワンポイント"] + w).strip()
                elif 今["種類"] and w.startswith(("燃", "粗", "資", "特", "小", "取")):
                    pass                      # 別の品目の種類。混ぜない
                else:
                    今["種類"] = (今["種類"] + w).strip()
            elif x < 460:
                今["ワンポイント"] = (今["ワンポイント"] + w).strip()
            else:
                今["出し方"] = (今["出し方"] + w).strip()
    for x in 出: x.pop("y", None)
    return [x for x in 出 if x["品名"] and x["種類"]]

道具 = pathlib.Path("/tmp/shiso_pdfwords")


def 座標の道具を用意():
    元s = 根 / "scripts" / "pdfwords.swift"
    if (not 道具.exists()) or 道具.stat().st_mtime < 元s.stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(元s), "-o", str(道具)], check=True)


if __name__ == "__main__":
    座標の道具を用意()
    取り出す = 取り出し係()
    全, 字数 = [], 0
    for 行名, f in 行ら:
        try:
            b = 取る(元 + f)
        except Exception as e:
            print(f"！{行名} が取れない {e}", file=sys.stderr); sys.exit(1)
        一時 = pathlib.Path("/tmp/shiso_bunbetsu.pdf"); 一時.write_bytes(b)
        文 = 取り出す(一時); 字数 += len(文)
        time.sleep(0.6)
        v = 表を読む(一時, 行名)
        print(f"  {行名}: {len(v)}品目（PDF {len(文):,}字）", file=sys.stderr)
        全 += v

    # 同じ品名が複数回出たらまとめる
    束 = {}
    for x in 全:
        if x["品名"] not in 束: 束[x["品名"]] = x
    項目 = sorted(束.values(), key=lambda x: x["品名"])
    if len(項目) < 200:
        print(f"★品目が {len(項目)} しか取れていない。読み取りが壊れている", file=sys.stderr)
        sys.exit(1)

    import collections
    数 = collections.Counter(x["種類"] for x in 項目)

    # ★ごみ袋とシールの値段（2026-08-28）。市民がいちばん多く聞く値段なのに
    #   「ごみ袋はいくらですか」に答えられなかった。
    #   市の『市指定ごみ袋等と取扱店』に書いてある値段だけを写す
    袋 = []
    try:
        kb = json.loads((根 / "shiso_kb.json").read_text(encoding="utf-8"))["項目"]
        for x in kb:
            if "市指定ごみ袋" not in x.get("題", ""): continue
            f = re.sub(r"\s+", " ", x.get("文", ""))
            # ★実データで確かめた形（2026-08-28）：
            #   「もやすごみ専用袋（大） 45リットル 506円 （460円+46円） 20枚入」
            #   最初に書いた形（[^\s]で名前を取る）では1件も取れなかった
            for m in re.finditer(
                    r"((?:もやす|もやさない|粗大)[^\s]{0,14}(?:専用袋|専用シール)"
                    r"(?:（[^）]*）)?)\s*(?:(\d+)リットル\s*)?([\d,]+)円"
                    r"\s*（[^）]*）\s*(\d+)枚", f):
                袋.append({"名": m.group(1).strip(),
                           "リットル": int(m.group(2)) if m.group(2) else None,
                           "1セットの値段": int(m.group(3).replace(",", "")),
                           "枚数": int(m.group(4)),
                           "url": x.get("url", "")})
            break
    except Exception as e:
        print(f"  ！ ごみ袋の値段が読めない: {e}", file=sys.stderr)
    if 袋:
        print("  ごみ袋の値段:", [(b["名"], b["1セットの値段"], b["枚数"]) for b in 袋])
    else:
        print("  ！ ごみ袋の値段が1件も取れなかった", file=sys.stderr)

    出力.write_text(json.dumps({
        "説明": "ごみの50音順分別早見表。品名からごみの種類と出し方が分かる",
        "出典": "宍粟市「家庭ごみの分け方と出し方ガイドブック」50音順早見表",
        "url": 親, "件数": len(項目), "項目": 項目,
        "ごみ袋の値段": 袋,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"○ {len(項目)}品目 → shiso_bunbetsu.json（{出力.stat().st_size//1024}KB）")
    print(f"  検算: PDF合計 {字数:,}字 → 拾った {len(全)}行 → 重複を除いて {len(項目)}品目")
    print("  種類ごと:", dict(数))
    print("  例:", [f"{x['品名']}={x['種類']}" for x in 項目[:6]])
