#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市の主要PDF（手引き・しおり・ガイド・時刻表・料金表など）の中身を文章にする。
出力: shiso_pdf.json

なぜ作るか（2026-08-22指示「あらゆる質問に答えられるように」の穴埋め①）：
  市の詳しい情報の多くは添付PDFの中にある（生活保護のしおり2.8万字、
  しーたんバス時刻表7.5万字など）。ページの本文だけでは
  「詳しくはPDFを見てください」までしか答えられない。
  中身を文章にして持てば、AIがそこから具体的に答えられる。

選び方（724候補→読み物だけに絞る）：
  ・ガイド/便利帳/しおり/手引き/時刻表/料金/一覧など「読む資料」だけ
  ・様式・申請書・記入例など「書く紙」は除く（文章がなく資料にならない）
  ・「令和6年度…」「令和7年度…」の年度違いは、一番新しい1本だけ
  ・画像だけのPDF（文章が取れない）は записыは残さず飛ばす

道具：
  macOS: scripts/pdf2txt.swift（PDFKit） ／ Linux(Actions): pdftotext（poppler）
"""
import time
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from kensan import 件数を守る
import json, re, time, sys, hashlib, subprocess, shutil, pathlib, urllib.request

根 = pathlib.Path(__file__).resolve().parent.parent
入力 = 根 / "shiso_kb.json"
出力 = 根 / "shiso_pdf.json"
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app; contact via site)"
間 = 0.6
上限本数 = 520      # ★2026-08-28：手数料・所信表明・レシピを拾うようにしたら
                   #   候補が497本になり、320本の枠で新しい資料が丸ごと切れていた。
                   #   （枠に収まった分だけ処理して「320本」と表示するので気づきにくい）
                   #   ★枠に当たったら知らせる（下の 候補を選ぶ の末尾）
                   # （2026-08-27にも同じことが起きている：200本の枠から
                   #   バス時刻表6分割が全部消え、236→184件になった）
上限バイト = 12 * 1024 * 1024      # 12MBを超えるPDFは扱わない
一片 = 8000                        # 1つの塊に入れる文字数
最大片 = 12                        # 1本のPDFを分ける上限（時刻表は約10片になる）

# ★「予定表」「日程」を足す（2026-08-27の指摘）。
#   「子どもの予防接種はいつ」に答えられず、原因を追うと
#   『令和8年度こどもの予防接種予定表』が拾う対象に入っていなかった。
#   接種の時期はこのPDFにしか書かれていない
# ★「手数料」「使用料」を足した（2026-08-28の実測：
#   『宍粟市の各種証明書手数料』が拾う対象に入っておらず、
#   住民票450円・印鑑証明300円といった、市民がいちばん多く聞く値段が
#   資料に1件も無かった。「料金」はあったが「手数料」は無かった）
拾う = re.compile(r"ガイド|便利|しおり|手引|手びき|分け方|出し方|時刻|ダイヤ|カレンダー|料金"
                  r"|手数料|使用料|利用料|価格|表$|早見"
                  # ★市民に必要なのに漏れていた語（2026-08-28に実データで数えて選んだ）。
                  #   「方針」は行政文書が84本も入るので足さない。
                  #   「チェック」も申請の様式ばかりだったので足さない
                  r"|所信表明|レシピ|読本|使い方|注意して|気をつけ"
                  r"|一覧|献立|案内|パンフ|マップ|バス|Q&A|よくある|予定表|日程|スケジュール"
                  r"|開催|実施予定")
# ★委員会の会議録・次第は案内ではない（2026-08-28の実測：「手数料」を足したら
#   「ごみ収集等手数料あり方検討委員会 第1〜6回の次第・会議録」まで拾い、
#   条件に合うPDFが320本→470本に膨れた。読む資料だけに絞る）
# ★「開催記録」「説明会」は市民向けの記録なので残す（2026-08-28の実測：
#   会議録を除いたら『新病院市民説明会 開催記録』5片まで消えた。
#   市民が知りたいのは、まさにこの説明会の中身）
除く = re.compile(r"様式|記入例|届出書|委任状|同意書|ポスター|チラシ|申告書"
                  r"|会議録|議事録|会議次第|委員名簿|答申|意見書|評価シート")


def _ssl文脈():
    try:
        import ssl, certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            import ssl
            return ssl.create_default_context()
        except Exception:
            return None

_文脈 = _ssl文脈()


def 取る(url):
    # ★通信は1回で諦めない（2026-08-23）。GitHub Actionsの週1更新が
    #   1回のタイムアウトで丸ごと落ち、79分かけた他の収集まで捨てられた。
    #   相手のサイトに迷惑をかけないよう、間をあけて3回まで試す
    最後 = None
    for 再試行 in range(3):
        try:
            return 取る一回(url)
        except Exception as e:
            最後 = e
            if 再試行 < 2:
                time.sleep(3 * (再試行 + 1))
    raise 最後


def 取る一回(url):
    req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
    with urllib.request.urlopen(req, timeout=60, context=_文脈) as r:
        return r.read()


def 候補を選ぶ(kb):
    """添付から読み物系を選ぶ。年度違いは一番新しい1本だけ"""
    見た, 束 = set(), {}
    for x in kb["項目"]:
        for a in x.get("添付", []):
            u, 名 = a["url"], a["名"]
            if not u.lower().endswith(".pdf") or u in 見た:
                continue
            見た.add(u)
            if not 拾う.search(名) or 除く.search(名):
                continue
            if "申請書" in 名 and "手引" not in 名:
                continue
            # 大きさの見立て（名前の「(PDFファイル: 7.7MB)」から）
            mb = re.search(r"([\d.]+)\s*MB", 名)
            if mb and float(mb.group(1)) > 上限バイト / 1024 / 1024:
                continue
            素名 = re.sub(r"[（(]PDFファイル[^）)]*[）)]", "", 名).strip()
            # 年度の数字を取り出し、同じ名前の年度違いは新しい方を残す
            年 = 0
            ym = re.search(r"令和(\d+)", 素名)
            if ym: 年 = int(ym.group(1))
            鍵 = re.sub(r"令和\d+年度?|平成\d+年度?", "", 素名)
            今 = 束.get(鍵)
            if 今 is None or 年 > 今["年"]:
                束[鍵] = {"名": 素名, "url": u, "年": 年,
                          "親": x["題"], "課": x.get("課", ""), "電話": x.get("電話", [])}
    out = list(束.values())
    out.sort(key=lambda r: (-r["年"], r["名"]))
    # ★枠で切ったら必ず知らせる（2026-08-28の失敗：320本の枠に当たって
    #   新しく拾えるようにした資料が丸ごと消えていたのに、表示は「候補320本」で
    #   何も起きていないように見えた）
    if len(out) > 上限本数:
        print(f"！ 候補 {len(out)}本のうち {len(out)-上限本数}本を枠で切った"
              f"（上限本数={上限本数}）。枠を上げるか、拾う条件を見直すこと",
              file=sys.stderr)
    return out[:上限本数]


def 取り出し係を用意():
    if shutil.which("pdftotext"):
        def 取り出す(pdf):
            r = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
                               capture_output=True, timeout=120)
            return r.stdout.decode("utf-8", "replace")
        return 取り出す, "pdftotext"
    swift元 = 根 / "scripts" / "pdf2txt.swift"
    道具 = pathlib.Path("/tmp/shiso_pdf2txt")
    if shutil.which("swiftc"):
        if (not 道具.exists()) or 道具.stat().st_mtime < swift元.stat().st_mtime:
            subprocess.run(["swiftc", "-O", str(swift元), "-o", str(道具)], check=True)
        def 取り出す(pdf):
            r = subprocess.run([str(道具), str(pdf)], capture_output=True, timeout=120)
            return r.stdout.decode("utf-8", "replace")
        return 取り出す, "PDFKit(Swift)"
    raise SystemExit("PDFの文章を取り出す道具が無い（pdftotext か swiftc が要る）")


def 整える(t):
    t = re.sub(r"[ \t　]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    return t[:一片 * 最大片]


def 分ける(t):
    """長い資料は塊に分けて、全部を検索できるようにする。
       ★2026-08-22の失敗：バス時刻表7.5万字を8千字で切っていたため、
         89%（ほとんどのバス停と便）が資料に存在せず、
         「山崎町山田から波賀へ」に答えられなかった。
       行の途中で切らない（時刻の並びを壊さないため）"""
    if len(t) <= 一片:
        return [t]
    out, 今 = [], []
    長さ = 0
    for 行 in t.split("\n"):
        if 長さ + len(行) > 一片 and 今:
            out.append("\n".join(今)); 今, 長さ = [], 0
            if len(out) >= 最大片: break
        今.append(行); 長さ += len(行) + 1
    if 今 and len(out) < 最大片: out.append("\n".join(今))
    # ★中身のほとんど無い断片は前の塊へ併合する（2026-08-23の点検で発覚：
    #   大型バス時刻表の(2/2)が「18:25\n11 12」の11字だけで保存されていた。
    #   ゴミ資料は検索の点数を薄めるだけで益が無い）
    while len(out) >= 2 and len(out[-1].strip()) < 200:
        末 = out.pop()
        out[-1] = out[-1] + "\n" + 末
    return out


if __name__ == "__main__":
    kb = json.loads(入力.read_text(encoding="utf-8"))
    候補 = 候補を選ぶ(kb)
    print(f"候補 {len(候補)}本", file=sys.stderr)

    前回 = {}
    if 出力.exists():
        try:
            for r in json.loads(出力.read_text(encoding="utf-8")).get("項目", []):
                前回[r["url"]] = r
        except Exception:
            pass

    取り出す, 道具名 = 取り出し係を用意()
    print(f"取り出しの道具: {道具名}", file=sys.stderr)
    # ★画像から文字を読む道具（macOSだけ。Linuxには無いので None）
    読み取りの道具 = None
    元ocr = 根 / "scripts" / "pdfocr.swift"
    if shutil.which("swiftc") and 元ocr.exists():
        道 = pathlib.Path("/tmp/shiso_pdfocr")
        try:
            if (not 道.exists()) or 道.stat().st_mtime < 元ocr.stat().st_mtime:
                subprocess.run(["swiftc", "-O", str(元ocr), "-o", str(道)], check=True)
            読み取りの道具 = 道
            print("  画像から文字を読む道具を用意した", file=sys.stderr)
        except Exception as e:
            print(f"  読み取りの道具を作れない: {e}", file=sys.stderr)

    項目, 文字なし = [], 0
    for i, r in enumerate(候補):
        try:
            b = 取る(r["url"])
        except Exception as e:
            print(f"  読めない {r['名'][:30]} {e}", file=sys.stderr)
            continue
        time.sleep(間)
        if len(b) > 上限バイト:
            continue
        指紋 = hashlib.sha256(b).hexdigest()
        古 = 前回.get(r["url"])
        if 古 and 古.get("指紋") == 指紋:
            項目.append(古)                      # 変わっていない＝前回の文章を使い回す
            continue
        一時 = pathlib.Path("/tmp/shiso_one.pdf")
        一時.write_bytes(b)
        try:
            文 = 整える(取り出す(一時))
        except Exception as e:
            print(f"  取り出せない {r['名'][:30]} {e}", file=sys.stderr)
            continue
        # ★画像だけのPDFは、macOSの文字読み取りにかける（2026-08-28）。
        #   実測：『宍粟市子育てガイドブック』（5.6MB）は文字情報が1字も無く、
        #   子育ての制度・相談窓口・遊び場が丸ごと届いていなかった。
        #   ★Linux（GitHub Actions）にはこの道具が無いので、あるときだけ使う
        読み取った = False
        if len(文) < 120 and 読み取りの道具:
            try:
                o = subprocess.run([str(読み取りの道具), str(一時)],
                                   capture_output=True, timeout=900)
                文2 = 整える(o.stdout.decode("utf-8", "replace"))
                if len(文2) > len(文): 文, 読み取った = 文2, True
            except Exception as e:
                print(f"  読み取れない {r['名'][:30]} {e}", file=sys.stderr)
        if len(文) < 120:                        # それでも文章が無い
            文字なし += 1
            continue
        # ★題に親記事の名前も含める（2026-08-22実測：題が「時刻表（…）」だけだと
        #   「バス」で探しても届かない。親「しーたんバス時刻表」が入って初めて当たる）
        題 = r["名"] if r["親"] in r["名"] else (r["親"] + " " + r["名"])
        片たち = 分ける(文)
        for k, 片 in enumerate(片たち, 1):
            付 = "" if len(片たち) == 1 else f"（{k}/{len(片たち)}）"
            一 = {"題": "資料 " + 題 + 付, "url": r["url"], "文": 片,
                  "親": r["親"], "課": r["課"], "電話": r["電話"], "指紋": 指紋}
            if 読み取った: 一["読み取り"] = True
            項目.append(一)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(候補)} … {r['名'][:26]}", file=sys.stderr)

    件数を守る("PDF資料", len(項目))

    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市公式サイトの添付PDF",
        "件数": len(項目),
        "項目": 項目,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(項目)}本の文章を保存（画像だけで飛ばした {文字なし}本）"
          f" → {出力}（{出力.stat().st_size//1024}KB）")
