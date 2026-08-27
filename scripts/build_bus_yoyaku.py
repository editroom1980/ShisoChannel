#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""予約制の交通（デマンド）を集めて shiso_bus.json に「予約制の交通」として書く。

なぜ作るか（2026-08-27 ユーザー指摘「千種町も」）：
  千種町の集落（岩野辺・鷹巣・河呂・黒土・七野・下河野・千草・西山）は、
  しーたんバスの時刻表に**1つも載っていない**（文にも表にも0件）。
  「千種町のバス停は」と聞かれて4停しか出せないのは、答えとして間違い。
  調べたら、千種町内は路線バスではなく
  **ちくさええとこバス（完全予約制）**が全域を走っていた。
  一宮北部の三方・繁盛地区も同じく**三方繁盛つれてってカー**。

  時刻表PDFの59-60ページは2段組みで、文章にすると2つの案内が混ざる。
  料金がどちらのものか確定できなかったため、
  **それぞれの専用PDF**（市が別ファイルで出している）から取る。

★見出しは市のPDFに実際に書かれている言葉（乗車料金・運行日時・利用方法…）。
  こちらで文章を作らない。見出しが見つからなければ、その欄は空にして報告する。
"""
import json, re, subprocess, shutil, sys, time, pathlib, urllib.request

根 = pathlib.Path(__file__).resolve().parent.parent
BUS = 根 / "shiso_bus.json"
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app)"
元 = "https://www.city.shiso.lg.jp/material/files/group/37/"

対象 = [
    {"名前": "ちくさええとこバス", "file": "r8chikusaeetoko.pdf",
     "区域": "千種町内全域", "町": ["千種町"],
     "呼び名": ["ちくさええとこ", "千種町のバス", "ちくさバス"]},
    {"名前": "三方繁盛つれてってカー", "file": "r8mikatahanse.pdf",
     "区域": "一宮北部の三方地区・繁盛地区", "町": ["一宮町"],
     "呼び名": ["つれてってカー", "三方繁盛", "みかたはんせ"]},
]

# PDFに実際に書かれている見出し（この言葉で切り出す）
見出しら = ["乗車料金", "運行日時", "利用方法", "乗降場所", "指定降車場所",
            "予約受付時間", "その他"]


def _ssl():
    try:
        import ssl, certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        import ssl
        return ssl.create_default_context()


def 取る(url):
    req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
    with urllib.request.urlopen(req, timeout=60, context=_ssl()) as r:
        return r.read()


def 取り出し係():
    if shutil.which("pdftotext"):
        return lambda p: subprocess.run(["pdftotext", "-enc", "UTF-8", str(p), "-"],
                                        capture_output=True, timeout=120
                                        ).stdout.decode("utf-8", "replace")
    元s = 根 / "scripts" / "pdf2txt.swift"
    道具 = pathlib.Path("/tmp/shiso_pdf2txt")
    if shutil.which("swiftc"):
        if (not 道具.exists()) or 道具.stat().st_mtime < 元s.stat().st_mtime:
            subprocess.run(["swiftc", "-O", str(元s), "-o", str(道具)], check=True)
        return lambda p: subprocess.run([str(道具), str(p)], capture_output=True,
                                        timeout=120).stdout.decode("utf-8", "replace")
    raise SystemExit("PDFの文章を取り出す道具が無い")


def 欄に切る(文):
    """見出しごとに切り分ける。見出しはPDFに書かれている言葉そのもの"""
    位置 = []
    for h in 見出しら:
        for m in re.finditer(r"^\s*" + re.escape(h) + r"\s*", 文, re.M):
            位置.append((m.start(), m.end(), h))
    位置.sort()
    出 = {}
    for i, (s, e, h) in enumerate(位置):
        終 = 位置[i + 1][0] if i + 1 < len(位置) else len(文)
        中 = 文[e:終].strip()
        中 = re.sub(r"\s*\n\s*", " ", 中)
        中 = re.sub(r"\s{2,}", " ", 中)
        中 = re.sub(r"\s*\d+\s*$", "", 中).strip()      # 末尾のページ番号
        if 中 and (h not in 出 or len(中) > len(出[h])):
            出[h] = 中
    return 出


def 電話を拾う(文):
    n = re.findall(r"0\d{1,3}[-−－]\d{2,4}[-−－]\d{3,4}", 文)
    return n[0].replace("−", "-").replace("－", "-") if n else ""


if __name__ == "__main__":
    取り出す = 取り出し係()
    出 = []
    欠け = []
    for t in 対象:
        url = 元 + t["file"]
        try:
            b = 取る(url)
        except Exception as e:
            print(f"！{t['名前']} が取れない {e}", file=sys.stderr); sys.exit(1)
        一時 = pathlib.Path("/tmp/shiso_yoyaku.pdf")
        一時.write_bytes(b)
        文 = 取り出す(一時)
        time.sleep(0.8)
        if len(文) < 200:
            print(f"！{t['名前']} の文章が短すぎる（{len(文)}字）", file=sys.stderr); sys.exit(1)
        欄 = 欄に切る(文)
        r = dict(t); r.pop("file")
        r["url"] = url
        r["電話"] = 電話を拾う(文)
        r["文"] = re.sub(r"\s*\n\s*", " ", 文).strip()
        for h in 見出しら:
            if h in 欄:
                r[h] = 欄[h]
        # 案内の骨になる欄が無ければ知らせる（黙って空で出さない）
        for 要 in ("乗車料金", "運行日時"):
            if 要 not in r:
                欠け.append(f"{t['名前']}に「{要}」が無い")
        if not r["電話"]:
            欠け.append(f"{t['名前']}に電話番号が無い")
        出.append(r)
        print(f"○ {t['名前']}（{len(文)}字）")
        for h in 見出しら:
            if h in r:
                print(f"    {h}: {r[h][:88]}")
        print(f"    電話: {r['電話']}")

    if 欠け:
        print("！ 足りない欄: " + " / ".join(欠け), file=sys.stderr)
        sys.exit(1)

    bus = json.loads(BUS.read_text(encoding="utf-8"))
    bus["予約制の交通"] = 出
    BUS.write_text(json.dumps(bus, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"\n○ shiso_bus.json に「予約制の交通」{len(出)}件を書いた"
          f"（{BUS.stat().st_size//1024}KB）")
