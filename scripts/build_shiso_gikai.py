#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""宍粟市議会の議員名簿を集める。
出力: shiso_gikai.json

なぜ作るか（2026-08-27）：
  「うちの地区の議員は誰ですか」に答えられなかった。
  資料に『議員』が題に入る記事は条例1件だけ。
  市議会のページは /soshiki/sonotabukyoku/gikaijimukyoku/ の下にあり、
  本体の収集器は /gikai/ を除外しているため一度も辿れていなかった。

  名簿には氏名・ふりがな・当選回数・党派・所属委員会・連絡先住所（町名）が載る。
  住所の町名で引ければ「山崎町の議員は」に答えられる。

★人の名前を扱うので、書いてあること以外は一切足さない。
  読み（ふりがな）も市が書いたものだけを使う。
"""
import json, re, sys, time, pathlib, importlib.util

根 = pathlib.Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("kb", 根/'scripts'/'build_shiso_kb.py')
kb = importlib.util.module_from_spec(_s); _s.loader.exec_module(kb)

元 = "https://www.city.shiso.lg.jp"
名簿 = 元 + "/soshiki/sonotabukyoku/gikaijimukyoku/tanntoujyouhou1/giinnituite/1387249527109.html"
構成 = 元 + "/soshiki/sonotabukyoku/gikaijimukyoku/tanntoujyouhou1/giinnituite/1420699347099.html"
仕組 = 元 + "/soshiki/sonotabukyoku/gikaijimukyoku/tanntoujyouhou1/giinnituite/1387247376444.html"
出力 = 根 / "shiso_gikai.json"


def 本文(u):
    h = kb.取る(u)
    time.sleep(0.7)
    return kb.文字だけ(h), kb.更新日を取る(h), h


def 走る():
    t, 更新, h = 本文(名簿)
    i = t.find("議長")
    if i < 0:
        print("！ 名簿のページが変わっている"); sys.exit(1)
    t = t[i:]

    議長 = re.search(r"議長[:：]\s*([^\s]+(?:\s[^\s]+)?)\s", t)
    副議長 = re.search(r"副議長[:：]\s*([^\s]+(?:\s[^\s]+)?)\s", t)
    現在 = re.search(r"名簿[（(](.+?年.+?月.+?日)現在", t)

    人 = []
    for m in re.finditer(
            r"議席番号\s*(\d+)\s*ふりがな[:：]\s*(.+?)\s*氏名[:：]\s*(.+?)\s*"
            r"当選回数[:：]\s*(.+?)\s*党派[:：]\s*(.+?)\s*"
            r"所属委員会[:：]\s*(.+?)\s*連絡先住所[:：]\s*([^\s]+)", t):
        人.append({
            "議席": int(m.group(1)),
            "読み": m.group(2).strip(),
            "名前": m.group(3).strip(),
            "当選回数": m.group(4).strip(),
            "党派": m.group(5).strip(),
            "委員会": m.group(6).strip(),
            "住所": m.group(7).strip(),
        })
    return 人, 議長, 副議長, 現在, 更新


if __name__ == "__main__":
    人, 議長, 副議長, 現在, 更新 = 走る()
    if len(人) < 10:
        print(f"！ 議員が {len(人)}人しか取れない。読み取りが壊れている"); sys.exit(1)

    町 = {}
    for x in 人:
        き = re.match(r"(.+?町)", x["住所"])
        き = き.group(1) if き else x["住所"]
        町.setdefault(き, []).append(x["名前"])

    # 議会の仕組み・構成も本文で持っておく（「議会は何人」「委員会は」に答えるため）
    足し = []
    for 名, u in (("宍粟市議会の構成", 構成), ("宍粟市議会の仕組み", 仕組)):
        try:
            t, _, _ = 本文(u)
            j = t.find("現在の位置")
            if j >= 0:
                t = t[j + 5:]
            k = t.find("この記事に関するお問い合わせ先")
            if k > 0:
                t = t[:k]
            if len(t) > 100:
                足し.append({"題": 名, "文": t[:4000], "url": u})
        except Exception as e:
            print(f"  ！{名}が取れない … {e}")

    出 = {
        "説明": "宍粟市議会の議員名簿。市議会事務局のページより",
        "出典": 名簿, "更新日": 更新,
        "名簿の時点": 現在.group(1) if 現在 else "",
        "議長": 議長.group(1).strip() if 議長 else "",
        "副議長": 副議長.group(1).strip() if 副議長 else "",
        "定数": len(人),
        "町ごと": {k: v for k, v in sorted(町.items())},
        "項目": 人,
        "説明の記事": 足し,
    }
    出力.write_text(json.dumps(出, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"○ 議員 {len(人)}人 → shiso_gikai.json")
    print(f"  議長 {出['議長']} / 副議長 {出['副議長']} / 時点 {出['名簿の時点']}")
    for k, v in 出["町ごと"].items():
        print(f"  {k}: {len(v)}人  {'、'.join(v)}")
    欠 = [x["議席"] for x in 人 if not x["読み"] or not x["住所"]]
    print(f"  読みか住所が欠けている議席: {欠 if 欠 else 'なし'}")
    print(f"  説明の記事 {len(足し)}件")
