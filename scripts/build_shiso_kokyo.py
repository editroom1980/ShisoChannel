# -*- coding: utf-8 -*-
"""宍粟市の公共施設（開館時間・休館日・住所・電話・バリアフリー）

なぜ：
  「図書館は何時までですか」「体育館は月曜も開いていますか」に答えられなかった。
  市の施設一覧（shiso_shisetsu.json）は学校とこども園が中心で、
  文化・運動・福祉の施設が入っていない。

どこから：
  市の『公共施設のバリアフリー情報』（21施設）。
  障がい福祉課が実際に車いすの人と回って調べた資料で、
  開館時間・休館日・住所・電話に加えて、設備の有無まで載っている。

★車いす対応やおむつ交換台の有無は、必要な人には決定的な情報。書いてある通りに写す。
"""
import json, pathlib, re, sys

根 = pathlib.Path(__file__).resolve().parent.parent

def 拾う設備(文):
    """『◯◯あり』『◯◯なし』の形で書かれている設備を全部拾う"""
    出 = {}
    for m in re.finditer(r"([一-鿿ぁ-んァ-ヶA-Za-z0-9・（）()]{3,22}?)(あり|なし)(?![^\s])", 文):
        名 = m.group(1).strip()
        if len(名) < 3 or "情報" in 名 or "場合" in 名: continue
        出[名] = (m.group(2) == "あり")
    return 出

def 主():
    kb = json.loads((根 / "shiso_kb.json").read_text(encoding="utf-8"))["項目"]
    出 = []
    for x in kb:
        題 = x.get("題", "")
        if not 題.endswith("のバリアフリー情報"): continue
        名 = 題[:-len("のバリアフリー情報")]
        if 名 in ("宍粟市公共施設", "バリアフリー情報の公表制度"): continue
        文 = re.sub(r"\s+", " ", x.get("文", ""))
        一 = {"名": 名, "url": x.get("url", ""), "課": x.get("課", "")}
        # 開館時間・休館日・住所・電話（複数の施設が1ページにある場合は最初のもの）
        for 鍵, 型 in (("開館時間", r"開館時間[：: ]\s*([^休住電]{4,60})"),
                       ("休館日", r"休館日[：: ]\s*([^開住電]{2,50})"),
                       ("住所", r"住所[：: ]\s*(宍粟市[^\s電話フ]{2,30})"),
                       ("電話", r"電話[：: ]\s*(0\d{1,4}-\d{2,4}-\d{3,4})")):
            m = re.search(型, 文)
            if m: 一[鍵] = m.group(1).strip("、 ・")
        設 = 拾う設備(文)
        # 使う人がいちばん知りたい設備だけを選ぶ
        大事 = {}
        for k in ("車いす用の駐車区画", "スロープ", "自動ドア", "車いす対応トイレ",
                  "オストメイト対応トイレ", "おむつ交換台", "授乳室", "エレベーター",
                  "車いす対応エレベーター", "視覚障害者用誘導ブロック（点字ブロック）",
                  "手話対応", "筆談対応"):
            if k in 設: 大事[k] = 設[k]
        if 大事: 一["設備"] = 大事
        # 何の施設か（記事のパンくずに「文化・運動施設」等がある）
        m = re.search(r"施設別でさがす\s*([^\s]{2,12})", 文)
        if m: 一["種類"] = m.group(1)
        出.append(一)
    if not 出:
        print("！ 公共施設が1件も無い"); return 1
    先 = 根 / "shiso_kokyo.json"
    先.write_text(json.dumps({
        "作成": "市公式『公共施設のバリアフリー情報』より",
        "注意": "施設情報は調査時点のもの。利用の前に各施設へお確かめください（市の但し書き）",
        "件数": len(出), "項目": sorted(出, key=lambda x: x["名"])},
        ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(f"○ 公共施設 {len(出)}件 → {先}（{先.stat().st_size//1024}KB）")
    print("  種類:", dict(Counter(x.get("種類", "（不明）") for x in 出)))
    for 鍵 in ("開館時間", "休館日", "住所", "電話", "設備"):
        n = sum(1 for x in 出 if 鍵 in x)
        print(f"  {鍵}が読めた {n}／{len(出)}件")
    print("\n  例:")
    for x in 出[:6]:
        print(f"   {x['名'][:26]:28s} {x.get('電話','')} {x.get('開館時間','')[:26]}")
    無 = [x["名"] for x in 出 if "電話" not in x]
    if 無: print(f"\n  電話が読めなかった: {無[:5]}")
    return 0

if __name__ == "__main__":
    sys.exit(主())
