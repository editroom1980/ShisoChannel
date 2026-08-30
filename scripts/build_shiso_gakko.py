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
import json, pathlib, re, subprocess, sys

根 = pathlib.Path(__file__).resolve().parent.parent

def 市の学校一覧():
    """市の『小・中学校』一覧ページから、いま実在する学校を取る（2026-08-30に新設）。

    ★施設一覧（shiso_shisetsu.json）だけを「いま実在する学校」の根拠にしていたため、
      そこから漏れた学校が閉校に化けていた。**独立した2つ目の情報源**を持つ。
    """
    出 = {}
    for u, 種 in [("https://www.city.shiso.lg.jp/shisetsu/syoutyuugakkou/index.html", None),
                  ("https://www.city.shiso.lg.jp/shisetsu/hoikusyo/index.html", "保育所"),
                  ("https://www.city.shiso.lg.jp/shisetsu/ninteikodomoen/index.html", "こども園"),
                  ("https://www.city.shiso.lg.jp/shisetsu/youtien/index.html", "幼稚園")]:
        try:
            r = subprocess.run(["curl", "-sL", "--max-time", "40", "-A",
                                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", u],
                               capture_output=True)
            h = r.stdout.decode("utf-8", "replace")
        except Exception as e:
            print(f"！ 市の学校一覧が取れない {u}: {e}", file=sys.stderr); continue
        for m in re.finditer(r'<a[^>]+href="[^"]*"[^>]*>([^<]*(?:小学校|中学校|こども園|幼稚園|保育[所園])[^<]*)</a>', h):
            名 = m.group(1).strip().replace("市立", "").replace("県立", "")
            if not 名 or "ホームページ" in 名: continue
            t = 種 or ("中学校" if "中学校" in 名 else "小学校" if "小学校" in 名 else
                       "こども園" if "こども園" in 名 else "幼稚園" if "幼稚園" in 名 else "保育所")
            出[名] = t
    if not 出:
        print("！ 市の学校一覧ページから1件も取れなかった。作りが変わった疑い", file=sys.stderr)
    return 出


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

    # ★★ 2026-08-30に作り直し。ここが「開校している学校を閉校と答える」の正体だった。
    #
    #   旧：校歌の記事に出てくる学校 − 施設一覧にある学校 ＝ 閉校
    #   ＝**施設一覧に載っていないだけの学校が、自動的に閉校にされる**。
    #   実際、一宮北小学校は指定避難所ではないため知識ベースに1ページも無く、
    #   施設一覧にも載らず、開校しているのに「閉校」に化けていた。
    #   （市の公式ページにも学校のサイトにも閉校の記載は無い。2026-08-30に確認）
    #
    #   ★「無いこと」を「存在しない証拠」に使わない。
    #     いま実在する学校は**2つの独立した情報源**から取り、
    #     どちらにも無い時だけ閉校とみなす。さらに
    #     「市立◯◯」のページが生きているのに閉校に入る物が出たら**止める**。
    今の別口 = 市の学校一覧()
    for 名, 種 in 今の別口.items():
        if 名 not in 今 and not any(名 in k or k in 名 for k in 今):
            今[名] = {"名": 名, "種類": 種, "地区": "", "電話": "", "url": ""}
            print(f"  ★施設一覧に無いが市の学校一覧にはある: {名}（{種}）", file=sys.stderr)

    閉 = []
    for 名 in 名ら:
        if 名 in 今: continue
        # 「はりま一宮小学校」のように今の名前に含まれる場合も実在とみなす
        if any(名 in k or k in 名 for k in 今): continue
        if 名 in 今の別口: continue
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
    # ★★ 検算：閉校としたものに、いま生きている「市立◯◯」のページが無いか。
    #   あれば開校している疑いが濃いので、**黙って出さずに止める**
    kb題 = {y.get("題", "") for y in kb}
    怪しい = [x["名"] for x in 閉 if ("市立" + x["名"]) in kb題]
    if 怪しい:
        print("！ 閉校としたが、市の『市立◯◯』のページが生きている: "
              + "、".join(怪しい), file=sys.stderr)
        print("  → 開校している疑いが濃い。資料を書かずに止める", file=sys.stderr)
        return 1

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
