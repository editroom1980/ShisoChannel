# -*- coding: utf-8 -*-
"""宍粟市の予算・決算を広報から拾う

なぜ作るか：
  「宍粟市の予算はいくらですか」に「お調べできませんでした」と答えていた（2026-08-28の実測）。
  市の公式ページは中身がPDFで、本文に金額が1つも書かれていない。
  ところが広報しそうは毎年4月号に当初予算、11月号に決算を数字つきで載せている。

★数字の書き方が年で違う（「253.9億円」「253億9000万円」「234 億 7000 万円」）。
  ぜんぶ万円の整数に直してから保存する。直せない書き方が出たら知らせる。
"""
import json, re, pathlib, sys

根 = pathlib.Path(__file__).resolve().parent.parent

def 半角(t):
    return (t.translate(str.maketrans("０１２３４５６７８９．，", "0123456789.,"))
             .replace(",", "").replace(" ", "").replace("　", "")
             .replace("\n", "").replace("（", "(").replace("）", ")"))

def 万円に(億, 万):
    """「253.9億」＋「なし」→ 2539000万円。「253億」＋「9000万」→ 2539000万円"""
    n = float(億) * 10000
    if 万: n += float(万)
    return int(round(n))

def 見やすく(万):
    億 = 万 // 10000
    残 = 万 % 10000
    return f"{億}億円" if 残 == 0 else f"{億}億{残}万円"

def 主():
    項 = []
    for f in ("shiso_koho.json", "shiso_koho_kako.json"):
        d = json.loads((根 / f).read_text(encoding="utf-8"))
        項 += d["項目"]
    予算, 決算, 地方債 = {}, {}, {}
    直せない = []
    for x in 項:
        号 = x.get("号", "")
        年 = int(号[:4]) if 号[:4].isdigit() else None
        f = 半角(x.get("文", ""))
        # ── 当初予算（4月号）
        # ★年で書き方が違う（実測）：
        #   「一般会計予算は231億8000万円」／「一般会計予算は、231億3000万円で」
        #   「一般会計予算\n227.3億円」／平成30年度だけ「一般会計歳入…歳入239億4000万円」
        for m in re.finditer(r"一般会計予算は?[、,]?([\d.]+)億(?:(\d+)万)?円", f):
            g = re.search(r"(令和|平成)(\d+|元)年度", f[max(0, m.start() - 200):m.start()])
            年度 = None
            if g:
                元 = 1 if g.group(2) == "元" else int(g.group(2))
                年度 = (1988 + 元) if g.group(1) == "平成" else (2018 + 元)
            elif 年: 年度 = 年          # 4月号は当年度
            if 年度:
                予算[年度] = {"一般会計": 万円に(m.group(1), m.group(2)), "出典": 号}
        # 平成30年度の書き方（表の見出しだけで「予算」の語が無い）
        if 年 and 年 not in 予算 and "一般会計歳入" in f:
            m2 = re.search(r"歳入(\d{3})億(\d+)万円", f)
            if m2:
                g = re.search(r"(令和|平成)(\d+|元)年度当初予算", f)
                年度 = 年
                if g:
                    元 = 1 if g.group(2) == "元" else int(g.group(2))
                    年度 = (1988 + 元) if g.group(1) == "平成" else (2018 + 元)
                予算[年度] = {"一般会計": 万円に(m2.group(1), m2.group(2)), "出典": 号}

        # ── 決算（11月号）
        m = re.search(r"歳出\)?は(\d+)億(\d+)万円.{0,40}?歳入\)?は(\d+)億(\d+)万円", f)
        if m and 年:
            g = re.search(r"(令和|平成)(\d+|元)年度の市の一般会計", f)
            年度 = 年 - 1
            if g:
                元 = 1 if g.group(2) == "元" else int(g.group(2))
                年度 = (1988 + 元) if g.group(1) == "平成" else (2018 + 元)
            決算[年度] = {"歳出": 万円に(m.group(1), m.group(2)),
                          "歳入": 万円に(m.group(3), m.group(4)), "出典": 号}
        # ── 地方債残高
        m = re.search(r"地方債の残高は[、]?一般会計で(\d+)億(\d+)万円", f)
        if m and 年:
            地方債[年] = {"一般会計": 万円に(m.group(1), m.group(2)), "出典": 号}
    if not 予算:
        print("！ 予算の記述が1件も無い。広報の資料を作り直すこと"); return 1
    新 = max(予算)
    出 = {
        "作成": "広報しそう（毎年4月号の当初予算・11月号の決算）より",
        "最新の年度": 新,
        "予算": {str(k): v for k, v in sorted(予算.items())},
        "決算": {str(k): v for k, v in sorted(決算.items())},
        "地方債残高": {str(k): v for k, v in sorted(地方債.items())},
        "まとめ": {
            "今年度": 新,
            "一般会計": 予算[新]["一般会計"],
            "言い方": 見やすく(予算[新]["一般会計"]),
            "出典": 予算[新]["出典"],
        },
    }
    先 = 根 / "shiso_yosan.json"
    先.write_text(json.dumps(出, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"○ 予算 {len(予算)}年度・決算 {len(決算)}年度・地方債 {len(地方債)}年 → {先}")
    print("\n【当初予算（一般会計）】")
    for k in sorted(予算): print(f"  {k}年度  {見やすく(予算[k]['一般会計']):>12s}  （{予算[k]['出典']}）")
    print("【決算】")
    for k in sorted(決算):
        v = 決算[k]
        print(f"  {k}年度  歳入 {見やすく(v['歳入']):>12s}  歳出 {見やすく(v['歳出']):>12s}")
    print("【地方債残高（一般会計）】")
    for k in sorted(地方債): print(f"  {k}年  {見やすく(地方債[k]['一般会計']):>12s}")
    # ★検算：金額が筋の通る幅に入っているか（桁の取り違えを見つける）
    変 = [k for k, v in 予算.items() if not (1000000 <= v["一般会計"] <= 5000000)]
    if 変: print(f"！ 金額が筋に合わない年度: {変}（100億〜500億の外）")
    return 0

if __name__ == "__main__":
    sys.exit(主())
