# -*- coding: utf-8 -*-
"""証明書の手数料（住民票・戸籍・印鑑証明など）

なぜ：
  「住民票はいくらですか」に答えられなかった。市民がいちばん多く聞く値段。
  市のページ本文には金額が1つも書かれておらず、PDFの表にしかない。
  ★誤った金額を言うと窓口で迷惑がかかるので、表の位置で正確に読む。

★この表は2列組み（左：戸籍証明書等／右：住民票等・印鑑登録）。
  文字の並び順で読むと、種類と金額の対応が崩れる。
"""
import json, pathlib, re, ssl, subprocess, sys, urllib.request
import certifi

根 = pathlib.Path(__file__).resolve().parent.parent
道具 = pathlib.Path("/tmp/shiso_pdfwords")

def 道具を用意():
    元 = 根 / "scripts" / "pdfwords.swift"
    if (not 道具.exists()) or 道具.stat().st_mtime < 元.stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(元), "-o", str(道具)], check=True)

def 取る(url):
    c = ssl.create_default_context(cafile=certifi.where())
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(r, timeout=180, context=c).read()

def 主():
    道具を用意()
    kb = json.loads((根 / "shiso_kb.json").read_text(encoding="utf-8"))["項目"]
    url = None
    for x in kb:
        for a in x.get("添付", []):
            if "各種証明書手数料" in a.get("名", ""):
                url = a["url"]; 元題 = x.get("題", ""); 元url = x.get("url", "")
                break
        if url: break
    if not url:
        print("！ 各種証明書手数料のPDFが見つからない"); return 1
    仮 = 根 / "scripts" / "_tesu.pdf"
    仮.write_bytes(取る(url))
    r = subprocess.run([str(道具), str(仮), "1"], capture_output=True, timeout=120)
    仮.unlink()
    語 = []
    for l in r.stdout.decode("utf-8", "replace").split("\n"):
        c = l.split("\t")
        if len(c) < 3: continue
        try: 語.append((c[0], float(c[1]), float(c[2])))
        except ValueError: pass
    if not 語:
        print("！ PDFから字が取れなかった"); return 1

    # 行にまとめる（y座標が近いものを同じ行に）
    from collections import defaultdict
    行ら = defaultdict(list)
    for w, x, y in 語: 行ら[round(y)].append((x, w))

    # ★左の表（x<320）と右の表（x>=320）に分けて読む
    出 = []
    for 端, 種x, 金x in ((0, 60, 260), (320, 340, 500)):
        for y in sorted(行ら):
            並 = sorted([(x, w) for x, w in 行ら[y] if 端 <= x < 端 + 320])
            if not 並: continue
            種 = "".join(w for x, w in 並 if 種x <= x < 金x)
            金 = "".join(w for x, w in 並 if x >= 金x)
            種 = re.sub(r"\s+", "", 種)
            if len(種) < 2: continue
            m = re.fullmatch(r"([\d,]{3,5})|無\s*料", 金.strip())
            # ★セルが縦に伸びていて、金額が次の行にあることがある（実測：
            #   「住民票 謄本・抄本・除票」はy=159、金額300はy=178）。
            #   同じ列の、すぐ下（25px以内）にある数字も見る
            if not m:
                for y2 in sorted(行ら):
                    if not (y < y2 <= y + 25): continue
                    右 = [(x, w) for x, w in 行ら[y2] if 端 <= x < 端 + 320]
                    種2 = "".join(w for x, w in 右 if 種x <= x < 金x).strip()
                    金2 = "".join(w for x, w in 右 if x >= 金x).strip()
                    if 種2: break            # 次の種類が始まっていたら諦める
                    m2 = re.fullmatch(r"([\d,]{3,5})|無\s*料", 金2)
                    if m2: m, 金 = m2, 金2; break
            if not m: continue
            if 種 in ("種類", "手数料"): continue
            出.append({"種類": 種, "手数料": 0 if "無" in 金 else int(m.group(1).replace(",", "")),
                       "無料": "無" in 金})
    if not 出:
        print("！ 手数料が1件も読めなかった"); return 1
    先 = 根 / "shiso_tesuryo.json"
    先.write_text(json.dumps({
        "作成": "宍粟市『各種証明書手数料』（PDF）より",
        "出典の題": 元題, "url": 元url, "pdf": url,
        "件数": len(出), "項目": 出}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"○ 証明書の手数料 {len(出)}件 → {先}（{先.stat().st_size//1024}KB）")
    for x in 出: print(f"   {x['種類'][:30]:32s} {'無料' if x['無料'] else str(x['手数料'])+'円'}")
    # ★検算：金額が筋の通る値か
    変 = [x for x in 出 if not x["無料"] and not (100 <= x["手数料"] <= 5000)]
    if 変: print(f"！ 金額が筋に合わない: {変}")
    else: print(f"検算: すべて100〜5000円の幅に収まっている")
    return 0

if __name__ == "__main__":
    sys.exit(主())
