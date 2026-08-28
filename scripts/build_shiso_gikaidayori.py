# -*- coding: utf-8 -*-
"""宍粟市議会だより（市政の実際の議論）

なぜ：
  議会だよりには、議案の中身・賛否・討論・一般質問が載っている。
  「新病院はどうなっている」「市議会で何を議論している」に答える一次資料。
  市のサイトの本文には載っておらず、PDFの中にしかない。

どこまで取るか：
  ★号単位で出ている分（Vol付き）だけを取る。
    平成17〜21年度は「2ページ」「3ページ」のようにページ単位で分かれており、
    1冊ぶんが40ファイルに散っている。今の市政の議論を答えるのが目的なので、
    号単位でまとまっている近年の分に絞る。
"""
import json, pathlib, re, ssl, subprocess, sys, time, urllib.request
import certifi

根 = pathlib.Path(__file__).resolve().parent.parent
間 = 1.0

def 取る(url, 秒=240):
    c = ssl.create_default_context(cafile=certifi.where())
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(r, timeout=秒, context=c).read()

def 道具():
    元 = 根 / "scripts" / "pdf2txt.swift"
    p = pathlib.Path("/tmp/shiso_pdf2txt")
    if (not p.exists()) or p.stat().st_mtime < 元.stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(元), "-o", str(p)], check=True)
    return p

def 文字読みの道具():
    """画像だけのPDF用（macOSのVisionで文字を読む）。
       ★実測：議会だよりVol.75・79・82は文字情報が1字も無い画像PDFで、
         ふつうの取り出しでは0字だった。目で見える字は読めるので、
         読み取りにかけて拾う"""
    元 = 根 / "scripts" / "pdfocr.swift"
    p = pathlib.Path("/tmp/shiso_pdfocr")
    if (not p.exists()) or p.stat().st_mtime < 元.stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(元), "-o", str(p)], check=True)
    return p

def 整える(t):
    """PDFの段組みで、同じ行が2回出ることがある（実測：見出しが二重）。
       ★連続して同じ行が並んだら1つにする"""
    行 = [l.strip() for l in t.split("\n")]
    出 = []
    for l in 行:
        if not l: continue
        if 出 and 出[-1] == l: continue
        出.append(l)
    s = "\n".join(出)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()

def 主():
    d = 道具()
    文字読み = 文字読みの道具()
    kb = json.loads((根 / "shiso_kb.json").read_text(encoding="utf-8"))["項目"]
    冊 = []
    見 = set()
    for x in kb:
        if "議会だより" not in x.get("題", ""): continue
        for a in x.get("添付", []):
            名 = a.get("名", "")
            m = re.search(r"[Vv]ol\.?\s*(\d+)", 名)
            if not m: continue                     # ページ単位の古い分は取らない
            号 = int(m.group(1))
            if 号 in 見: continue
            見.add(号)
            冊.append({"号": 号, "名": 名, "url": a.get("url", ""), "年度": x["題"]})
    冊.sort(key=lambda x: -x["号"])
    上限 = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    冊 = 冊[:上限]
    if not 冊:
        print("！ 号単位の議会だよりが1冊も無い"); return 1
    print(f"号単位の議会だより {len(見)}冊を見つけ、新しい順に {len(冊)}冊を取る")
    出, 字数, 失敗 = [], 0, []
    for i, c in enumerate(冊, 1):
        try:
            b = 取る(c["url"])
            仮 = 根 / "scripts" / "_gikai.pdf"
            仮.write_bytes(b)
            r = subprocess.run([str(d), str(仮)], capture_output=True, timeout=180)
            t = 整える(r.stdout.decode("utf-8", "replace"))
            読み = ""
            # ★頁数に対して字が少なすぎる号もある（2026-08-28の実測：
            #   Vol.76は12頁で2,053字＝1頁170字。文字と画像が混ざった作りで、
            #   本文の大半が画像になっている）。1頁500字を下回れば読み取りも試す
            頁数 = 0
            try:
                import pypdf
                頁数 = len(pypdf.PdfReader(str(仮)).pages)
            except Exception: pass
            薄い = 頁数 > 0 and len(t) < 頁数 * 500
            if len(t) < 800 or 薄い:
                o = subprocess.run([str(文字読み), str(仮)], capture_output=True, timeout=600)
                t2 = 整える(o.stdout.decode("utf-8", "replace"))
                if len(t2) > len(t): t, 読み = t2, "（画像から読み取り）"
            仮.unlink()
        except Exception as e:
            失敗.append((c["名"], str(e)[:50])); continue
        if len(t) < 800:
            失敗.append((c["名"], f"文章が短い {len(t)}字")); continue
        一 = {"号": c["号"], "年度": c["年度"], "url": c["url"], "文": t}
        if 読み: 一["読み取り"] = True
        出.append(一)
        字数 += len(t)
        print(f"  {i}/{len(冊)} Vol.{c['号']} … {len(t):,}字 {読み}")
        time.sleep(間)
    if not 出:
        print("！ 1冊も読めなかった"); return 1
    先 = 根 / "shiso_gikaidayori.json"
    先.write_text(json.dumps({
        "作成": "宍粟市議会だより（市公式サイトのPDF）より",
        "冊数": len(出), "字数": 字数,
        "項目": sorted(出, key=lambda x: -x["号"])}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    号ら = sorted(x["号"] for x in 出)
    飛 = [n for n in range(号ら[0], 号ら[-1] + 1) if n not in 号ら]
    print(f"\n○ {len(出)}冊・{字数:,}字 → {先}（{先.stat().st_size//1024}KB）")
    print(f"検算: Vol.{号ら[0]}〜Vol.{号ら[-1]} で欠け {len(飛)}冊 {飛 if 飛 else ''}")
    if 失敗:
        print(f"！ 取れなかった {len(失敗)}冊:")
        for n, e in 失敗[:6]: print(f"    {n[:40]} … {e}")
    # 中身の確かめ（議案・一般質問が入っているか）
    全 = " ".join(x["文"] for x in 出)
    for 語 in ("一般質問", "議案", "賛成", "反対", "定例会"):
        print(f"  「{語}」{全.count(語)}回")
    return 0

if __name__ == "__main__":
    sys.exit(主())
