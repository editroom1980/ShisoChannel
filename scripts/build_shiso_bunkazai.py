# -*- coding: utf-8 -*-
"""宍粟市の指定文化財の一覧を作る

どこから：
  市の『宍粟市文化財保存活用地域計画』資料編のPDF（令和7年8月現在）。
  国・県・市の指定文化財が、名称・員数・地域・所有者・指定年月日・類型の表で載っている。

なぜ：
  市のサイトの「宍粟市の文化財」ページには8件しか載っておらず、
  「◯◯神社の文化財は」「波賀町の文化財を教えて」に答えられなかった。

★表は列の位置（x座標）で分ける。文字の並び順だけで読むと、
  名称の欄に員数や類型が混ざる（ごみの分別表で同じ失敗をしている）。
"""
import json, pathlib, re, subprocess, ssl, sys, urllib.request
import certifi

根 = pathlib.Path(__file__).resolve().parent.parent
元 = "https://www.city.shiso.lg.jp/material/files/group/75/siryouhenn.pdf"
道具 = pathlib.Path("/tmp/shiso_pdfwords")

def 道具を用意():
    元s = 根 / "scripts" / "pdfwords.swift"
    if (not 道具.exists()) or 道具.stat().st_mtime < 元s.stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(元s), "-o", str(道具)], check=True)

def 取る(url):
    c = ssl.create_default_context(cafile=certifi.where())
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(r, timeout=240, context=c).read()

def 語を読む(pdf, 頁):
    r = subprocess.run([str(道具), str(pdf), str(頁)], capture_output=True, timeout=120)
    出 = []
    for l in r.stdout.decode("utf-8", "replace").split("\n"):
        c = l.split("\t")
        if len(c) < 3: continue
        try: 出.append((c[0], float(c[1]), float(c[2])))
        except ValueError: pass
    return 出

# 表の列の境目。★実測した見出しの位置から決める（2026-08-28）：
#   名称116／員数等193／地域240／所有者等276／指定登録年月日338／類型460
#   中身は見出しより少し左から始まる（名称72・員数181・地域235・所有者265・年月日326・類型416）
def 欄(x):
    if x < 178: return "名称"
    if x < 232: return "員数"
    if x < 262: return "地域"
    if x < 320: return "所有者"
    if x < 410: return "指定年月日"
    return "類型"

def 表を読む(pdf, 頁ら):
    出 = []
    区分 = ""
    for 頁 in 頁ら:
        語 = 語を読む(pdf, 頁)
        if not 語: continue
        # ★同じ行はy座標がぴったり同じ（実測）。丸めると別の行が混ざる。
        #   丸めていたせいで、名称の欄に次の件の名称までつながっていた
        行ら = {}
        for w, x, y in 語:
            行ら.setdefault(y, []).append((w, x, y))
        for 鍵 in sorted(行ら):
            並 = sorted(行ら[鍵], key=lambda t: t[1])
            文 = "".join(w for w, _, _ in 並)
            m = re.search(r"■(国|県|市)指定文化財", 文)
            if m: 区分 = m.group(1) + "指定"; continue
            if not 区分: continue
            if "名称" in 文 and "員数" in 文: continue        # 見出しの行
            一 = {"名称": "", "員数": "", "地域": "", "所有者": "",
                  "指定年月日": "", "類型": ""}
            for w, x, y in 並:
                一[欄(x)] += w
            # ★名称が空の行をここで捨ててはいけない（2026-08-28の失敗）。
            #   所有者が2行に折り返した件（池王神社・／深河谷自治会 昭和61年3月25日）は、
            #   指定年月日が「名称の空いた次の行」に入っている。
            #   捨てていたせいで、23件の指定年月日が読めなかった。
            #   つなぐ() に渡して、そこで前の件に足す
            if not any(一[k] for k in 一): continue
            一["区分"] = 区分
            一["y"] = 並[0][2] + 頁 * 10000    # ★頁をまたいで混ざらないように離す
            出.append(一)
    return 出

