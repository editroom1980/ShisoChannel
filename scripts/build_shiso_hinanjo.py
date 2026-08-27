#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宍粟市の指定避難所を、市の記事（/shiteihinanjo/ 配下）から整理する。
出力: shiso_hinanjo.json

なぜ作るか（2026-08-27）：
  「避難所はどこ」に答えられなかった。記事は30件あったのに、
  一覧としてまとまっておらず、地区で引く形になっていなかった。
  災害時にテレビの前の人が最初に聞くことなので、確実に答えられるようにする。

★市の記事には、住所・電話・収容人員・浸水想定深・土砂災害警戒区域まで
  書かれている。数値は必ず記事から取り、作らない。
出典：宍粟市公式サイト（まちづくり部 危機管理課）
"""
import json, re, sys, time, pathlib

根 = pathlib.Path(__file__).resolve().parent.parent
入力 = 根 / "shiso_kb.json"
出力 = 根 / "shiso_hinanjo.json"


def 中身だけ(文):
    m = re.search(r"更新日：\d{4}年\d{1,2}月\d{1,2}日\s*", 文 or "")
    return (文[m.end():] if m else (文 or "")).strip()


def 拾う(t, 見出し, 上限=40):
    """「収容人員 200人」のような『見出し 値』の形から値だけ取る"""
    m = re.search(re.escape(見出し) + r"[\s:：]*([^\s　]{1,%d})" % 上限, t)
    return m.group(1).strip() if m else ""


if __name__ == "__main__":
    kb = json.loads(入力.read_text(encoding="utf-8"))
    出 = []
    for x in kb["項目"]:
        if "shiteihinanjo" not in x.get("url", ""):
            continue
        t = 中身だけ(x.get("文", ""))
        if len(t) < 40:
            continue
        住 = re.search(r"(兵庫県宍粟市[^\s　]+)", t)
        電 = re.search(r"0\d{1,4}-\d{1,4}-\d{3,4}", t)
        地区 = ""
        for g in ("山崎町", "一宮町", "波賀町", "千種町"):
            if 住 and g in 住.group(1):
                地区 = g; break
        # 地区が住所から取れない時は、URLの区分（yamasakinishi 等）から寄せる
        if not 地区:
            u = x["url"]
            for 鍵, g in (("yamasaki", "山崎町"), ("ichinomiya", "一宮町"),
                          ("haga", "波賀町"), ("chikusa", "千種町")):
                if 鍵 in u:
                    地区 = g; break
        出.append({
            "名": x.get("題", "").strip(),
            "住所": 住.group(1) if 住 else "",
            "電話": 電.group(0) if 電 else "",
            "地区": 地区,
            "収容人員": 拾う(t, "収容人員"),
            "浸水想定": 拾う(t, "浸水想定深（想定最大規模降雨）") or 拾う(t, "浸水想定深"),
            "土砂災害警戒区域": 拾う(t, "土砂災害警戒区域"),
            "url": x.get("url", ""),
        })
    見, 一覧 = set(), []
    for x in 出:
        if x["名"] in 見: continue
        見.add(x["名"]); 一覧.append(x)
    一覧.sort(key=lambda x: (x["地区"], x["名"]))

    # ── 検算 ──
    住あり = sum(1 for x in 一覧 if x["住所"])
    収あり = sum(1 for x in 一覧 if x["収容人員"])
    if len(一覧) < 15:
        print(f"★{len(一覧)}件しか取れていない。記事の場所が変わった可能性", file=sys.stderr)
        sys.exit(1)
    if 住あり < len(一覧) * 0.8:
        print(f"★住所の取れないものが多い（{len(一覧)-住あり}件）", file=sys.stderr)
        sys.exit(1)

    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市公式サイト 指定避難所（まちづくり部 危機管理課）",
        "注意": "開設される避難所は災害の種類や状況で変わります。"
                "実際の避難は市の防災行政無線・テレビ・市公式LINEの案内に従ってください",
        "件数": len(一覧),
        "項目": 一覧,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    from collections import Counter
    print(f"{len(一覧)}か所（住所{住あり}・収容人員{収あり}）→ {出力}"
          f"（{出力.stat().st_size//1024}KB）")
    for k, v in Counter(x["地区"] or "(不明)" for x in 一覧).most_common():
        print(f"  {k}: {v}か所")
