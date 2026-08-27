#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""市の外にある窓口（市役所では扱っていない手続きの行き先）を集める。
出力: shiso_shigai.json

なぜ作るか（2026-08-28）：
  「パスポートはどこで取れますか」に答えられなかった。
  市の資料を隅まで探しても、パスポートの扱いは1件も無い。
  実際、宍粟市役所ではパスポートを扱っていない（市民課の一覧に無い）。
  ここで「分かりません」と答えるのは、市民にとって答えになっていない。

  こういう「市ではやっていないが、市民が必要とする手続き」の行き先を、
  出どころのはっきりした一次情報から持っておく。

★必ず、その窓口を運営している役所の公式ページから取る。
★取れなかった項目は空のままにして報告する（埋めない）。
"""
import json, re, sys, time, pathlib, urllib.request, importlib.util

根 = pathlib.Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("kb", 根/'scripts'/'build_shiso_kb.py')
kb = importlib.util.module_from_spec(_s); _s.loader.exec_module(kb)
出力 = 根 / "shiso_shigai.json"

対象 = [
    {"件名": "パスポート（旅券）",
     "呼び名": ["パスポート", "旅券"],
     "市では": "宍粟市役所では扱っていません（市民課の手続き一覧に無い）",
     "url": "https://www.hyogo-passport.jp/main/n_madoguchi.html",
     "窓口名": "兵庫県旅券事務所 姫路出張所",
     "切り出し": "姫路出張所"},
]


def 拾う(文, 見出し):
    i = 文.find(見出し)
    if i < 0:
        return {}
    塊 = 文[i:i + 700]
    r = {}
    m = re.search(r"〒\s*(\d{3}-?\d{4})\s*([^\s]{4,40})", 塊)
    if m:
        r["住所"] = m.group(2).strip()
        r["郵便番号"] = m.group(1)
    m = re.search(r"TEL[：:]\s*(\d{2,4}-\d{2,4}-\d{3,4})", 塊)
    if m: r["電話"] = m.group(1)
    m = re.search(r"申請（申し込み）受付時間[…\s]*(.{5,60}?)\s*交付", 塊)
    if m: r["申請の受付"] = m.group(1).strip()
    m = re.search(r"交付（受け取り）受付時間[…\s]*(.{5,90}?)\s*アクセス", 塊)
    if m: r["受け取りの受付"] = m.group(1).strip()
    m = re.search(r"アクセス[…\s]*(.{5,80}?)\s*(バリアフリー|○|$)", 塊)
    if m: r["行き方"] = m.group(1).strip()
    m = re.search(r"※\s*(土[^。]{5,60})", 塊)
    if m: r["休み"] = m.group(1).strip()
    return r


if __name__ == "__main__":
    出, 欠 = [], []
    for t in 対象:
        try:
            h = kb.取る(t["url"])
        except Exception as e:
            print(f"！{t['件名']} が取れない {e}", file=sys.stderr); sys.exit(1)
        time.sleep(0.6)
        文 = kb.文字だけ(h)
        r = dict(t); r.pop("切り出し")
        r.update(拾う(文, t["切り出し"]))
        for 要 in ("住所", "電話"):
            if 要 not in r: 欠.append(f"{t['件名']}に「{要}」が無い")
        出.append(r)
        print(f"○ {t['件名']} → {r.get('窓口名')}")
        for k in ("住所", "電話", "申請の受付", "受け取りの受付", "行き方", "休み"):
            if k in r: print(f"    {k}: {r[k][:70]}")

    if 欠:
        print("！ 足りない欄: " + " / ".join(欠), file=sys.stderr); sys.exit(1)

    出力.write_text(json.dumps({
        "説明": "宍粟市役所では扱っていないが、市民が必要とする手続きの行き先",
        "件数": len(出), "項目": 出,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n○ {len(出)}件 → shiso_shigai.json")
