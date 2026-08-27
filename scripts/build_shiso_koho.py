#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
広報しそう（市の広報紙）の中身を文章にする。
出力: shiso_koho.json

なぜ作るか（2026-08-27）：
  市民にいちばん身近な情報源なのに、資料に1冊も入っていなかった。
  行事の詳報・制度の解説・市長のことば・地域の話題が、
  ウェブの記事にならず広報紙にだけ載っていることが多い。

★1冊6MB前後・数十ページある。全文を持つと重いので、
  直近の号だけを対象にし、1冊を塊に分けて保存する。
出典：宍粟市公式サイト「広報しそう」
"""
import json, re, sys, time, html, subprocess, shutil, pathlib, urllib.request

根 = pathlib.Path(__file__).resolve().parent.parent
出力 = 根 / "shiso_koho.json"
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app)"
一覧 = "https://www.city.shiso.lg.jp/soshiki/shichokoshitsu/hishokoho/tantojoho/kohoshiso/index.html"
年度一覧 = "https://www.city.shiso.lg.jp/soshiki/shichokoshitsu/hishokoho/tantojoho/kohoshiso/backnumber/"
何冊 = int(sys.argv[1]) if len(sys.argv) > 1 else 12   # 直近の号数
一片 = 6000
最大片 = 8
間 = 0.8


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


def 取る(url, 生=False):
    最後 = None
    for 再 in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
            with urllib.request.urlopen(req, timeout=60, context=_文脈) as r:
                b = r.read()
                return b if 生 else b.decode("utf-8", "ignore")
        except Exception as e:
            最後 = e
            if 再 < 2:
                time.sleep(3 * (再 + 1))
    raise 最後


def 取り出し係():
    if shutil.which("pdftotext"):
        def f(p):
            r = subprocess.run(["pdftotext", "-enc", "UTF-8", str(p), "-"],
                               capture_output=True, timeout=180)
            return r.stdout.decode("utf-8", "replace")
        return f, "pdftotext"
    元 = 根 / "scripts" / "pdf2txt.swift"
    道具 = pathlib.Path("/tmp/shiso_pdf2txt")
    if shutil.which("swiftc"):
        if (not 道具.exists()) or 道具.stat().st_mtime < 元.stat().st_mtime:
            subprocess.run(["swiftc", "-O", str(元), "-o", str(道具)], check=True)
        def f(p):
            r = subprocess.run([str(道具), str(p)], capture_output=True, timeout=180)
            return r.stdout.decode("utf-8", "replace")
        return f, "PDFKit(Swift)"
    raise SystemExit("PDFの文章を取り出す道具が無い")


def 整える(t):
    t = re.sub(r"[ \t　]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    return re.sub(r"\n{2,}", "\n", t).strip()


def 分ける(t):
    if len(t) <= 一片:
        return [t]
    out, 今, 長 = [], [], 0
    for 行 in t.split("\n"):
        if 長 + len(行) > 一片 and 今:
            out.append("\n".join(今)); 今, 長 = [], 0
            if len(out) >= 最大片: break
        今.append(行); 長 += len(行) + 1
    if 今 and len(out) < 最大片: out.append("\n".join(今))
    while len(out) >= 2 and len(out[-1].strip()) < 200:
        末 = out.pop(); out[-1] += "\n" + 末
    return out


def URLを直す(u):
    """相対・プロトコル相対のURLを、たどれる形に直す。
       ★市のサイトのhrefは「//www.city.shiso.lg.jp/...」の形（プロトコル相対）。
         先頭が「/」だからと機械的に足すと
         「https://www.city.shiso.lg.jp//www.city.shiso.lg.jp/...」になって404
         （2026-08-27の実測。58冊見つけて1冊も取れなかった）"""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return "https://www.city.shiso.lg.jp" + u
    return u


def 号を集める():
    """今月号＋年度別のバックナンバーからPDFのURLを集める"""
    出 = []
    見 = set()
    頁ら = [一覧]
    try:
        h = 取る(一覧)
        for m in re.finditer(r'href="([^"]*backnumber/\d+\.html)"', h):
            u = URLを直す(m.group(1))
            if u not in 頁ら:
                頁ら.append(u)
    except Exception as e:
        print(f"  一覧が読めない {e}", file=sys.stderr)
    for p in 頁ら:
        try:
            h = 取る(p)
        except Exception:
            continue
        time.sleep(間)
        for m in re.finditer(r'href="([^"]+\.pdf)"[^>]*>([^<]{0,60})', h, re.I):
            u, 名 = URLを直す(m.group(1)), html.unescape(m.group(2)).strip()
            if u in 見:
                continue
            # 広報紙の本体だけ（広告募集・要綱などは除く）
            if not re.search(r"koho|広報しそう", u + 名, re.I):
                continue
            if re.search(r"広告|要綱|要領|申請|掲示板", 名):
                continue
            見.add(u)
            出.append({"url": u, "名": re.sub(r"[（(]PDF[^）)]*[）)]", "", 名).strip()})
    return 出


if __name__ == "__main__":
    号ら = 号を集める()
    print(f"広報しそう {len(号ら)}冊を見つけた", file=sys.stderr)
    if not 号ら:
        print("★1冊も見つからない。ページの作りが変わった可能性", file=sys.stderr)
        sys.exit(1)
    # 新しい号を優先（ファイル名の年月が大きい順）
    def 年月(x):
        m = re.search(r"(20\d{2})(\d{2})", x["url"])
        return int(m.group(0)) if m else 0
    号ら.sort(key=年月, reverse=True)
    号ら = 号ら[:何冊]

    取り出す, 道具名 = 取り出し係()
    print(f"取り出しの道具: {道具名}", file=sys.stderr)
    項目 = []
    for i, r in enumerate(号ら):
        try:
            b = 取る(r["url"], 生=True)
        except Exception as e:
            print(f"  読めない {r['名'][:30]} {e}", file=sys.stderr)
            continue
        time.sleep(間)
        一時 = pathlib.Path("/tmp/shiso_koho.pdf")
        一時.write_bytes(b)
        try:
            文 = 整える(取り出す(一時))
        except Exception as e:
            print(f"  取り出せない {r['名'][:30]} {e}", file=sys.stderr)
            continue
        if len(文) < 500:
            continue
        m = re.search(r"(20\d{2})(\d{2})", r["url"])
        号 = f"{m.group(1)}年{int(m.group(2))}月号" if m else r["名"]
        片ら = 分ける(文)
        for k, 片 in enumerate(片ら, 1):
            付 = "" if len(片ら) == 1 else f"（{k}/{len(片ら)}）"
            項目.append({"題": f"広報しそう {号}{付}", "号": 号,
                         "文": 片, "url": r["url"]})
        print(f"  {i+1}/{len(号ら)} {号} … {len(文):,}字", file=sys.stderr)

    if not 項目:
        print("★中身を取り出せなかった", file=sys.stderr)
        sys.exit(1)
    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市公式サイト「広報しそう」",
        "冊数": len({x["号"] for x in 項目}),
        "件数": len(項目),
        "項目": 項目,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    字 = sum(len(x["文"]) for x in 項目)
    print(f"{len({x['号'] for x in 項目})}冊・{len(項目)}片・{字:,}字 → {出力}"
          f"（{出力.stat().st_size//1024}KB）")
