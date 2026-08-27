#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""広報しそうの古い号（市のサイトから消えた分）を集める。
出力: shiso_koho_kako.json

なぜ作るか（2026-08-28のご指示）：
  「広報しそうの内容はかなり強力なデータベースになるはず。
    宍粟市が合併して誕生後の推移が分析できるはず」

  市の公式サイトのバックナンバーは**令和3年度までしか無い**。
  それ以前のページもPDFも消えている（実測：404）。
  ところがインターネット・アーカイブに、
  旧サイトのバックナンバーのページとPDF本体が残っていた。

  取れる範囲を実測で確かめた結果：
    平成29年度（2017）〜令和2年度（2020） … 4年度・50冊
    平成28年度以前 … アーカイブにもページが保存されておらず取れない

★アーカイブのURLは「id_」を付けて元のファイルそのものを取る
  （付けないとアーカイブの枠が付いたHTMLになる）。
★取れた冊数・字数を検算して出す。取れなかった号は名前を出して報告する。
"""
import json, re, sys, time, subprocess, shutil, pathlib, urllib.request

根 = pathlib.Path(__file__).resolve().parent.parent
出力 = 根 / "shiso_koho_kako.json"
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app)"

# 旧サイトのバックナンバー（アーカイブに残っている時点を指定）
年度ら = [
    ("平成29年度", "20211026160346", "kikakusomu/hishokoho/tantojoho/kohoshiso/backnumber/h29nendo.html"),
    ("平成30年度", "20211026152008", "kikakusomu/hishokoho/tantojoho/kohoshiso/backnumber/2018kohoshiso.html"),
    ("令和元年度", "20211026153444", "kikakusomu/hishokoho/tantojoho/kohoshiso/backnumber/H31_kohoshiso.html"),
    ("令和2年度",  "20211026143808", "kikakusomu/hishokoho/tantojoho/kohoshiso/backnumber/10304.html"),
]
基 = "https://www.city.shiso.lg.jp/soshiki/"
一片, 最大片, 間 = 6000, 30, 1.0


def _ssl文脈():
    """★証明書の指定を忘れると、この端末では全部つながらない（2026-08-28の失敗）。
       ほかの収集器はみな certifi を使っている。同じ作法に揃える"""
    try:
        import ssl, certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        import ssl
        return ssl.create_default_context()


_文脈 = _ssl文脈()


def 取る(url, 生=False, 秒=90):
    最後 = None
    for 再 in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
            with urllib.request.urlopen(req, timeout=秒, context=_文脈) as r:
                b = r.read()
                return b if 生 else b.decode("utf-8", "replace")
        except Exception as e:
            最後 = e
            if 再 < 2: time.sleep(4 * (再 + 1))
    raise 最後


def 一番大きい保存(url):
    """そのPDFの保存時点を、大きい順に返す。
    ★アーカイブは大きなファイルを1MBで切って保存していることがある（実測）。
      切れた保存に当たると文章が1字も取れない。
      先に長さを調べ、大きい方から試す"""
    u = url.replace("https://", "").replace("http://", "")
    try:
        r = 取る(f"https://web.archive.org/cdx/search/cdx?url={u}"
                 "&output=json&fl=timestamp,statuscode,length", 秒=60)
        v = json.loads(r)
    except Exception:
        return [("2021", 0)]
    出 = []
    for row in v[1:]:
        if len(row) < 3 or row[1] != "200": continue
        try: 出.append((row[0], int(row[2])))
        except ValueError: pass
    出.sort(key=lambda x: -x[1])
    return 出 if 出 else [("2021", 0)]


def 取り出し係():
    if shutil.which("pdftotext"):
        return lambda p: subprocess.run(["pdftotext", "-enc", "UTF-8", str(p), "-"],
                                        capture_output=True, timeout=300
                                        ).stdout.decode("utf-8", "replace")
    元 = 根 / "scripts" / "pdf2txt.swift"
    道具 = pathlib.Path("/tmp/shiso_pdf2txt")
    if shutil.which("swiftc"):
        if (not 道具.exists()) or 道具.stat().st_mtime < 元.stat().st_mtime:
            subprocess.run(["swiftc", "-O", str(元), "-o", str(道具)], check=True)
        return lambda p: subprocess.run([str(道具), str(p)], capture_output=True,
                                        timeout=300).stdout.decode("utf-8", "replace")
    raise SystemExit("PDFの文章を取り出す道具が無い")


def 号を集める():
    出, 見 = [], set()
    for 名, 時, path in 年度ら:
        u = f"https://web.archive.org/web/{時}/{基}{path}"
        try:
            h = 取る(u)
        except Exception as e:
            print(f"  ！{名}の一覧が読めない {e}", file=sys.stderr); continue
        time.sleep(間)
        n = 0
        for a, t in re.findall(r'href="([^"]*?\.pdf)"[^>]*>([^<]{0,70})', h, re.I):
            m = re.search(r"(https?://www\.city\.shiso\.lg\.jp/[^\"]+\.pdf)", a)
            if not m or "広報" not in t: continue
            元 = m.group(1)
            if 元 in 見: continue
            見.add(元)
            出.append({"url": 元, "名": re.sub(r"[（(]PDF[^）)]*[）)]", "", t).strip(),
                      "年度": 名})
            n += 1
        print(f"  {名}: {n}冊", file=sys.stderr)
    return 出


def 号の名前(名, url):
    m = re.search(r"(平成|令和)\s*(\d+|元)\s*年\s*(\d+)\s*月", 名)
    if m:
        元 = 1 if m.group(2) == "元" else int(m.group(2))
        西 = (1988 + 元) if m.group(1) == "平成" else (2018 + 元)
        return f"{西}年{int(m.group(3))}月号"
    m = re.search(r"shiso_((?:19|20)\d{2})_(\d{1,2})", url)
    if m: return f"{m.group(1)}年{int(m.group(2))}月号"
    m = re.search(r"((?:19|20)\d{2})(\d{2})", url)
    if m: return f"{m.group(1)}年{int(m.group(2))}月号"
    return 名


def 整える(t):
    t = re.sub(r"[ \t　]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    return re.sub(r"\n{2,}", "\n", t).strip()


def 分ける(t):
    if len(t) <= 一片: return [t]
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


if __name__ == "__main__":
    号ら = 号を集める()
    print(f"古い号 {len(号ら)}冊を見つけた", file=sys.stderr)
    if len(号ら) < 30:
        print("★見つかった数が少なすぎる。アーカイブの作りが変わった疑い", file=sys.stderr)
        sys.exit(1)
    取り出す, 項目, 取込, 落 = 取り出し係(), [], 0, []
    for i, r in enumerate(号ら):
        # ★どの保存時点がいちばん大きいかを先に調べてから取る（2026-08-28の根治）。
        #   時点を指定せずに取ると、2021年の**1MBで切れた保存**に当たり、
        #   14冊が「文章0字」になっていた。
        #   同じPDFでも2024年の保存には7.7MB全部が残っている
        b = None
        for 時, 大 in 一番大きい保存(r["url"]):
            try:
                b2 = 取る(f"https://web.archive.org/web/{時}id_/{r['url']}", 生=True, 秒=240)
            except Exception as e:
                continue
            # ★1MBちょうどは「切れた保存」の印。次の時点を試す
            if len(b2) == 1048576:
                print(f"    （{時} は1MBで切れている。別の保存を試す）", file=sys.stderr)
                continue
            if b2[:5].startswith(b"%PDF") and len(b2) > 100000:
                b = b2; break
        if b is None:
            落.append((r["名"], "どの保存時点からも取れない")); continue
        一時 = pathlib.Path("/tmp/shiso_koho_kako.pdf"); 一時.write_bytes(b)
        try:
            文 = 整える(取り出す(一時))
        except Exception as e:
            落.append((r["名"], f"取り出せない {e}")); continue
        time.sleep(間)
        if len(文) < 500:
            落.append((r["名"], f"文章が短い {len(文)}字")); continue
        取込 += len(文)
        号 = 号の名前(r["名"], r["url"])
        片ら = 分ける(文)
        for k, 片 in enumerate(片ら, 1):
            付 = "" if len(片ら) == 1 else f"（{k}/{len(片ら)}）"
            項目.append({"題": f"広報しそう {号}{付}", "号": 号, "年度": r["年度"],
                         "文": 片, "url": r["url"], "出典": "インターネット・アーカイブ"})
        print(f"  {i+1}/{len(号ら)} {号} … {len(文):,}字", file=sys.stderr)

    if not 項目:
        print("★1冊も取り込めなかった", file=sys.stderr); sys.exit(1)
    # 見出し語（本編の収集器と同じ処理を使う。同じものを2か所に持たない）
    import importlib.util
    _s = importlib.util.spec_from_file_location("koho", 根/'scripts'/'build_shiso_koho.py')
    koho = importlib.util.module_from_spec(_s); _s.loader.exec_module(koho)
    koho.見出しを付ける(項目)

    字 = sum(len(x["文"]) for x in 項目)
    出力.write_text(json.dumps({
        "説明": "広報しそうの古い号（市のサイトから消えた分。アーカイブより）",
        "出典": "宍粟市公式サイトの旧バックナンバー（Internet Archive 経由）",
        "冊数": len({x["号"] for x in 項目}), "件数": len(項目), "項目": 項目,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n○ {len({x['号'] for x in 項目})}冊・{len(項目)}片・{字:,}字 → {出力}"
          f"（{出力.stat().st_size//1024}KB）")
    print(f"検算: PDFから取り出した {取込:,}字 / 保存 {字:,}字（{100*字//max(取込,1)}%）")
    if 落:
        print(f"！ 取れなかった {len(落)}冊:")
        for 名, 理 in 落[:10]: print(f"    {名[:34]} … {理}")
