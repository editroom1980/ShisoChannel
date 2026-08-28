# -*- coding: utf-8 -*-
"""宍粟市への行き方（市外から来る人向け）

なぜ：
  10月に市外の関係者へ見せる。「宍粟市へはどう行けばいいですか」に
  答えられないのは弱い。市民も「三宮からのバスは」と聞く。

どこから：
  市の記事に書いてある行き方の記述だけを集める。★所要時間や乗り場は
  こちらで作らず、書いてある通りに写す。
"""
import json, pathlib, re, sys

根 = pathlib.Path(__file__).resolve().parent.parent

def 主():
    kb = json.loads((根 / "shiso_kb.json").read_text(encoding="utf-8"))["項目"]
    出 = {"作成": "市公式サイトの記事に書かれた行き方の記述より", "経路": [], "駐車場": []}

    # ① 交通アクセスのページ（いちばん確かな記述）
    for x in kb:
        if x.get("題", "") != "交通アクセス": continue
        f = re.sub(r"\s+", "", x.get("文", ""))
        for m in re.finditer(r"(JR[^〈]{0,10}駅から)〈([^〉]+)〉([^JR]{6,120})", f):
            道 = m.group(3)
            # ★病院までの徒歩やアクセスマップの案内は、市への行き方ではない
            #   （2026-08-28の実測：「徒歩5分」を拾って「およそ5分です」と答えた）
            道 = re.split(r"山崎バスターミナルから病院|アクセスマップ|大きな地図", 道)[0]
            # ★バスの所要時間だけを取り出す（「4乗場」の数字と混ざらないように）
            分ら = [int(t) for t in re.findall(r"行\s*(\d+)\s*分", 道)]
            一 = {
                "どこから": m.group(1).replace("から", ""),
                "手段": m.group(2),
                "行き方": 道[:120],
                "url": x.get("url", ""),
            }
            if 分ら: 一["いちばん短い分"] = min(分ら)
            出["経路"].append(一)
        m = re.search(r"自動車をご利用の場合(.{10,200}?)公共交通", f)
        if m:
            出["車"] = {"行き方": m.group(1)[:200], "url": x.get("url", "")}
        break

    # ② パークアンドライド駐車場（高速バスに乗る人向け）
    for x in kb:
        if "パークアンドライド" not in x.get("題", ""): continue
        f = re.sub(r"\s+", "", x.get("文", ""))
        for m in re.finditer(r"([^。０-９\d]{4,20}(?:駐車場|駐輪場))概要?"
                             r"駐車料金([^利]{1,10})利用可能時間([^最]{1,12})"
                             r"最寄りのバス停([^場]{2,20})場所(宍粟市[^利]{4,30})", f):
            出["駐車場"].append({
                "名": m.group(1), "料金": m.group(2), "時間": m.group(3),
                "最寄りの停": m.group(4), "場所": m.group(5), "url": x.get("url", ""),
            })
        m = re.search(r"予約不要で(\d+)台", f)
        if m and 出["駐車場"]: 出["駐車場"][0]["台数"] = int(m.group(1))
        break

    if not 出["経路"] and "車" not in 出:
        print("！ 行き方の記述が1件も無い"); return 1
    先 = 根 / "shiso_access.json"
    先.write_text(json.dumps(出, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"○ 行き方 → {先}（{先.stat().st_size//1024}KB）")
    for r in 出["経路"]:
        print(f"  {r['どこから']}（{r['手段']}）… {r['行き方'][:70]}")
    if "車" in 出: print(f"  車 … {出['車']['行き方'][:80]}")
    for p in 出["駐車場"]:
        print(f"  駐車場 {p['名']} 料金{p['料金']} {p.get('台数','?')}台 {p['場所'][:24]}")
    # ★検算：高速バスと路線バスの両方が取れているか
    手 = {r["手段"] for r in 出["経路"]}
    print(f"検算: 手段 {手}")
    if not any("高速" in t for t in 手): print("！ 高速バスの記述が取れていない")
    return 0

if __name__ == "__main__":
    sys.exit(主())
