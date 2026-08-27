#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""広報しそうの連載「宍粟 歴史 再発見」全44回を取り込む。
出力: shiso_rekishi.json

なぜ作るか（2026-08-28 ユーザーご指摘）：
  市が現役で公開しているのに、1件も取り込めていなかった。
  原因は収集器の除外が「/koho」という部分一致で、
  URLの途中の /kohoshiso/ にも当たり、広報のページを丸ごと捨てていたこと。
  黒田官兵衛と宍粟・播磨国風土記・宍粟藩・たたら製鉄など、
  宍粟の歴史そのものが44回分そろっている。市民が聞きたい話が詰まっている。

★まとめ版（年度ごと4冊）ではなく個別の44回を取る。
  同じ中身を二重に持たないため。
★取り込んだ回数と字数を検算する。
"""
import json, re, sys, time, subprocess, shutil, pathlib, urllib.request, importlib.util

根 = pathlib.Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("kb", 根/'scripts'/'build_shiso_kb.py')
kb = importlib.util.module_from_spec(_s); _s.loader.exec_module(kb)

出力 = 根 / "shiso_rekishi.json"
一覧 = ("https://www.city.shiso.lg.jp/soshiki/shichokoshitsu/hishokoho/"
        "tantojoho/kohoshiso/backnumber/1495438850507.html")
間 = 0.8


def 取り出し係():
    if shutil.which("pdftotext"):
        return lambda p: subprocess.run(["pdftotext", "-enc", "UTF-8", str(p), "-"],
                                        capture_output=True, timeout=180
                                        ).stdout.decode("utf-8", "replace")
    元 = 根 / "scripts" / "pdf2txt.swift"
    道具 = pathlib.Path("/tmp/shiso_pdf2txt")
    if shutil.which("swiftc"):
        if (not 道具.exists()) or 道具.stat().st_mtime < 元.stat().st_mtime:
            subprocess.run(["swiftc", "-O", str(元), "-o", str(道具)], check=True)
        return lambda p: subprocess.run([str(道具), str(p)], capture_output=True,
                                        timeout=180).stdout.decode("utf-8", "replace")
    raise SystemExit("PDFの文章を取り出す道具が無い")


def 整える(t):
    """★広報のPDFは縦書き・多段組みなので、
       1行が数文字で折り返され、漢字の間にも空白が入る（実測：
       「南 北 朝 時 代に赤 松 顕 則が築き、」）。
       そのまま読み上げると最初の行だけで切れる。文としてつなぎ直す"""
    t = t.replace("\u3000", " ")
    # 日本語の文字にはさまれた1つの空白は、組版の都合なので詰める
    for _ in range(3):
        t = re.sub(r"([ぁ-んァ-ヶ一-鿿]) ([ぁ-んァ-ヶ一-鿿])", r"\1\2", t)
    t = re.sub(r"[ \t]+", " ", t)
    # 行の終わりが句読点でなければ、次の行とつなぐ（折り返しをほどく）
    行 = [l.strip() for l in t.split("\n")]
    出, 今 = [], ""
    for l in 行:
        if not l:
            if 今: 出.append(今); 今 = ""
            continue
        今 = (今 + l) if 今 else l
        if 今.endswith(("。", "！", "？", "」", "）")):
            出.append(今); 今 = ""
    if 今: 出.append(今)
    t = "\n".join(出)
    # ★紙面の見出し（「宍粟歴史再発見〜 第11回 〜篠ノ丸城址の調査」）を落とす。
    #   資料の題としては持っているので、本文の頭に残すと読み上げが見出しから始まる
    t = re.sub(r"^宍粟\s*歴史\s*再発見\s*[〜～]?\s*第?\s*\d*\s*回?\s*[〜～]?\s*", "", t)
    return re.sub(r"\n{2,}", "\n", t).strip()


if __name__ == "__main__":
    h = kb.取る(一覧)
    n = re.findall(r'href="([^"]*?\.pdf)"[^>]*>([^<]{0,80})', h, re.I)
    回ら = []
    for u, t in n:
        名 = re.sub(r"\s*[（(]PDF[^）)]*[）)]", "", t).strip()
        # ★年度ごとのまとめ版は取らない（個別の回と同じ中身になる）
        if re.search(r"第\s*\d+\s*回\s*[～~]", 名):
            continue
        if not 名 or len(名) < 3:
            continue
        回ら.append({"url": urllib.request.urljoin(一覧, u), "題名": 名})
    print(f"個別の回 {len(回ら)}件を見つけた", file=sys.stderr)
    if len(回ら) < 30:
        print("★見つかった回が少なすぎる。ページの作りが変わった疑い", file=sys.stderr)
        sys.exit(1)

    取り出す, 項目, 取込, 落 = 取り出し係(), [], 0, []
    for i, r in enumerate(回ら):
        try:
            b = kb.取る一回(r["url"]) if False else urllib.request.urlopen(
                urllib.request.Request(r["url"], headers={"User-Agent": kb.名乗り}),
                timeout=90, context=kb._文脈).read()
        except Exception as e:
            落.append((r["題名"], str(e)[:40])); continue
        一時 = pathlib.Path("/tmp/shiso_rekishi.pdf"); 一時.write_bytes(b)
        try:
            文 = 整える(取り出す(一時))
        except Exception as e:
            落.append((r["題名"], f"取り出せない {e}")); continue
        time.sleep(間)
        if len(文) < 200:
            落.append((r["題名"], f"文章が短い {len(文)}字")); continue
        取込 += len(文)
        # ファイル名から掲載年月を取る（shisorekishihakken201304P28.pdf）
        m = re.search(r"((?:19|20)\d{2})(\d{2})", r["url"])
        号 = f"{m.group(1)}年{int(m.group(2))}月号" if m else ""
        m2 = re.search(r"^(\d+)", r["url"].rsplit("/", 1)[-1])
        項目.append({"題": "宍粟 歴史 再発見　" + r["題名"],
                     "題名": r["題名"], "掲載": 号, "文": 文, "url": r["url"]})
        print(f"  {i+1}/{len(回ら)} {r['題名'][:30]} … {len(文):,}字", file=sys.stderr)

    if len(項目) < 30:
        print(f"★{len(項目)}回しか取り込めなかった", file=sys.stderr); sys.exit(1)
    項目.sort(key=lambda x: x["掲載"])
    字 = sum(len(x["文"]) for x in 項目)
    出力.write_text(json.dumps({
        "説明": "広報しそうの連載「宍粟 歴史 再発見」。宍粟の歴史を市が44回に分けて書いたもの",
        "出典": "宍粟市公式サイト 広報しそう「宍粟 歴史 再発見」",
        "url": 一覧, "件数": len(項目), "項目": 項目,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n○ {len(項目)}回・{字:,}字 → {出力}（{出力.stat().st_size//1024}KB）")
    print(f"検算: PDFから取り出した {取込:,}字 / 保存 {字:,}字（{100*字//max(取込,1)}%）")
    print(f"  掲載年月が取れた回: {sum(1 for x in 項目 if x['掲載'])}/{len(項目)}")
    if 落:
        print(f"！ 取れなかった {len(落)}回: {[t for t,_ in 落[:5]]}")
