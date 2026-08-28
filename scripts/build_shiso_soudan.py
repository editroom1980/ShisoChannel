# -*- coding: utf-8 -*-
"""宍粟市の相談窓口の一覧

なぜ：
  困った時にどこへ電話すればいいか、が市民のいちばんの関心。
  市の記事は31件あるが、ばらばらに置かれていて
  「相談したいのですが」「こころの相談はどこ」に一覧で答えられなかった。

★電話番号は記事に書いてある番号だけを使う。書いていなければ載せない。
"""
import json, pathlib, re, sys
from collections import Counter

根 = pathlib.Path(__file__).resolve().parent.parent

# 悩みの種類（市民が言う言葉で分ける）
分け = [
    ("こころ・いのち", r"こころ|心の|自殺|いのち|依存症|ギャンブル"),
    ("子育て・家庭", r"子育て|児童|母子|父子|ひとり親|家庭児童|乳幼児|DV|妊娠"),
    ("福祉・障がい", r"福祉|障害|障がい|基幹相談|生活困窮|生活保護"),
    ("高齢・介護", r"高齢|介護|地域包括|認知症"),
    ("人権・女性", r"人権|女性|男性|にじいろ|性的|いじめ|差別"),
    ("しごと・お金", r"仕事|就労|就職|경영|経営|消費生活|多重債務|お金|創業"),
    ("法律・その他", r"法テラス|法律|弁護士|行政"),
    ("健康・医療", r"健康|健診|救急|医療|病気"),
]

def 悩み(題, 文):
    t = 題
    if not any(re.search(型, t) for _, 型 in 分け):
        t = 題 + " " + 文[:200]
    出 = [名 for 名, 型 in 分け if re.search(型, t)]
    return 出 or ["そのほか"]

def 社協の窓口(出):
    """社会福祉協議会の支部（2026-08-28）。
       ★ひとり暮らしの高齢者を支える配食・見守り・ボランティアは、
         市ではなく社協がやっている。市の記事だけでは永久に届かない"""
    f = 根 / "shiso_syakyo.json"
    if not f.exists(): return
    d = json.loads(f.read_text(encoding="utf-8"))
    文 = " ".join(x.get("文", "") for x in d.get("項目", d))
    支 = {}
    for m in re.finditer(r"(本部[一-鿿ぁ-ん]{0,4}|山崎支部|一宮支部|波賀支部|千種支部)"
                         r"[：: ]?\s*(0790-\d{2}-\d{4})", 文):
        名 = m.group(1).replace("本部一宮", "一宮支部")
        # ★同じ番号が「本部一宮」と「一宮支部」の2通りで書かれている（実測）。
        #   番号で見て、同じものを二重に持たない
        if m.group(2) in 支.values(): continue
        支.setdefault(名, m.group(2))
    if not 支: return
    出.append({
        "題": "宍粟市社会福祉協議会（配食・見守り・ボランティア）",
        "url": "https://www.shiso-wel.or.jp/",
        "課": "宍粟市社会福祉協議会",
        "悩み": ["福祉・障がい", "高齢・介護"],
        "電話": list(支.values())[:4],
        "支部": 支,
        "時間の記述": "支部ごとに受付。まずはお近くの支部へお電話ください",
    })

def 主():
    kb = json.loads((根 / "shiso_kb.json").read_text(encoding="utf-8"))["項目"]
    出 = []
    # ★題に「相談」が無くても、相談を受ける窓口がある（2026-08-28の実測：
    #   「地域包括支援センター」は高齢者の総合相談の窓口なのに拾えていなかった）
    窓口の名 = ("地域包括支援センター", "家庭児童相談室", "基幹相談支援センター",
                "子育て支援センター", "消費生活センター", "ボランティア・市民活動センター")
    for x in kb:
        題 = x.get("題", "")
        if "相談" not in 題 and not any(n == 題 for n in 窓口の名): continue
        # 相談の案内でないもの（実施結果・要綱など）は除く
        if re.search(r"実施結果|パブリックコメント|議案|条例|規則|審査|委員会", 題): continue
        文 = x.get("文", "")
        if len(文) < 120: continue
        一 = {"題": 題, "url": x.get("url", ""), "課": x.get("課", ""),
              "悩み": 悩み(題, 文)}
        電 = x.get("電話")
        if 電: 一["電話"] = [電] if isinstance(電, str) else 電[:3]
        # ★記事の本文に書かれた電話（0790-…、フリーダイヤル、#で始まる番号）も拾う
        番 = re.findall(r"(?:0\d{1,4}-\d{2,4}-\d{3,4}|0120-?\d{2,3}-?\d{3,4}|#\d{4})", 文)
        if 番:
            見 = 一.get("電話", [])
            for b in 番:
                if b not in 見 and len(見) < 4: 見.append(b)
            一["電話"] = 見
        # 受付の時間
        m = re.search(r"[^。\n]{0,20}(?:受付|受け付け|時間|開設)[^。\n]{0,50}", 文)
        if m: 一["時間の記述"] = re.sub(r"\s+", "", m.group(0))[:90]
        出.append(一)
    社協の窓口(出)
    if not 出:
        print("！ 相談の記事が1件も無い"); return 1
    c = Counter(s for x in 出 for s in x["悩み"])
    電あり = [x for x in 出 if x.get("電話")]
    先 = 根 / "shiso_soudan.json"
    先.write_text(json.dumps({
        "作成": "市公式サイトの記事から、相談窓口の案内だけを集めた",
        "件数": len(出), "項目": sorted(出, key=lambda x: x["題"])},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"○ 相談窓口 {len(出)}件 → {先}（{先.stat().st_size//1024}KB）")
    print("  悩みごと:", dict(c.most_common()))
    print(f"  電話が分かる {len(電あり)}／{len(出)}件")
    print("\n  例:")
    for x in 出[:8]:
        print(f"   {x['題'][:30]:32s} {'/'.join(x.get('電話', []))[:34]}")
    無 = [x["題"] for x in 出 if not x.get("電話")]
    if 無: print(f"\n  電話が読めなかった {len(無)}件: {無[:5]}")
    return 0

if __name__ == "__main__":
    sys.exit(主())
