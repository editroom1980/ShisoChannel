# -*- coding: utf-8 -*-
"""宍粟市の学校・園の一覧（今ある学校と、閉校・閉園した学校）

なぜ：
  「閉校になった小学校を教えて」に答えられなかった（今ある9校の電話一覧を返していた）。
  お年寄りは「私の母校はどうなった」と聞く。合併・統廃合が進んだ市では大事な問い。

どこから：
  市の『心のふるさと校歌保存事業（校歌・園歌）』。
  昭和30年以降に閉校・閉園した学校園も含めて、校歌を復元・保存している。
  ここに載っている学校名を全部拾い、いま実在する学校（shiso_shisetsu.json）と
  突き合わせて「閉校したもの」を出す。

★閉校の年は書かれていないので、こちらで作らない。「閉校・閉園した」とだけ言う。
"""
import json, pathlib, re, sys

根 = pathlib.Path(__file__).resolve().parent.parent

def 主():
    kb = json.loads((根 / "shiso_kb.json").read_text(encoding="utf-8"))["項目"]
    元 = [x for x in kb if "校歌保存事業" in x.get("題", "")]
    if not 元:
        print("！ 校歌保存事業の記事が無い。shiso_kb.json を作り直すこと"); return 1
    文 = 元[0].get("文", "")
    url = 元[0].get("url", "")
    # 学校・園の名前を拾う（「◯◯小学校 メロディ譜面」の形で必ず出てくる）
    名ら = []
    for m in re.finditer(r"([一-鿿ぁ-んァ-ヶA-Za-z]{2,12}(?:小学校|中学校|幼稚園|こども園|中学|小学))"
                         r"\s*(?:メロディ譜面|ホームページ|音源|園歌|校歌)", 文):
        t = m.group(1)
        if t not in 名ら: 名ら.append(t)
    if not 名ら:
        print("！ 学校名が1つも拾えなかった。記事の作りが変わった可能性"); return 1

    # いま実在する学校（市の施設一覧より）
    施 = json.loads((根 / "shiso_shisetsu.json").read_text(encoding="utf-8"))
    施 = 施.get("項目", 施)
    今 = {}
    for x in 施:
        種 = x.get("種類", "")
        if 種 in ("小学校", "中学校", "幼稚園", "こども園", "保育所", "高校"):
            名 = x.get("名", "").replace("市立", "").replace("県立", "").strip()
            今[名] = {"名": 名, "種類": 種, "地区": x.get("地区", ""),
                      "電話": x.get("電話", ""), "url": x.get("url", "")}

    閉 = []
    for 名 in 名ら:
        if 名 in 今: continue
        # 「はりま一宮小学校」のように今の名前に含まれる場合も実在とみなす
        if any(名 in k or k in 名 for k in 今): continue
        種 = ("中学校" if "中学" in 名 else
              "幼稚園" if "幼稚園" in 名 else
              "こども園" if "こども園" in 名 else "小学校")
        一 = {"名": 名, "種類": 種}
        # ★閉校のあと何に使われているかを市の資料から拾う（2026-08-28）。
        #   旧校舎は指定避難所になっていることが多い（旧市立戸原小学校など）。
        #   「私の母校はどうなった」に答えられる
        for y in kb:
            題 = y.get("題", "")
            # ★名前がまるごと入っているときだけ結びつける（2026-08-28の失敗）。
            #   「三方」で探すと「旧市立下三方小学校」に当たり、
            #   別の学校を「三方小学校のいま」として書いてしまう
            if 題.startswith("旧市立") and ("旧市立" + 名) == 題.split("（")[0].strip():
                一["いま"] = 題
                住 = re.search(r"兵庫県宍粟市[^\s]{2,24}", y.get("文", ""))
                if 住: 一["住所"] = 住.group(0)
                if "指定避難所" in y.get("文", ""): 一["指定避難所"] = True
                収 = re.search(r"収容人員\s*([\d,]+)人", y.get("文", ""))
                if 収: 一["収容人員"] = int(収.group(1).replace(",", ""))
                break
        閉.append(一)

    出 = {
        "作成": "市公式『心のふるさと校歌保存事業（校歌・園歌）』と施設一覧より",
        "url": url,
        "注意": "閉校・閉園の年は市の資料に書かれていないため持っていない",
        "今ある学校": sorted(今.values(), key=lambda x: (x["種類"], x["名"])),
        "閉校・閉園した学校園": sorted(閉, key=lambda x: (x["種類"], x["名"])),
    }
    先 = 根 / "shiso_gakko.json"
    先.write_text(json.dumps(出, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    c1 = Counter(x["種類"] for x in 出["今ある学校"])
    c2 = Counter(x["種類"] for x in 出["閉校・閉園した学校園"])
    print(f"○ 今ある {len(今)}校／閉校・閉園 {len(閉)}校 → {先}（{先.stat().st_size//1024}KB）")
    print("  今ある:", dict(c1))
    print("  閉校・閉園:", dict(c2))
    print(f"\n検算: 校歌の記事から拾った学校名 {len(名ら)}件"
          f" ＝ 今ある {len(名ら)-len(閉)}件 ＋ 閉校 {len(閉)}件")
    print("\n  閉校・閉園した小学校:")
    for x in 出["閉校・閉園した学校園"]:
        if x["種類"] == "小学校": print("   ", x["名"])
    return 0

if __name__ == "__main__":
    sys.exit(主())
