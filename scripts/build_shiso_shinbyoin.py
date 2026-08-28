# -*- coding: utf-8 -*-
"""新病院（公立宍粟総合病院の移転新築）の要点

なぜ：
  「新病院はいつ開院しますか」に、AIが古い記事から「令和8年」と答えた（2026-08-28の実測）。
  実際は1年延びて「令和10年3月」。市の一大事業なので、誤った日付を言うのは重い。

★開院時期は、市の資料に書かれた記述を**新しい順に**集めて、
  いちばん新しいものを採る。こちらで日付を決め打ちしない。
"""
import json, pathlib, re, sys
from collections import Counter

根 = pathlib.Path(__file__).resolve().parent.parent

def 更新日(文):
    m = re.search(r"更新日：(\d{4})年(\d{2})月(\d{2})日", 文)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""

def 主():
    kb = json.loads((根 / "shiso_kb.json").read_text(encoding="utf-8"))["項目"]
    記述 = []
    for x in kb:
        f = x.get("文", "")
        if "新病院" not in f and "総合病院" not in f: continue
        日 = 更新日(f)
        for m in re.finditer(r"[^。\n]{0,70}開院[^。\n]{0,70}。", f):
            t = re.sub(r"\s+", "", m.group(0))
            g = re.search(r"(令和\d+年\d+月|令和\d+年度末頃|令和\d+年度末|令和\d+年)", t)
            if not g: continue
            # ★「〜でしたが」「前提に」は過去の予定の話なので、時期の根拠にしない
            過去 = any(k in t for k in ("でしたが", "前提", "当初", "策定しており"))
            記述.append({"日": 日, "題": x.get("題", ""), "時期": g.group(1),
                         "文": t[:160], "過去の話": 過去, "url": x.get("url", "")})
    if not 記述:
        print("！ 開院に触れる記述が1件も無い"); return 1
    記述.sort(key=lambda r: r["日"], reverse=True)
    生きている = [r for r in 記述 if not r["過去の話"]]
    if not 生きている:
        print("！ 今の予定と読める記述が無い"); return 1
    # ★いちばん新しい記述の時期を採り、同じ時期を言う記述が何件あるかも数える
    時期 = 生きている[0]["時期"]
    c = Counter(r["時期"] for r in 生きている)
    出 = {
        "作成": "市公式サイトの記事から、開院時期の記述を新しい順に集めた",
        "開院の時期": 時期,
        "根拠": [{"日": r["日"], "題": r["題"], "文": r["文"], "url": r["url"]}
                 for r in 生きている[:5]],
        "時期の言われ方": dict(c),
        "延期": [r for r in 記述 if r["過去の話"]][:2],
    }
    # 建設の進み具合（工事進捗のページ）
    for x in kb:
        if "工事進捗状況" in x.get("題", "") and "新病院" in x.get("題", ""):
            m = re.search(r"工事進捗状況（(令和\d+年\d+月末?時点)）\s*(.{0,200})", x["文"])
            if m:
                出["工事の進み"] = {"時点": m.group(1),
                                    "様子": re.sub(r"\s+", "", m.group(2))[:180],
                                    "url": x.get("url", "")}
            break
    # ★場所は「新病院建設地」と書いてある所から取る（2026-08-28）。
    #   実測：「7月8日、山崎町中比地の新病院建設地で『新病院起工式』が…」
    #   ★こちらで地名を決め打ちしない
    for x in kb:
        m = re.search(r"(山崎町[一-鿿ぁ-んァ-ヶ]{1,8}|一宮町[一-鿿ぁ-んァ-ヶ]{1,8}"
                      r"|波賀町[一-鿿ぁ-んァ-ヶ]{1,8}|千種町[一-鿿ぁ-んァ-ヶ]{1,8})"
                      r"の新病院建設地", x.get("文", ""))
        if m:
            出["場所"] = m.group(1)
            出["場所の根拠"] = re.sub(r"\s+", "", x["文"][max(0, m.start()-30):m.end()+60])
            break
    先 = 根 / "shiso_shinbyoin.json"
    先.write_text(json.dumps(出, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"○ 新病院の要点 → {先}（{先.stat().st_size//1024}KB）")
    print(f"  開院の時期: {時期}")
    print(f"  時期の言われ方: {dict(c)}")
    print(f"  根拠（新しい順）:")
    for r in 生きている[:4]: print(f"    [{r['日']}] {r['題'][:26]} … {r['文'][:70]}")
    if "工事の進み" in 出:
        print(f"  工事: {出['工事の進み']['時点']} … {出['工事の進み']['様子'][:60]}")
    if 出["延期"]:
        print(f"  延期の記述: {出['延期'][0]['文'][:80]}")
    # ★検算：いちばん多い言われ方と、いちばん新しい記述が食い違わないか
    多 = c.most_common(1)[0][0]
    if 多 != 時期:
        print(f"！ いちばん新しい記述『{時期}』と、いちばん多い言われ方『{多}』が違う。要確認")
    else:
        print(f"  検算: 新しい記述と多数の言われ方が一致（{時期}／{c[時期]}件）")
    return 0

if __name__ == "__main__":
    sys.exit(主())
