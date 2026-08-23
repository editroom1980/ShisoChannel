#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ごみ収集カレンダーの資料を作る。
出力: shiso_gomi.json ＋ gomi_cal/ フォルダのPNG画像

なぜ作るか（2026-08-22指示）：
  「ゴミ出しの仕方を教えて→お住まいの地域は？→地域名→その地区のカレンダーを表示」
  を実現するため。市のカレンダーは地区ごとに34種類のPDFで配られているが、
  テレビのWebViewはPDFを表示できない。そこで、
   1. 市のページから「地区 → カレンダー番号」の対応表を取り出し
   2. PDFを34本すべて取り寄せ
   3. 全ページをPNG画像（幅1600px・テレビで文字が読める精細さ）に描き直して
  アプリが「地区名を聞いて→画像を出す」だけで済む形にしておく。

無駄な取り直しをしないこと：
  PDFの中身の指紋(sha256)を控えておき、変わっていなければ描き直さない。
  （毎週の自動更新で、市が差し替えた時だけ画像が作り直される）

道具：
  macOS: scripts/pdf2png.swift（CoreGraphics。sipsは1枚目しか変換できないため不可）
  Linux(GitHub Actions): pdftoppm（poppler-utils）
"""
import time
import json, re, time, sys, html, hashlib, subprocess, shutil
import urllib.request, urllib.parse, pathlib

ページ = "https://www.city.shiso.lg.jp/kurashi/gomishinyokankyo/kankyorisaikuru/21206.html"
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app; contact via site)"
根 = pathlib.Path(__file__).resolve().parent.parent
出力 = 根 / "shiso_gomi.json"
画像置き場 = 根 / "gomi_cal"
幅 = 1600
間 = 0.5


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


def 取る(url, バイトで=False):
    # ★通信は1回で諦めない（2026-08-23）。GitHub Actionsの週1更新が
    #   1回のタイムアウトで丸ごと落ち、79分かけた他の収集まで捨てられた。
    #   相手のサイトに迷惑をかけないよう、間をあけて3回まで試す
    最後 = None
    for 再試行 in range(3):
        try:
            return 取る一回(url, バイトで)
        except Exception as e:
            最後 = e
            if 再試行 < 2:
                time.sleep(3 * (再試行 + 1))
    raise 最後


def 取る一回(url, バイトで=False):
    req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
    with urllib.request.urlopen(req, timeout=30, context=_文脈) as r:
        b = r.read()
    return b if バイトで else b.decode("utf-8", "replace")


def 文字だけ(h):
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def 対応表を取り出す(h):
    """表の各行 = [カレンダー番号のリンク, 収集地区の文]。番号とPDFと地区を対で返す"""
    表 = re.search(r"(?is)<table[^>]*>.*?</table>", h)
    if not 表:
        raise SystemExit("対応表が見つからない（ページの作りが変わった）")
    行たち = []
    for tr in re.findall(r"(?is)<tr[^>]*>.*?</tr>", 表.group(0)):
        マス生 = re.findall(r"(?is)<t[hd][^>]*>.*?</t[hd]>", tr)
        if len(マス生) < 2:
            continue
        番号名 = 文字だけ(マス生[0])
        m = re.search(r'href=["\']([^"\']+\.pdf)["\']', マス生[0])
        番 = re.search(r"[Nn][Oo]\.?\s*([\d]+(?:-\d+)?)", 番号名)
        if not (m and 番):
            continue                      # 見出し行（エリア番号/収集路線）はここで落ちる
        地区 = 文字だけ(マス生[1])
        行たち.append({
            "番号": "No." + 番.group(1),
            "pdf": urllib.parse.urljoin(ページ, m.group(1)),
            "地区": 地区,
        })
    return 行たち


def 年度を取り出す(h):
    m = re.search(r"(令和\d+年度)家庭ごみ", 文字だけ(h))
    return m.group(1) if m else ""


def 変換係を用意():
    """PDF→PNGの道具。Macは自前のSwift、LinuxはpdftoppmM"""
    if shutil.which("pdftoppm"):
        def 変換(pdf, 頭):
            subprocess.run(["pdftoppm", "-png", "-r", "150", str(pdf), str(頭)], check=True)
            # pdftoppm は 頭-1.png 形式で出す → 頭_1.png に揃える
            出た = sorted(頭.parent.glob(頭.name + "-*.png"))
            for i, p in enumerate(出た, 1):
                p.rename(頭.parent / f"{頭.name}_{i}.png")
            return len(出た)
        return 変換, "pdftoppm"
    swift元 = 根 / "scripts" / "pdf2png.swift"
    道具 = pathlib.Path("/tmp/shiso_pdf2png")
    if shutil.which("swiftc"):
        if (not 道具.exists()) or 道具.stat().st_mtime < swift元.stat().st_mtime:
            subprocess.run(["swiftc", "-O", str(swift元), "-o", str(道具)], check=True)
        def 変換(pdf, 頭):
            r = subprocess.run([str(道具), str(pdf), str(頭), str(幅)],
                               capture_output=True, text=True, check=True)
            return int(r.stdout.strip())
        return 変換, "swift(CoreGraphics)"
    raise SystemExit("PDFを画像にする道具が無い（pdftoppm か swiftc が要る）")


if __name__ == "__main__":
    h = 取る(ページ)
    行たち = 対応表を取り出す(h)
    年度 = 年度を取り出す(h)
    if len(行たち) < 20:
        raise SystemExit(f"対応表が{len(行たち)}行しか取れない（例年34行。ページの作りが変わった）")
    print(f"{年度} 対応表 {len(行たち)}行", file=sys.stderr)

    # 前回の指紋を読む（変わっていない地区は描き直さない）
    前回 = {}
    if 出力.exists():
        try:
            for r in json.loads(出力.read_text(encoding="utf-8")).get("地区表", []):
                前回[r["番号"]] = r
        except Exception:
            pass

    画像置き場.mkdir(exist_ok=True)
    変換, 道具名 = 変換係を用意()
    print(f"描き直しの道具: {道具名}", file=sys.stderr)

    for r in 行たち:
        名 = r["番号"].lower().replace("no.", "no")        # No.2-1 → no2-1
        pdf = 取る(r["pdf"], バイトで=True)
        time.sleep(間)
        指紋 = hashlib.sha256(pdf).hexdigest()
        古 = 前回.get(r["番号"])
        if (古 and 古.get("指紋") == 指紋
                and all((根 / p).exists() for p in 古.get("画像", []))):
            r["指紋"], r["画像"] = 指紋, 古["画像"]        # 変化なし＝前回の画像のまま
            continue
        一時 = pathlib.Path(f"/tmp/shiso_{名}.pdf")
        一時.write_bytes(pdf)
        頁数 = 変換(一時, 画像置き場 / 名)
        r["指紋"] = 指紋
        r["画像"] = [f"gomi_cal/{名}_{i}.png" for i in range(1, 頁数 + 1)]
        print(f"  {r['番号']} {頁数}頁を描いた", file=sys.stderr)
        一時.unlink()

    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": ページ,
        "年度": 年度,
        "件数": len(行たち),
        "地区表": 行たち,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    総画像 = sum(len(r.get("画像", [])) for r in 行たち)
    print(f"{len(行たち)}地区・画像{総画像}枚 → {出力}（{出力.stat().st_size//1024}KB）")
