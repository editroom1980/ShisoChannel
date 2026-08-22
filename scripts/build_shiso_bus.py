#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
バス時刻表（しーたんバス・大型バス・高速バス）の資料を作る。
出力: shiso_bus.json ＋ bus_cal/ フォルダのPNG画像（全ページ）

なぜ作るか（2026-08-22の実声テスト「どこのバス停からかわからない」への根治）：
  時刻表は32ページのPDF。文章にしても表の数字の並びは崩れるので、
  **時刻はページの画像で見せるのが確実**（ごみカレンダーと同じ考え方）。
  ページごとの文章も控えておき、質問の地名（山田・波賀など）が
  入っているページだけを選んで画面に出す。
  ページと画像の対応は機械が作る＝市が改訂しても手作業なしで追従する。

置き場の判断：
  ・画像は幅1600px（テレビで数字が読める精細さ。ごみカレンダーで実証済み）
  ・ページ文はそのまま保存（1ページ2千〜3千字。検索に使う）
"""
import json, re, time, sys, hashlib, subprocess, shutil, pathlib, urllib.request

根 = pathlib.Path(__file__).resolve().parent.parent
kb路 = 根 / "shiso_kb.json"
出力 = 根 / "shiso_bus.json"
画像置き場 = 根 / "bus_cal"
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app; contact via site)"
幅 = 1600


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
    req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
    with urllib.request.urlopen(req, timeout=90, context=_文脈) as r:
        return r.read()


def 時刻表のPDFを探す(kb):
    """kbの添付から、しーたんバス時刻表の本体PDFを見つける（改訂されても追従）"""
    for x in kb["項目"]:
        if "しーたんバス時刻表" not in x.get("題", ""):
            continue
        for a in x.get("添付", []):
            if a["名"].startswith("時刻表") and a["url"].lower().endswith(".pdf"):
                return a["url"], x.get("題", "")
    raise SystemExit("時刻表のPDFが見つからない（ページの作りが変わった）")


def 道具を用意():
    """ページ画像(pdf2png)とページ文(1ページずつ)の取り出し"""
    if shutil.which("pdftoppm") and shutil.which("pdftotext"):
        def 画像に(pdf, 頭):
            subprocess.run(["pdftoppm", "-png", "-r", "150", str(pdf), str(頭)], check=True)
            出た = sorted(頭.parent.glob(頭.name + "-*.png"))
            for i, p in enumerate(出た, 1):
                p.rename(頭.parent / f"{頭.name}_{i}.png")
            return len(出た)
        def 頁文(pdf, n):
            r = subprocess.run(["pdftotext", "-enc", "UTF-8", "-f", str(n), "-l", str(n),
                                str(pdf), "-"], capture_output=True, timeout=60)
            return r.stdout.decode("utf-8", "replace")
        return 画像に, 頁文, "poppler"
    # macOS: Swiftの道具（既存のpdf2png.swiftと、ページ文用の小さな相棒）
    if not shutil.which("swiftc"):
        raise SystemExit("道具が無い（poppler か swiftc が要る）")
    p2 = pathlib.Path("/tmp/shiso_pdf2png")
    src = 根 / "scripts" / "pdf2png.swift"
    if (not p2.exists()) or p2.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(src), "-o", str(p2)], check=True)
    pt = pathlib.Path("/tmp/shiso_pdfpage")
    swift = '''
import Foundation
import PDFKit
let doc = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1]))!
if CommandLine.arguments.count > 2, let n = Int(CommandLine.arguments[2]) {
    print(doc.page(at: n - 1)?.string ?? "")
} else { print(doc.pageCount) }
'''
    tmp = pathlib.Path("/tmp/shiso_pdfpage.swift")
    tmp.write_text(swift, encoding="utf-8")
    if (not pt.exists()) or True:
        subprocess.run(["swiftc", "-O", str(tmp), "-o", str(pt)], check=True)
    def 画像に(pdf, 頭):
        r = subprocess.run([str(p2), str(pdf), str(頭), str(幅)],
                           capture_output=True, text=True, check=True)
        return int(r.stdout.strip())
    def 頁文(pdf, n):
        r = subprocess.run([str(pt), str(pdf), str(n)], capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", "replace")
    return 画像に, 頁文, "PDFKit(Swift)"


def 整える(t):
    t = re.sub(r"[ \t　]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    return t.strip()[:4000]


if __name__ == "__main__":
    kb = json.loads(kb路.read_text(encoding="utf-8"))
    url, 親 = 時刻表のPDFを探す(kb)
    print(f"時刻表: {url}", file=sys.stderr)
    b = 取る(url)
    指紋 = hashlib.sha256(b).hexdigest()

    # 変わっていなければ何もしない（週1の自動更新で無駄な描き直しをしない）
    if 出力.exists():
        try:
            旧 = json.loads(出力.read_text(encoding="utf-8"))
            if 旧.get("指紋") == 指紋 and all((根 / p["画像"]).exists() for p in 旧.get("頁", [])):
                print("変化なし（前回のまま）")
                sys.exit(0)
        except Exception:
            pass

    一時 = pathlib.Path("/tmp/shiso_bus.pdf")
    一時.write_bytes(b)
    画像に, 頁文, 道具名 = 道具を用意()
    print(f"道具: {道具名}", file=sys.stderr)
    画像置き場.mkdir(exist_ok=True)
    頁数 = 画像に(一時, 画像置き場 / "bus")
    print(f"{頁数}ページを描いた", file=sys.stderr)

    頁たち = []
    for n in range(1, 頁数 + 1):
        文 = 整える(頁文(一時, n))
        頁たち.append({"n": n, "画像": f"bus_cal/bus_{n}.png", "文": 文})

    # 保存量の検算（絶対ルール30：取り込んだら量を検算する）
    総 = sum(len(p["文"]) for p in 頁たち)
    空 = sum(1 for p in 頁たち if len(p["文"]) < 50)
    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市公式サイト " + 親,
        "url": url, "指紋": 指紋, "頁数": 頁数,
        "問い合わせ": "ウイング神姫 山崎営業所 0790-62-1720",
        "頁": 頁たち,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{頁数}ページ・文章合計{総}字（文の無い頁 {空}）→ {出力}（{出力.stat().st_size//1024}KB）")
    if 頁数 < 20:
        print("★注意: ページ数が例年（32）より大幅に少ない。PDFの作りが変わった疑い", file=sys.stderr)
