#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市の施設（学校・保育所・公共施設・避難所など）の一覧を作る。
出力: shiso_shisetsu.json

なぜ作るか（2026-08-22の実声テストで判明した2つの失敗）：
  ① 「宍粟市内の小学校の電話番号」で **4校しか出なかった**。
     学校は1校1ページなので、AIに渡す上位4件＝4校で打ち止めだった。
     → 一覧を1枚にまとめて持てば、全校を一度に答えられる。
  ② 「波賀町の小学校」の連絡先に **危機管理課** が出た。
     学校のページは「指定避難所」のページで、担当課が危機管理課になっている。
     ページ本文には学校の電話（0790-75-2354）があるのに、そちらが使われなかった。
     → 施設そのものの電話・住所を抜き出して持てば、課と取り違えない。

作り方：
  市のページ本文にある「住所 〒… 兵庫県宍粟市… 電話番号 0790-…」の型を読む。
  避難所ページは収容人員・土砂災害警戒区域も持っているので、防災の質問にも使える。
"""
import json, re, time, pathlib, sys

根 = pathlib.Path(__file__).resolve().parent.parent
入力 = 根 / "shiso_kb.json"
出力 = 根 / "shiso_shisetsu.json"

# ★「住所」と「所在地」の両方の書き方がある（こども園のページは所在地。2026-08-22追加）
住所電話 = re.compile(
    r"(?:住所|所在地)\s*(?:〒\s*)?(\d{3}-?\d{4})?\s*((?:兵庫県)?宍粟市[^\s]{2,30})\s+電話番号\s*"
    r"(0\d{1,3}[-−]\d{2,4}[-−]\d{3,4})")
収容 = re.compile(r"収容人員\s*([\d,]+)\s*人")
土砂 = re.compile(r"土砂災害警戒区域\s*(あり[^\s]*|なし)")


def 種類(題, 文):
    """名前と中身から施設の種類を決める。質問の言葉で引けるようにするため"""
    for 語, 名 in (("小学校", "小学校"), ("中学校", "中学校"), ("高等学校", "高校"),
                   ("こども園", "こども園"), ("保育所", "保育所"), ("幼稚園", "幼稚園"),
                   ("公民館", "公民館"), ("図書館", "図書館"), ("市民局", "市民局"),
                   ("センター", "センター"), ("体育館", "体育館"), ("グラウンド", "運動施設"),
                   ("温泉", "温泉"), ("病院", "病院"), ("診療所", "診療所"),
                   ("消防", "消防"), ("駐在所", "警察")):
        if 語 in 題:
            return 名
    if "指定避難所" in 文:
        return "避難所"
    return "施設"


def 表から施設(kb):
    """名称と電話番号の列を持つ表（こども園・保育所の一覧など）から施設を抜く。
       2026-08-22追加：こども園9園・保育所4園はページ本文でなく表に入っている"""
    出た = []
    for x in kb["項目"]:
        for 表 in x.get("表", []):
            if len(表) < 2:
                continue
            頭 = 表[0]
            try:
                名列 = next(i for i, c in enumerate(頭) if "名称" in c or c == "名前")
                電列 = next(i for i, c in enumerate(頭) if "電話" in c)
            except StopIteration:
                continue
            住列 = next((i for i, c in enumerate(頭) if "所在地" in c or "住所" in c), None)
            定列 = next((i for i, c in enumerate(頭) if "定員" in c), None)
            for 行 in 表[1:]:
                if len(行) <= max(名列, 電列):
                    continue
                名 = re.sub(r"[（(][^（()）]*[)）]", "", 行[名列]).strip()
                名 = re.sub(r"\s*施設を紹介$", "", 名)
                # 電話欄には「0790-…（代表）」等の飾りが付くことがある。番号だけを取る
                電m = re.search(r"0\d{1,3}[-−]\d{2,4}[-−]\d{3,4}", 行[電列])
                if len(名) < 2 or not 電m:
                    continue
                電 = 電m.group(0)
                r = {"名": 名, "種類": 種類(名 + x["題"], ""), "電話": 電.replace("−", "-"),
                     "url": x["url"]}
                if 住列 is not None and len(行) > 住列:
                    住 = 行[住列].strip()
                    # ★市外の施設（あじさい苑＝姫路市安富町）に宍粟市を付けない。
                    #   市内の町名で始まる時だけ「宍粟市」を頭に足す
                    if re.match(r"(山崎町|一宮町|波賀町|千種町)", 住):
                        住 = "宍粟市" + 住
                    r["住所"] = 住
                    g = re.search(r"(山崎町|一宮町|波賀町|千種町)", r["住所"])
                    if g: r["地区"] = g.group(1)
                if 定列 is not None and len(行) > 定列 and 行[定列].strip():
                    r["定員"] = 行[定列].strip()
                出た.append(r)
    return 出た


if __name__ == "__main__":
    kb = json.loads(入力.read_text(encoding="utf-8"))
    出た, 見た = [], set()
    for r in 表から施設(kb):
        鍵 = re.sub(r"^(市立|公立)\s*", "", r["名"])
        if 鍵 in 見た:
            continue
        見た.add(鍵)
        出た.append(r)
    for x in kb["項目"]:
        文 = x.get("文", "")
        m = 住所電話.search(文)
        if not m:
            continue
        名 = re.sub(r"^(市立|公立)\s*", "", x["題"]).strip()
        if 名 in 見た:
            continue
        見た.add(名)
        r = {
            "名": x["題"].strip(),
            "種類": 種類(x["題"], 文),
            "住所": m.group(2).replace("兵庫県", ""),
            "電話": m.group(3).replace("−", "-"),
            "url": x["url"],
        }
        if m.group(1): r["郵便番号"] = m.group(1)
        c = 収容.search(文)
        if c: r["収容人員"] = c.group(1) + "人"
        d = 土砂.search(文)
        if d: r["土砂災害警戒区域"] = d.group(1)
        # 地区（山崎町・一宮町・波賀町・千種町）を住所から取る
        g = re.search(r"宍粟市(山崎町|一宮町|波賀町|千種町)", m.group(2))
        if g: r["地区"] = g.group(1)
        # 「指定避難所 波賀中学校区」のような校区の記載
        k = re.search(r"指定避難所\s+([^\s]{2,12}区)", 文)
        if k: r["校区"] = k.group(1)
        出た.append(r)

    出た.sort(key=lambda r: (r["種類"], r.get("地区", ""), r["名"]))
    from collections import Counter
    数 = Counter(r["種類"] for r in 出た)
    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市公式サイト（各施設・指定避難所のページ本文より機械抽出）",
        "件数": len(出た),
        "種類別": dict(数),
        "項目": 出た,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(出た)}件 → {出力}（{出力.stat().st_size//1024}KB）")
    print("種類別:", dict(数))