def つなぐ(行ら):
    """PDFの表は1件が複数行に割れる。
       ★行の順番で足してはいけない（2026-08-28の実測）。
         「山崎町町方文書」は、所有者が3行に折り返した都合で
         指定年月日（y=214）が名称（y=218）より**先**に描かれていた。
         順番で足すと、その年月日が前の件のものになる。
       ★『名称のある行』を軸にして、各行をいちばん近い軸に配る。
         軸から15pxより離れた行は、どの件にも属さない（表の外）"""
    # ★軸は「地域の欄に町名がある行」。名称だけの行を軸にすると、
    #   名称が2行に折り返した件（安養寺木造阿弥陀如来立／像及び両脇侍像）が
    #   2件に割れる（2026-08-28の実測）
    町ら = ("山崎町", "一宮町", "波賀町", "千種町", "地域を")
    軸 = [(i, r["y"]) for i, r in enumerate(行ら)
          if any(t in r["地域"] for t in 町ら)]
    if not 軸: return []
    出 = {i: dict(行ら[i]) for i, _ in 軸}
    for j, r in enumerate(行ら):
        if any(j == i for i, _ in 軸): continue
        近, 差 = None, 1e9
        for i, y in 軸:
            d = abs(r["y"] - y)
            if d < 差: 近, 差 = i, d
        if 近 is None or 差 > 15: continue
        # ★名称の続きは前に付ける（「安養寺木造阿弥陀如来立」＋「像及び両脇侍像」）。
        #   軸より上の行が名称の1行目なので、順番を守る
        if r["名称"].strip():
            出[近]["名称"] = (r["名称"] + 出[近]["名称"]) if r["y"] < 行ら[近]["y"] \
                             else (出[近]["名称"] + r["名称"])
        for k in ("員数", "地域", "所有者", "指定年月日", "類型"):
            出[近][k] = (出[近][k] + r[k]).strip()
    return [出[i] for i, _ in 軸]

def 整える(r):
    r.pop("y", None)
    for k in list(r):
        r[k] = re.sub(r"\s+", "", r[k]).replace("　", "")
    # 資-1 のようなページ番号を落とす
    r["類型"] = re.sub(r"資-\d+", "", r["類型"])
    r["名称"] = re.sub(r"資-\d+", "", r["名称"])
    return r

def 主():
    道具を用意()
    仮 = 根 / "scripts" / "_bunkazai.pdf"
    仮.write_bytes(取る(元))
    行ら = 表を読む(仮, range(3, 9))
    仮.unlink()
    件 = [整える(r) for r in つなぐ(行ら)]
    # ★文化財の行だけを残す（2026-08-28）。資料編には表のあとにアンケートの
    #   説明文が続いており、それも1行1件として拾ってしまっていた。
    #   ★「町が入っている」か「地域を定めず」（国指定のオオサンショウウオ）を条件にする
    町ら = ("山崎町", "一宮町", "波賀町", "千種町", "地域を定めず")
    件 = [r for r in 件 if len(r["名称"]) >= 3 and any(t in r["地域"] for t in 町ら)]
    # ★同じ名称が二重に入っていないか
    見 = set(); 出 = []
    for r in 件:
        鍵 = (r["区分"], r["名称"])
        if 鍵 in 見: continue
        見.add(鍵); 出.append(r)
    if not 出:
        print("！ 文化財が1件も読めなかった。PDFの作りが変わった可能性"); return 1
    from collections import Counter
    c = Counter(r["区分"] for r in 出)
    c2 = Counter(r["地域"] for r in 出)
    先 = 根 / "shiso_bunkazai.json"
    先.write_text(json.dumps({
        "作成": "宍粟市文化財保存活用地域計画 資料編（令和7年8月現在）より",
        "url": 元, "件数": len(出), "項目": 出}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"○ {len(出)}件 → {先}（{先.stat().st_size // 1024}KB）")
    print("  区分:", dict(c))
    print("  地域:", dict(c2))
    print("\n  例:")
    for r in 出[:6]:
        print(f"   {r['区分']} {r['名称'][:26]:28s} {r['地域']:6s} {r['所有者'][:14]:16s} {r['指定年月日']}")
    # ★検算：年月日が入っていない件がどれだけあるか
    無 = [r["名称"] for r in 出 if not re.search(r"\d+年\d+月\d+日", r["指定年月日"])]
    print(f"\n検算: 指定年月日が読めた {len(出)-len(無)}／{len(出)}件")
    if 無: print("  読めなかった:", 無[:6])
    return 0

if __name__ == "__main__":
    sys.exit(主())
