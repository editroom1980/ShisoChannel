#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""宍粟市の「よくある質問」を丸ごと集める。
出力: shiso_faq.json

なぜ作るか（2026-08-27）：
  市民の言い方40問を試したら即答は32%で、26問がAI行きだった。
  資料そのものは有るのに、条例や要綱が上に来て記事を1件に絞れない。
  ところが市のサイトには /faq/ の木があり、**題がそのまま質問文**になっている。
  「妊娠したことによる、必要な手続きがありますか」――市が自分で書いた問いと答え。
  これなら聞かれた言葉と題を突き合わせるだけで、AIを使わずに答えられる。

  本体の収集器(build_shiso_kb.py)は /faq/ を入口に持っておらず、
  他のページから偶然繋がっていた56件しか入っていなかった。

取り決め：
  ・取得の作法（間をあける・名乗る・3回まで再試行）は本体から読み込んで使う。
    同じ処理を2か所に持たない
  ・「//www...」で始まる書き方（プロトコル相対）が市のページに実在する。
    そのまま繋ぐとファイル扱いで全滅するので直す
"""
import json, re, sys, time, pathlib, urllib.parse, importlib.util
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from kensan import 件数を守る

根 = pathlib.Path(__file__).resolve().parent.parent
# 本体の収集器を読み込む（フォルダ名に空白があるので importlib で）
_s = importlib.util.spec_from_file_location("kb", 根/'scripts'/'build_shiso_kb.py')
kb = importlib.util.module_from_spec(_s); _s.loader.exec_module(kb)

元 = "https://www.city.shiso.lg.jp"
出力 = 根 / "shiso_faq.json"
間 = 0.7          # 1ページごとに空ける秒数（市のサーバーに負担をかけない）
上限 = int(sys.argv[1]) if len(sys.argv) > 1 else 600


def URLを直す(u, 基):
    """市のページには「//www.city...」で始まる書き方が実在する。
       urljoin はこれを正しく扱えるが、素で繋ぐと壊れるので明示的に直す"""
    u = (u or "").strip()
    if u.startswith("//"):
        return "https:" + u
    return urllib.parse.urljoin(基, u)


def 質問文(生html, 予備):
    """記事の見出し＝市が書いた質問文"""
    for 型 in (r'(?is)<h1[^>]*>(.*?)</h1>', r'(?is)<title[^>]*>(.*?)</title>'):
        m = re.search(型, 生html)
        if not m:
            continue
        t = kb.文字だけ(m.group(1))
        t = re.sub(r'[／/]宍粟市\s*$', '', t).strip()
        if len(t) >= 4:
            return t
    return 予備


def 答え文(生html):
    """本文から、パンくず（現在の位置〜）と繰り返しの題を落とした中身"""
    t = kb.本文(生html)
    # 「くらし・手続き ○○ ○○ 質問文 質問文 広報ID …」の形。
    # 広報IDより後ろが答え本体。無ければ更新日より後ろ
    m = re.search(r'広報ID\s*\d+\s*更新日[：:]\s*\d{4}年\d{1,2}月\d{1,2}日', t)
    if m:
        return t[m.end():].strip()
    m = re.search(r'更新日[：:]\s*\d{4}年\d{1,2}月\d{1,2}日', t)
    if m:
        return t[m.end():].strip()
    return t


def 走る():
    待ち = ["/faq/index.html"]
    見た, 集め = set(), []
    索引数 = 0
    while 待ち and len(集め) < 上限:
        u = 待ち.pop(0)
        u = URLを直す(u, 元)
        if u in 見た or "/faq/" not in u:
            continue
        見た.add(u)
        try:
            h = kb.取る(u)
        except Exception as e:
            print(f"  ！取れない {u} … {e}")
            continue
        time.sleep(間)

        # ページ内の /faq/ の行き先を全部待ち行列へ
        for m in re.finditer(r'href="([^"]+)"', h):
            v = URLを直す(m.group(1), u).split("#")[0]
            if "/faq/" in v and v not in 見た and not kb.除外.search(v):
                待ち.append(v)

        if u.endswith("/index.html"):
            索引数 += 1
            continue   # 一覧ページ自体は答えではない

        題 = 質問文(h, u.rsplit("/", 1)[-1])
        本 = 答え文(h)
        if len(本) < 20:
            continue
        集め.append({
            "題": 題,
            "文": 本,
            "url": u,
            "更新日": kb.更新日を取る(h),
            "問い合わせ": kb.問い合わせ先(h),
            "表": kb.表を取る(h),
            "添付": kb.添付を取る(h, u),
        })
        print(f"  {len(集め):3d}. {題[:52]}")
    return 集め, 索引数, len(見た)


if __name__ == "__main__":
    始 = time.time()
    集め, 索引数, 見た数 = 走る()
    # 同じ質問が別のカテゴリにも載っている（保育とけんこうに同じ妊娠の質問）。
    # 題が同じものは、本文の長い方を残す
    束 = {}
    for x in 集め:
        き = x["題"]
        if き not in 束 or len(x["文"]) > len(束[き]["文"]):
            束[き] = x
    項目 = sorted(束.values(), key=lambda x: x["題"])

    出 = {"説明": "宍粟市公式サイトの「よくある質問」。題が市の書いた質問文そのもの",
          "出典": 元 + "/faq/index.html",
          "件数": len(項目), "項目": 項目}
    出力.write_text(json.dumps(出, ensure_ascii=False, indent=1), encoding="utf-8")

    字 = sum(len(x["文"]) for x in 項目)
    件数を守る("よくある質問", len(項目))
    print(f"\n○ {len(項目)}件（重複を除く前 {len(集め)}件）/ 一覧ページ {索引数} / 見たURL {見た数}")
    print(f"  本文 合計 {字:,}字 / 1件あたり平均 {字//max(len(項目),1)}字")
    print(f"  電話つき {sum(1 for x in 項目 if x['問い合わせ'].get('電話'))}件")
    print(f"  {時:.0f}秒".replace("時", "") if False else f"  {time.time()-始:.0f}秒")
