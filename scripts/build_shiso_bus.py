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
import time
import json, math, re, time, sys, hashlib, subprocess, shutil, pathlib, urllib.request

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


# ══ 時刻の格子の復元（2026-08-23）══════════════════════════
#  「どこからどこまで」に**乗れる時刻**で答えるため、ページ画像だけでなく
#  停留所×便の表そのものを持つ。文字の並びでは表が崩れるので、
#  紙の上の座標（scripts/pdfwords.swift / pdftotext -bbox）から組み直す。
#  検算：バスは先へ進むほど時刻が遅い。**各便の列が上から下へ増えていること**を
#  確かめ、崩れた列は捨てる（並び順の取り違えを機械が自分で見つける）。

時刻型 = re.compile(r"^(\d{1,2}):(\d{2})$")


def 語々を取る(pdf, n):
    """1ページの語を (語, x, y) で返す"""
    out = []
    if shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-bbox", "-f", str(n), "-l", str(n), str(pdf), "-"],
                           capture_output=True, timeout=60)
        for m in re.finditer(
                r'<word xMin="([\d.]+)" yMin="([\d.]+)"[^>]*>([^<]+)</word>',
                r.stdout.decode("utf-8", "replace")):
            out.append((m.group(3), float(m.group(1)), float(m.group(2))))
        return out
    道具 = pathlib.Path("/tmp/shiso_pdfwords")
    src = 根 / "scripts" / "pdfwords.swift"
    if (not 道具.exists()) or 道具.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(src), "-o", str(道具)], check=True)
    r = subprocess.run([str(道具), str(pdf), str(n)], capture_output=True, timeout=60)
    for 行 in r.stdout.decode("utf-8", "replace").splitlines():
        p = 行.split("\t")
        if len(p) >= 3:
            try:
                out.append((p[0], float(p[1]), float(p[2])))
            except ValueError:
                pass
    return out


def 分(t):
    m = 時刻型.match(t)
    return int(m.group(1)) * 60 + int(m.group(2))


# 頁の見出し「運行日 ◯曜日」の言い方 → 保存する運行日の名前。
# ★2026-08-23の点検で発覚：火曜だけの路線（梯河東線）等8頁を「平日」と
#   保存しており、走らない曜日に「運行あり」と誤答していた。
#   頁自身が名乗る運行日を最優先で使う
運行日の言い方 = (
    ("月・水・金", "月水金"), ("火・木", "火木"), ("月・木", "月木"),
    ("月・水", "月水"), ("火・金", "火金"),
    ("月〜土", "月〜土"), ("月～土", "月〜土"),
    ("月〜金", "平日"), ("月～金", "平日"),
    ("土日祝", "土日祝"), ("火曜", "火"), ("水曜", "水"), ("金曜", "金"),
    ("平 日", "平日"), ("平日", "平日"),
)


def 運行日を読む(頁文):
    """そのページの便が走る日。誤った日の便を案内しないために持つ（2026-08-23）"""
    休 = "（祝日運休）" if ("祝日運休" in 頁文 or "祝日除く" in 頁文) else ""
    # 頁の見出し「運行日 ◯曜日」が最優先（頁が自分で名乗っている）。
    # ★語の並び順の都合で文の後ろに現れる頁がある（p13・p14で実測）ため全文を見る
    m = re.search(r"運行日[ 　]*([^\n]{1,20})", 頁文)
    if m:
        for 語, 名 in 運行日の言い方:
            if 語 in m.group(1):
                return 名 + ("" if "（" in 名 else 休)
    for 語, 名 in 運行日の言い方:
        if 語 in 頁文[:800]:
            return 名 + 休
    return "平日" + 休


def 路線名を拾う(語々, 頁文):
    """ページ左上の見出し（x≈69, y≈35）にある路線名。
       ★左右の端（x<40, x>700）は全路線の索引タブなので拾わない（実測で確認）
       ★「梯河東線（三谷経由）」のように経由が付くと『線』で終わらず
         拾い漏れていた（2026-08-23の点検で発覚）。括弧を外して判定する"""
    候補 = [(語, x, y) for 語, x, y in 語々
            if re.sub(r"[（(][^（()）]*[)）]$", "", 語).endswith("線")
            and 40 < x < 700 and y < 90]
    if 候補:
        return min(候補, key=lambda w: w[2])[0]
    if "大型バス" in 頁文[:60]: return "大型バス"
    if "高速バス" in 頁文[:60]: return "高速バス"
    return ""


def 日の札を拾う(語々):
    """ページの中で「平日」「土日祝」等が書かれている位置（x,y）を集める。
       ★1ページに平日と土日祝が同居する（p7で実測）。表ごとに近い札を採るため
       ★p8（循環線）は「月曜日から金曜日（祝日除く）」と「土曜日・祝日」の
         2表（2026-08-23の点検で発覚）。土曜日・祝日＝日曜は走らない（土祝）"""
    札 = []
    語順 = sorted(語々, key=lambda w: (w[2], w[1]))
    for i, (語, x, y) in enumerate(語順):
        つなぎ = 語
        for k in range(1, 4):        # 「平 日」のように割れることがある
            if i + k < len(語順) and abs(語順[i+k][2] - y) <= 3:
                つなぎ += 語順[i+k][0]
        for 形, 名 in (("土日祝", "土日祝"), ("土曜日・祝日", "土祝"),
                       ("月・水・金", "月水金"), ("火・木", "火木"),
                       ("月曜日から金曜日", "平日（祝日運休）"),
                       ("平日", "平日")):
            if つなぎ.startswith(形):
                札.append((名, x, y)); break
    return 札


def 近い札(札たち, x, y, 既定):
    """その表の運行日の札を採る。札は表の【上】に書かれるので、
       表の上端より上にある札のうちいちばん近いものを最優先にする
       （単純な最短距離だと、下の表の札を上の表が拾うことがある）"""
    if not 札たち:
        return 既定
    上側 = [s for s in 札たち if s[2] <= y + 6]
    if 上側:
        return max(上側, key=lambda s: s[2] - abs(s[1] - x) * 0.05)[0]
    return min(札たち, key=lambda s: abs(s[2] - y) + abs(s[1] - x) * 0.3)[0]


# ★停留所ではない注記（2026-08-23の点検で発見）。
#   「山崎行き連絡便の東市場発時刻 7:34…」のように、乗り継ぎ先の
#   **別のバス**の発時刻を知らせる案内文が、停留所の行に混ざる。
#   同じ便の列に残すと「乗り換え無しで行ける」という嘘の続きになるため、
#   行ごと捨てる。連絡便の時刻は本物の路線の格子（p3・p5等）に全て
#   載っていることを検算済み（2026-08-23）。乗り換え探索がそちらを使う。
注記の型 = re.compile(r"(発時刻|連絡便|参照|凡例|注意|ページ|^[−ー-]+$)")


def 格子を組む(語々):
    """語の座標から「停留所×便」の表を組む。1ページに複数の表（往路/復路）があってよい"""
    # 行にまとめる（yが近い語は同じ行）
    行たち = []
    for 語, x, y in sorted(語々, key=lambda w: (w[2], w[1])):
        for r in 行たち:
            if abs(r["y"] - y) <= 3:
                r["語"].append((語, x)); break
        else:
            行たち.append({"y": y, "語": [(語, x)]})
    表たち = []
    # 各行で「時刻セル」と「その左隣の名前セル」を対にする
    対たち = []   # (名前, 名x, 時刻, 時x, y)
    for r in 行たち:
        名前セル = [(w, x) for w, x in r["語"] if not 時刻型.match(w) and re.search(r"[぀-ゟ゠-ヿ一-鿿]", w)]
        for w, x in r["語"]:
            if not 時刻型.match(w):
                continue
            左 = [(nw, nx) for nw, nx in 名前セル if nx < x]
            if not 左:
                continue
            nw, nx = max(左, key=lambda p: p[1])
            対たち.append((nw, nx, w, x, r["y"]))
    if not 対たち:
        return []
    # 名前の列（x）ごとに1つの表とみなす
    名列たち = []
    for _, nx, _, _, _ in 対たち:
        for c in 名列たち:
            if abs(c - nx) <= 12: break
        else:
            名列たち.append(nx)
    # 各行の文字（時刻以外）を上から順に並べ、前後の行の文脈を引けるようにする。
    # 「山崎行き連絡便の / はりま一宮小学校 / 前発時刻」と3行に割れた注記の、
    # 真ん中の断片を見抜くため（p23・p29で実測。2026-08-23）
    行順 = sorted(行たち, key=lambda r: r["y"])
    行文々 = ["".join(w for w, _ in sorted(r["語"], key=lambda p: p[1])
                     if not 時刻型.match(w)) for r in 行順]
    文脈 = {}
    for i, r in enumerate(行順):
        文脈[round(r["y"] / 3)] = (行文々[i - 1] if i > 0 else "",
                                   行文々[i + 1] if i + 1 < len(行文々) else "")
    for 名x in 名列たち:
        全部 = [p for p in 対たち if abs(p[1] - 名x) <= 12]
        for こ in 上下に分ける(全部):
            表 = 表を組む(こ, 名x, 文脈)
            if 表:
                表たち.append(表)
    return 表たち


def 上下に分ける(全部):
    """同じ名前列に上下へ積まれた【別々の表】を切り分ける。

    ★見分け方は「隙間の大きさ」ではなく **停留所の並びが最初から繰り返されるか**
      （2026-08-23の点検で発覚した重大な誤り）。
      隙間で切ると、p3（山崎発 一宮・波賀方面）の『道谷・戸倉』のように
      時刻を持たない停留所の空白を表の切れ目と誤判定し、
      **1本で行ける23停の路線を2つに割ってしまう**。
      割れると「山崎から倉床へ」が乗り換え扱いになり、
      実際には乗ったままでよいのに降りて待てと案内する（致命的な誤案内）。
      往路と復路・平日と土曜祝日が積まれている頁（p7・p8・p28）は、
      下の塊が上の塊と同じ停留所を頭から繰り返すので、そこで切る。
    """
    行 = []            # (行の位置キー, 停名, その行の対たち)
    見た = {}
    for p in sorted(全部, key=lambda p: p[4]):
        鍵 = round(p[4] / 3)
        if 鍵 not in 見た:
            見た[鍵] = len(行); 行.append([鍵, p[0], []])
        行[見た[鍵]][2].append(p)
    if not 行:
        return []
    # ① まず「行の縦の隙間」が普段より大きく開く所を候補にする
    隙間 = [(行[i + 1][0] - 行[i][0]) * 3 for i in range(len(行) - 1)]
    if not 隙間:
        return [[p for _, _, 対 in 行 for p in 対]]
    並み = sorted(隙間)[len(隙間) // 2]
    候補 = [i + 1 for i, g in enumerate(隙間) if 並み > 0 and g > max(2.5 * 並み, 30)]
    # ② 候補のうち「その先で停留所の並びが繰り返される」所だけを本当の切れ目とする。
    #    隙間だけで切ると、時刻を持たない停留所（p3の道谷・戸倉）の空白を
    #    切れ目と誤判定し、1本で行ける路線を割ってしまう＝乗り換えの誤案内になる。
    #    繰り返しだけで切ると、循環線のように同じ停を2度通る1本の便を割ってしまう。
    切れ目 = []
    始め = 0
    for c in 候補 + [len(行)]:
        if c == len(行):
            break
        前 = set(s for _, s, _ in 行[始め:c])
        後 = [s for _, s, _ in 行[c:min(c + 6, len(行))]]
        if sum(1 for s in 後 if s in 前) >= 2:
            切れ目.append(c); 始め = c
    群, 前切 = [], 0
    for c in 切れ目 + [len(行)]:
        if c > 前切:
            群.append([p for _, _, 対 in 行[前切:c] for p in 対])
        前切 = c
    return 群


def 表を組む(こ, 名x, 文脈):
    """1つの塊（行の集まり）から表を1枚組む。組めなければ None"""
    # 停留所（行）を上から順に。
    # ★名前でなく「行の位置」で束ねる（2026-08-23実測：水谷線は同じ停留所を
    #   2回通るため、名前で束ねると時刻の並びが壊れて表ごと捨てられていた）
    停順, 行キー, 見た = [], [], {}
    for nw, _, _, _, y in sorted(こ, key=lambda p: p[4]):
        鍵 = round(y / 3)
        if 鍵 not in 見た:
            見た[鍵] = len(停順); 停順.append(nw); 行キー.append(鍵)
    # 注記の行（連絡便の発時刻など）は【列を組む前に】行ごと捨てる。
    #   ★順序が命（2026-08-23実測）：後で捨てると、表の下に書かれた注記の
    #   時刻（例:「の山崎発時刻 11:20」）が列の並びを壊し、単調増加の検算が
    #   復路の列を丸ごと落としていた（p21は5列・p24は復路2便が消えていた）。
    #   名前を直して残す案は不採用：注記が便の列を共有していると
    #   「乗り換え無しで行ける」という嘘の続きになる。
    #   連絡便の時刻は本物の路線の格子（p3・p5等）に全て載っている。
    捨てる = set()
    for k, 名 in enumerate(停順):
        if 注記の型.search(名):
            捨てる.add(行キー[k]); continue
        # 3行に割れた注記の真ん中の断片：前の行が「〜連絡便の」で終わるか、
        # 次の行が「（前）発時刻」で始まるなら、この行は停留所ではない
        前文, 次文 = 文脈.get(行キー[k], ("", ""))
        if re.search(r"(連絡便の|連絡する便の)$", 前文) or re.match(r"前?発時刻", 次文):
            捨てる.add(行キー[k])
    if 捨てる:
        こ = [p for p in こ if round(p[4] / 3) not in 捨てる]
        停順, 行キー, 見た = [], [], {}
        for nw, _, _, _, y in sorted(こ, key=lambda p: p[4]):
            鍵 = round(y / 3)
            if 鍵 not in 見た:
                見た[鍵] = len(停順); 停順.append(nw); 行キー.append(鍵)
    # 便（時刻のx）ごとに列を作る
    列xたち = []
    for _, _, _, tx, _ in こ:
        for c in 列xたち:
            if abs(c - tx) <= 8:
                break
        else:
            列xたち.append(tx)
    列xたち.sort()
    便たち = []
    for cx in 列xたち:
        列 = [""] * len(停順)
        for nw, _, tw, tx, y in こ:
            if abs(tx - cx) <= 8:
                列[見た[round(y / 3)]] = tw
        # ★検算：上から下へ時刻が増えているか（バスは先へ進むほど遅い）。
        #   崩れている列は座標の取り違え＝載せない
        並び = [分(t) for t in 列 if t]
        if len(並び) >= 2 and all(並び[i] <= 並び[i+1] for i in range(len(並び)-1)):
            便たち.append(列)
    if len(停順) >= 3 and 便たち:
        上端 = min(p[4] for p in こ)
        return {"停": 停順, "便": 便たち, "_x": 名x, "_y": 上端}
    return None



# ══ 停留所の座標（宍粟市が公開している公式GTFSから）════════════
#  ★なぜ要るか（2026-08-23の実測）：
#   「山崎町山田から波賀町飯見まで」で、山田→山崎のバスに乗せていた。
#   ところが山田と山崎のバス停は **442メートル＝徒歩5分** しか離れていない。
#   Googleは徒歩で山崎まで出て「山崎〜皆木」の1本で行く案内を出す（1時間2分・200円）。
#   座標が無いと「歩けば済む区間」が分からず、乗り換えだらけの遠回りになる。
#  出典: 宍粟市 しーたんバス GTFS-JP（api.gtfs-data.jp / organization=shisocity）
GTFS一覧 = ("shitanbus-wingshinki", "shitanbus")

# ★この道具の作りの版（2026-08-29）。中身の作り方を変えたら必ず上げる。
#   PDFが同じでも作り直させるための札
作りの版 = "2026-08-30-zahyo"


def 停の座標を取る():
    """公式GTFSから 停留所名→(緯度, 経度) を作る。取れなければ空"""
    import io, zipfile, csv as _csv
    out = {}
    for f in GTFS一覧:
        try:
            b = 取る("https://api.gtfs-data.jp/v2/organizations/shisocity/feeds/"
                     + f + "/files/feed.zip")
            z = zipfile.ZipFile(io.BytesIO(b))
            with z.open("stops.txt") as fp:
                r = _csv.DictReader(io.TextIOWrapper(fp, encoding="utf-8-sig"))
                for s in r:
                    n = (s.get("stop_name") or "").strip()
                    if not n:
                        continue
                    try:
                        out.setdefault(n, []).append(
                            (float(s["stop_lat"]), float(s["stop_lon"])))
                    except Exception:
                        pass
        except Exception as e:
            print(f"GTFSが取れない({f}): {e}", file=sys.stderr)
    # 同じ名前で複数の乗り場がある（上り・下り）ので真ん中を代表にする。
    # ★★ ただし「同じ名前で遠く離れた別のバス停」を平均してはいけない（2026-08-30に発覚）。
    #   宍粟市には「上垣内」が2つある：
    #     一宮町西安積（35.1095, 134.5701）＝ **うえがいち**
    #     波賀町谷　　（35.1395, 134.5645）＝ **かみがいち**
    #   3.4km離れた別の停なのに、平均して (35.1245, 134.5673) という
    #   **実在しない地点**を代表にしていた（本物から1686mずれ）。
    #   読みも「うえがいち」だけを採っており、「かみがいち」は永久に当たらなかった。
    #   ★200mより離れた組は平均せず、**いちばん本数の多い側**でもなく
    #     「別の停として残す」。名前が同じでは区別できないので、
    #     ここでは代表として1つ目を返し、離れている事実を 別地点 に記録して外へ出す
    代表, 別地点 = {}, {}
    for n, v in out.items():
        遠い = False
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                dy = (v[i][0] - v[j][0]) * 111000.0
                dx = (v[i][1] - v[j][1]) * 111000.0 * math.cos(math.radians(v[i][0]))
                if math.hypot(dx, dy) > 200:
                    遠い = True
        if 遠い:
            # ★平均しない。全部の地点をそのまま残し、代表は1つ目
            別地点[n] = [[round(a, 6), round(b, 6)] for a, b in v]
            代表[n] = [round(v[0][0], 6), round(v[0][1], 6)]
            print(f"    ★『{n}』は同じ名前で離れた地点が{len(v)}か所ある。平均しない",
                  file=sys.stderr)
        else:
            代表[n] = [round(sum(a for a, _ in v) / len(v), 6),
                       round(sum(b for _, b in v) / len(v), 6)]
    return 代表, 別地点




# ══ 数字の読み方（2026-08-30。NAVITIMEの実データから確定）════════
#  ★なぜ要るか（この日に見つけた、120停に効く不具合）
#    公式GTFSのふりがなは「下宇原４」を「しもうはら４」と、**数字のまま**返す。
#    ところが人は「しもうはら**よん**」と言う。数字のままでは音が一生一致しない。
#    NAVITIMEの読み（569停）と突き合わせたところ、
#    **数字以外の食い違いは0件**で、違いは全部この数字の扱いだった。
#    NAVITIMEが実際に使っている読み方をそのまま採る（4はし ではなく よん、
#    7は しち ではなく なな。JIS S 0015 5.2b の作法とも一致する）。
数字の読み = {"0": "ゼロ", "1": "イチ", "2": "ニ", "3": "サン", "4": "ヨン",
              "5": "ゴ", "6": "ロク", "7": "ナナ", "8": "ハチ", "9": "キュウ"}


def 読みの数字を開く(読み):
    """読みの中に残っている数字を、実際に言う形へ開く。
    ★2桁（10）は「イチゼロ」ではなく「ジュウ」。実データにある10だけを見る"""
    if not 読み:
        return 読み
    t = 読み.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    t = t.replace("10", "ジュウ")
    出 = []
    for c in t:
        出.append(数字の読み.get(c, c))
    return "".join(出)

def 読みの穴を埋める(ふりがな, 停名すべて):
    """公式GTFSに読みが無い停を、**手元の検証済みデータから導いて**埋める（2026-08-30）。

    ★なぜ要るか（実機の失敗）
      「みかた」と話した人に「そのバス停が見つかりませんでした」と答えた。
      正解の「三方」は一宮町の実在の停なのに、**読みが無かった**ため
      音での突き合わせが1度も動かなかった。
      公式GTFS（api.gtfs-data.jp）を取り直して確かめたところ、
      stops.txt 233件＋53件のどちらにも三方は無い＝市が出していない。

    ★絶対に推測で埋めない（既存方針「読みは推測しない」を守る）。
      使ってよいのは
        ① shiso_goi.json の 地名読み（出典＝MapFan＋日本郵便ken_all・2026-08-23検証）から
           町名の接頭辞を機械的に剥がして導けるもの
        ② 全部かなの停名（そのままカタカナに直すだけ。判断が入らない）
      それ以外は**空のまま残し、根拠が要ることを表に出す**。
    """
    import unicodedata
    goi = 根 / "shiso_goi.json"
    if not goi.exists():
        return ふりがな, [], list(t for t in 停名すべて if t not in ふりがな)
    G = json.loads(goi.read_text(encoding="utf-8"))
    地名 = {a: b for a, b in G.get("地名読み", [])}
    町 = {k: v for k, v in 地名.items() if k.endswith("町") and len(k) <= 4}
    # 町名を剥がした「大字→読み」の索引
    大字 = {}
    for addr, rd in 地名.items():
        for m, mr in 町.items():
            if addr.startswith(m) and rd.startswith(mr) and len(addr) > len(m):
                大字.setdefault(addr[len(m):], set()).add(rd[len(mr):])
    for m, mr in 町.items():                       # 千種町=チクサチョウ ⇒ 千種=チクサ
        if mr.endswith("チョウ"):
            大字.setdefault(m[:-1], set()).add(mr[:-3])

    def かなだけか(t):
        return all(unicodedata.name(c, "").startswith(("HIRAGANA", "KATAKANA"))
                   or c in "ー・" for c in t)

    足した, 残り = {}, []
    for t in sorted(set(停名すべて)):
        if ふりがな.get(t):
            continue
        # ② 全部かな → そのままカタカナへ
        if かなだけか(t):
            足した[t] = ("".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in t),
                        "停名が全部かな（そのままカタカナに直しただけ）")
            continue
        # ① 大字にそのまま当たる
        当 = None
        for cand in (t, t + "町", t + "村"):
            if cand in 大字 and len(大字[cand]) == 1:
                r = list(大字[cand])[0]
                if cand == t + "町":
                    r = r[:-2] if r.endswith("マチ") else (r[:-3] if r.endswith("チョウ") else r)
                if cand == t + "村" and r.endswith("ムラ"):
                    r = r[:-2]
                当 = (r, f"地名読み『{cand}』（MapFan＋日本郵便ken_all）から町名を外した")
                break
        if 当:
            足した[t] = 当
            continue
        # ③ 「確かめた大字 ＋ 迷いの無い接尾」で組み立てる（2026-08-30）
        #    ★接尾はここに書いた分だけ。読み方が1つに決まる語しか置かない。
        #      「東門」のように ひがしもん/とうもん の両方あり得る語は**入れない**
        接尾 = {"北": "キタ", "南": "ミナミ", "東": "ヒガシ", "西": "ニシ",
                "口": "グチ", "橋": "バシ", "上": "カミ", "下": "シモ"}
        組んだ = None
        for suf in sorted(接尾, key=len, reverse=True):
            if not t.endswith(suf) or len(t) <= len(suf):
                continue
            頭 = t[:-len(suf)]
            for cand in (頭, 頭 + "町"):
                if cand in 大字 and len(大字[cand]) == 1:
                    r = list(大字[cand])[0]
                    if cand == 頭 + "町":
                        r = r[:-2] if r.endswith("マチ") else (r[:-3] if r.endswith("チョウ") else r)
                    組んだ = (r + 接尾[suf],
                              f"地名読み『{cand}』({r})に、読みが1つに決まる接尾『{suf}』"
                              f"({接尾[suf]})を足した")
                    break
            if 組んだ: break
        if 組んだ:
            足した[t] = 組んだ
            continue
        # ③-2 「確かめた大字 ＋ 後ろは全部かな」（山崎インター など）。
        #      後ろがかなだけなら読み方に迷いが無いので、そのまま足せる
        for k in range(len(t) - 1, 0, -1):
            頭, 尾 = t[:k], t[k:]
            if not かなだけか(尾):
                continue
            for cand in (頭, 頭 + "町"):
                if cand in 大字 and len(大字[cand]) == 1:
                    r = list(大字[cand])[0]
                    if cand == 頭 + "町":
                        r = r[:-2] if r.endswith("マチ") else (r[:-3] if r.endswith("チョウ") else r)
                    尾カナ = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in 尾)
                    組んだ = (r + 尾カナ,
                              f"地名読み『{cand}』({r})に、かなだけの『{尾}』をそのまま足した")
                    break
            if 組んだ: break
        if 組んだ:
            足した[t] = 組んだ
            continue
        # ④ 地名ではない一般の語だけでできている停（判断が入らないものに限る）
        #    ★出所を1件ずつ書く。地名は1つも入れない
        一般 = {
            "車庫前":     ("シャコマエ", "『車庫』『前』とも一般の語（地名ではない）"),
            "まほろばの湯": ("マホロバノユ",
                          "『まほろばの』は元からかな、『湯』は一般の語（一宮温泉まほろばの湯）"),
            # ★地元の方（利用者）に直接うかがって確認した読み（2026-08-30）。
            #   NAVITIMEにも郵便番号データにも無く、機械では取れなかった分。
            #   同時にうかがった 上三河/宮の元/船越/千種高校東門前 の4件は、
            #   あとからNAVITIMEの読みと突き合わせて**全部一致**した
            "神戸三宮":   ("コウベサンノミヤ", "地元の方に確認（2026-08-30）。高速便の行き先"),
        }
        if t in 一般:
            足した[t] = 一般[t]
            continue
        残り.append(t)
    for k, (r, _) in 足した.items():
        ふりがな[k] = r
    return ふりがな, sorted(足した.items()), 残り

def 停のふりがなを取る():
    """公式GTFSの translations.txt から 停留所名→ふりがな を作る。

    ★なぜ要るか（2026-08-29の実測）：
      バス停302種のうち **275種（91%）** が読みに直せていなかった。
      「引原（ひきばら）」「土万（ひじま）」「音水（おんずい）」のような
      難読地名は、読みが無いと音声認識の結果と突き合わせられない。
      日本語の認識器は「ひきばら」と聞こえた音を漢字に直して返すので、
      こちらも読みを持っていないと同じ土俵に乗らない。
    ★読みは**推測しない**。市が公式GTFSで出している ja-Hrkt（日本語ふりがな）を使う。
      実測：302種のうち283種（94%）に公式のふりがながあった。
    出典: 宍粟市 しーたんバス GTFS-JP（api.gtfs-data.jp / organization=shisocity）
          translations.txt の language=ja-Hrkt
    """
    import io as _io, zipfile, csv as _csv
    out = {}
    for f in GTFS一覧:
        try:
            b = 取る("https://api.gtfs-data.jp/v2/organizations/shisocity/feeds/"
                     + f + "/files/feed.zip")
            z = zipfile.ZipFile(_io.BytesIO(b))
            名 = {}
            with z.open("stops.txt") as fp:
                for x in _csv.DictReader(_io.TextIOWrapper(fp, encoding="utf-8-sig")):
                    sid = (x.get("stop_id") or "").strip()
                    nm = (x.get("stop_name") or "").strip()
                    if sid and nm:
                        名[sid] = nm
            if "translations.txt" not in z.namelist():
                print(f"ふりがなが無い({f})", file=sys.stderr)
                continue
            with z.open("translations.txt") as fp:
                for x in _csv.DictReader(_io.TextIOWrapper(fp, encoding="utf-8-sig")):
                    if (x.get("table_name") or "") != "stops":      continue
                    if (x.get("field_name") or "") != "stop_name":  continue
                    if (x.get("language") or "") != "ja-Hrkt":      continue
                    rid = (x.get("record_id") or "").strip()
                    よみ = (x.get("translation") or "").strip()
                    if rid in 名 and よみ:
                        out.setdefault(名[rid], よみ)
        except Exception as e:
            print(f"ふりがなが取れない({f}): {e}", file=sys.stderr)
    return out


def GTFSの表を作る():
    """公式GTFSから「停留所×便」の表を作る。しーたんバスの地域路線17系統ぶん。

    ★なぜPDFでなくGTFSか（2026-08-23の突き合わせで判明）：
      PDFの座標から組んだ格子は、公式GTFSと比べて **1本で行ける組を738通り取りこぼし**
      ていた。紙の表は行がずれたり注記が混ざったりするので、どうしても穴が出る。
      市が機械可読の形（GTFS-JP）で出しているのだから、そちらを正とする。
      GTFSは運行日も正確で、夏季・冬季の別や**運休日2152件**まで持っている。
    ★大型バス（山崎⇔一宮・波賀・千種）と高速バスはGTFSに無い（神姫バスの一般路線で、
      しーたんバスではない）。そこだけはPDFの格子を使い続ける。
    返り値: {路線名: [表, ...]}, {service_id: 運休日の集合}
    """
    import io, zipfile, csv as _csv
    表たち = {}
    運休 = {}
    for f in GTFS一覧:
        try:
            b = 取る("https://api.gtfs-data.jp/v2/organizations/shisocity/feeds/"
                     + f + "/files/feed.zip")
            z = zipfile.ZipFile(io.BytesIO(b))
        except Exception as e:
            print(f"GTFSが取れない({f}): {e}", file=sys.stderr)
            continue

        def 読む(名):
            with z.open(名) as fp:
                return list(_csv.DictReader(io.TextIOWrapper(fp, encoding="utf-8-sig")))

        停名 = {r["stop_id"]: r["stop_name"].strip() for r in 読む("stops.txt")}
        路線 = {r["route_id"]: (r.get("route_long_name") or r.get("route_short_name") or "").strip()
                for r in 読む("routes.txt")}
        暦 = {c["service_id"]: c for c in 読む("calendar.txt")}
        for c in 読む("calendar_dates.txt"):
            if c.get("exception_type") == "2":
                運休.setdefault(c["service_id"], set()).add(c["date"])
        便 = {}
        for r in 読む("trips.txt"):
            便[r["trip_id"]] = r
        時 = {}
        for r in 読む("stop_times.txt"):
            時.setdefault(r["trip_id"], []).append(r)

        # 「路線 × 運行日 × 停留所の並び」が同じものを1つの表にまとめる
        束 = {}
        for tid, 列 in 時.items():
            t = 便.get(tid)
            if not t:
                continue
            列.sort(key=lambda x: int(x["stop_sequence"]))
            並 = tuple(停名.get(x["stop_id"], "") for x in 列)
            if len(並) < 2 or "" in 並:
                continue
            刻 = tuple((x.get("departure_time") or x.get("arrival_time") or "")[:5].lstrip("0") or "0:00"
                       for x in 列)
            鍵 = (路線.get(t["route_id"], ""), t["service_id"], 並)
            束.setdefault(鍵, []).append(刻)
        for (路, sid, 並), 便ら in 束.items():
            c = 暦.get(sid, {})
            曜 = [i + 1 for i, k in enumerate(
                ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])
                if c.get(k) == "1"]
            便ら.sort(key=lambda v: 分(v[0]) if 時刻型.match(v[0]) else 0)
            表 = {"停": list(並), "便": [list(v) for v in 便ら],
                  "運行日": sid, "走る曜日": 曜, "運休の鍵": sid, "路線": 路}
            表たち.setdefault(路, []).append(表)
    return 表たち, {k: sorted(v) for k, v in 運休.items()}


def 路線の芯(名):
    """「しーたんバス　蔦沢線（三谷経由）」→「蔦沢線」。頁とGTFSを結ぶための形"""
    t = re.sub(r"^しーたんバス[\s　]*", "", 名 or "")
    return re.sub(r"[（(][^（()）]*[)）]", "", t).strip()

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
            # ★PDFが同じでも「この道具の作り」が変わったら作り直す（2026-08-29）。
            #   指紋だけを見ていたため、ふりがなを足す改修をしても
            #   「変化なし」で素通りし、いつまでも古い中身のままだった
            同じ作り = 旧.get("作りの版") == 作りの版
            # ★中身が揃っているかも見る（2026-08-29）。
            #   前回が途中で落ちて「地区の玄関」「町の停」が欠けたまま保存されても、
            #   指紋と版が同じなら素通りしてしまい、欠けたまま何日も気づけなかった
            要る = ("地区の玄関", "町の停", "町の停の組", "停の座標", "停の読み", "予約制の交通", "頁")
            欠け = [k for k in 要る if not 旧.get(k)]
            if 欠け:
                print(f"前回の資料に {欠け} が欠けている → 作り直す", file=sys.stderr)
            if (旧.get("指紋") == 指紋 and 同じ作り and not 欠け
                    and all((根 / p["画像"]).exists() for p in 旧.get("頁", []))):
                print("変化なし（前回のまま）")
                sys.exit(0)
            if not 同じ作り:
                print(f"作りの版が変わった（{旧.get('作りの版')} → {作りの版}）ので作り直す",
                      file=sys.stderr)
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
    格子あり = 0
    for n in range(1, 頁数 + 1):
        文 = 整える(頁文(一時, n))
        頁 = {"n": n, "画像": f"bus_cal/bus_{n}.png", "文": 文}
        try:
            表 = 格子を組む(語々を取る(一時, n))
        except Exception as e:
            print(f"  p{n} 格子が組めない {e}", file=sys.stderr)
            表 = []
        # ★「時刻表の見方」の説明頁の例示格子は収録しない（p29で実測。
        #   本物の路線（p23）と重複し、架空の路線名まで生んでいた。2026-08-23）
        if 文.startswith("時刻表の見方"):
            表 = []
        if 表:
            既定 = 運行日を読む(文)
            try:
                語々 = 語々を取る(一時, n)
                札 = 日の札を拾う(語々)
                路線 = 路線名を拾う(語々, 文)
            except Exception:
                札 = []; 路線 = ""
            休 = "（祝日運休）" if ("祝日運休" in 文[:1200] or "祝日除く" in 文[:1200]) else ""
            for t in 表:
                芯 = 近い札(札, t.pop("_x", 0), t.pop("_y", 0), 既定.split("（")[0])
                # 祝日の印は、札に既に付いている時と、祝日にも走る表（土日祝・土祝）
                # には重ねない
                t["運行日"] = 芯 + ("" if ("（" in 芯 or 芯 in ("土日祝", "土祝")) else 休)
                # 表示用の路線名。見出しが無ければ「起点〜終点」で表す
                t["路線"] = 路線 or (t["停"][0] + "〜" + t["停"][-1])
            頁["表"] = 表
            頁["運行日"] = 既定
            # 便・停留所ごとの運行条件の注記（「土曜日のみ運行」「冬季運休」等。
            # 格子には表現できないため、案内に一言添えるための印。2026-08-23）
            条件 = re.findall(r"[（(][^（()）]*(?:のみ運行|運行なし|冬季運休)[^（()）]*[)）]", 文)
            条件 += [m.strip() for m in re.findall(
                r"[^\n。]{2,20}(?:のみ運行|運行なし|冬季運休)[^\n。]{0,18}", 文)]
            条件 = sorted(set(条件))
            条件 = [c for c in 条件 if not any(c != d and c in d for d in 条件)]
            if 条件:
                頁["便注記"] = 条件
            格子あり += 1
        頁たち.append(頁)
    print(f"時刻の格子を組めたページ: {格子あり}/{頁数}", file=sys.stderr)

    # 祝日の一覧（内閣府の公式CSV）。祝日運休の便を祝日に案内しないために持つ。
    # 取れない時は前回の一覧を使い続ける（無いよりまし。2026-08-23）
    祝日たち = []
    try:
        生 = 取る("https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv").decode("cp932")
        今年 = int(time.strftime("%Y"))
        for 行 in 生.splitlines()[1:]:
            部 = 行.split(",")
            if len(部) >= 1 and "/" in 部[0]:
                y, m, d = (int(v) for v in 部[0].split("/"))
                if 今年 - 1 <= y <= 今年 + 1:
                    祝日たち.append("%04d-%02d-%02d" % (y, m, d))
    except Exception as e:
        print(f"祝日CSVが取れない（前回の一覧を残す）: {e}", file=sys.stderr)
        try:
            祝日たち = json.loads(出力.read_text(encoding="utf-8")).get("祝日", [])
        except Exception:
            祝日たち = []

    # ★しーたんバスの地域路線は、公式GTFSの表で置き換える（2026-08-23）。
    #   PDFの格子は1本で行ける組を738通り取りこぼしていた。
    #   大型バス・高速バスはGTFSに無いのでPDFのまま残す。
    #   頁の画像は時刻表を見せるために使うので、路線名で頁に結びつける
    try:
        G表, G運休 = GTFSの表を作る()
    except Exception as e:
        print(f"GTFSの表が作れない（PDFのまま進む）: {e}", file=sys.stderr)
        G表, G運休 = {}, {}
    置換, 残し = 0, 0
    if G表:
        芯ごと = {}
        for 路, ts in G表.items():
            芯ごと.setdefault(路線の芯(路), []).append((路, ts))
        使った = set()
        for p in 頁たち:
            表 = p.get("表")
            if not 表:
                continue
            芯 = 路線の芯(表[0].get("路線", ""))
            if 芯 in 芯ごと and 芯 not in ("大型バス", "高速バス"):
                新表 = []
                for 路, ts in 芯ごと[芯]:
                    # 同じ芯でも「三谷経由」等で頁が分かれるので、頁の路線名と
                    # 完全に合うものを優先し、無ければ芯が同じもの全部を載せる
                    if 路線の芯(路) == 芯:
                        新表.extend(ts)
                p["表"] = [dict(t) for t in 新表]
                for t in p["表"]:
                    t["出典"] = "GTFS"
                使った.add(芯)
                置換 += 1
            else:
                残し += 1
        print(f"表の出どころ: GTFSで置き換えた頁 {置換} ／ PDFのまま {残し}", file=sys.stderr)

    # 停留所の座標（歩ける距離を測るため。GTFSが取れない日は前回の分を残す）
    座標, 離れた同名 = 停の座標を取る()
    if not 座標 and 出力.exists():
        try:
            座標 = json.loads(出力.read_text(encoding="utf-8")).get("停の座標", {})
        except Exception:
            座標 = {}
    停名すべて = {t for p in 頁たち for tb in p.get("表", []) for t in tb["停"]}
    付いた = sum(1 for t in 停名すべて if t in 座標)
    print(f"停留所の座標: {付いた}/{len(停名すべて)}件（GTFS {len(座標)}件）", file=sys.stderr)

    # 停留所のふりがな（音声で聞き取った音と突き合わせるため。2026-08-29）
    ふりがな = 停のふりがなを取る()
    if not ふりがな and 出力.exists():
        try:
            ふりがな = json.loads(出力.read_text(encoding="utf-8")).get("停の読み", {})
        except Exception:
            ふりがな = {}
    GTFS件数 = len(ふりがな)
    ふりがな, 補った, 読み無し = 読みの穴を埋める(ふりがな, 停名すべて)
    # ★★ 座標の穴もNAVITIMEで埋める（2026-08-30）。
    #   市の公式GTFSに無い19停（三方・千種・エーガイヤちくさ等）は座標も無く、
    #   **千種町に基準点が1つも無い**状態だった。そのため
    #   「近い停の町に入れる」処理が、千種町の停を全部山崎町に寄せていた
    navi0 = 根 / "data_src" / "bus_navitime.json"
    if navi0.exists():
        import re as _re0
        N0 = json.loads(navi0.read_text(encoding="utf-8"))
        座0 = {}
        for r0 in (N0.get("路線") or {}).values():
            for t0 in r0.get("停", []):
                if t0.get("緯度") is None: continue
                n0 = _re0.sub(r"[（(][^）)]*[）)]$", "", t0["名"]).strip()
                n0 = _re0.sub(r"[［\[][^］\]]*[］\]]$", "", n0).strip()
                座0.setdefault(n0, [round(t0["緯度"], 6), round(t0["経度"], 6)])
        足0 = 0
        for t0 in 停名すべて:
            if t0 not in 座標 and t0 in 座0:
                座標[t0] = 座0[t0]; 足0 += 1
        if 足0: print(f"    NAVITIMEの座標で {足0}件を補った", file=sys.stderr)

    # ★NAVITIMEで集めた読みで穴を埋める（2026-08-30）。
    #   市の公式GTFSに無い停（神姫バスの路線の停）の読みはここから来る
    navi = 根 / "data_src" / "bus_navitime.json"
    足したnavi = 0
    if navi.exists():
        N = json.loads(navi.read_text(encoding="utf-8"))
        NY = N.get("停の読み") or {}
        for t in 停名すべて:
            if not ふりがな.get(t) and NY.get(t):
                ふりがな[t] = NY[t]; 足したnavi += 1
        if 足したnavi:
            print(f"    NAVITIMEの読みで {足したnavi}件を補った", file=sys.stderr)
        読み無し = [t for t in 読み無し if not ふりがな.get(t)]
    # ★★ 同じ名前で読みが2通りある停（2026-08-30に上垣内で発覚）。
    #   公式GTFSは 上垣内＝うえがいち（一宮町西安積）と
    #   上垣内＝かみがいち（波賀町谷）の**2つ**を持っているのに、
    #   名前で1つに潰していたため「かみがいち」は永久に当たらなかった。
    #   ★どちらの読みでも当たるように、別の読みも残す
    別の読み = {}
    try:
        import zipfile as _zp, io as _io2, csv as _cv2
        for _f in GTFS一覧:
            _b = 取る("https://api.gtfs-data.jp/v2/organizations/shisocity/feeds/"
                      + _f + "/files/feed.zip")
            _z = _zp.ZipFile(_io2.BytesIO(_b))
            _名 = {r["stop_id"]: r["stop_name"].strip() for r in
                   _cv2.DictReader(_io2.TextIOWrapper(_z.open("stops.txt"), encoding="utf-8-sig"))}
            for r in _cv2.DictReader(_io2.TextIOWrapper(_z.open("translations.txt"),
                                                        encoding="utf-8-sig")):
                if r.get("language") != "ja-Hrkt" or r.get("table_name") != "stops":
                    continue
                n = _名.get((r.get("record_id") or "").strip())
                t = (r.get("translation") or "").strip()
                if n and t: 別の読み.setdefault(n, set()).add(t)
        別の読み = {n: sorted(v) for n, v in 別の読み.items() if len(v) >= 2}
        for n, v in 別の読み.items():
            print(f"    ★『{n}』は読みが{len(v)}通りある: {' / '.join(v)}", file=sys.stderr)
    except Exception as e:
        print(f"別の読みが取れない: {e}", file=sys.stderr)

    # ★読みに残っている数字を、実際に言う形へ開く（120停に効く）
    開いた = 0
    for t, r in list(ふりがな.items()):
        新 = 読みの数字を開く(r)
        if 新 != r:
            ふりがな[t] = 新; 開いた += 1
    print(f"    読みの数字を開いた: {開いた}件（例 しもうはら４→しもうはらヨン）", file=sys.stderr)
    読み付いた = sum(1 for t in 停名すべて if t in ふりがな)
    print(f"停留所のふりがな: {読み付いた}/{len(停名すべて)}件"
          f"（GTFS {GTFS件数}件＋手元の検証済みデータから {len(補った)}件）", file=sys.stderr)
    for k, (r, なぜ) in 補った:
        print(f"    補った: {k} → {r}　（{なぜ}）", file=sys.stderr)
    if 読み無し:
        print(f"  ★読みが無いまま残った {len(読み無し)}件（推測で埋めない）: "
              + "、".join(読み無し), file=sys.stderr)

    # 保存量の検算（絶対ルール30：取り込んだら量を検算する）
    総 = sum(len(p["文"]) for p in 頁たち)
    空 = sum(1 for p in 頁たち if len(p["文"]) < 50)
    格子頁 = sum(1 for p in 頁たち if p.get("表"))
    停総 = sum(len(t["停"]) for p in 頁たち for t in p.get("表", []))
    便総 = sum(len(t["便"]) for p in 頁たち for t in p.get("表", []))
    表総 = sum(len(p.get("表", [])) for p in 頁たち)
    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市公式サイト " + 親,
        "url": url, "指紋": 指紋, "頁数": 頁数, "作りの版": 作りの版,
        # 検収（daikensa）が保存量を独立に検算するための欄（検収三原則②）
        "便数": 便総, "表数": 表総, "停のべ数": 停総,
        "祝日": 祝日たち,
        "停の座標": 座標,
        # ★同じ名前で200m以上離れた「別のバス停」。平均すると実在しない地点になる
        #   （2026-08-30に上垣内で発覚。1686mずれた地点を指していた）
        "離れた同名": 離れた同名,
        # ★停留所のふりがな（2026-08-29）。音声で聞き取った音と突き合わせるのに要る。
        #   推測ではなく、市が公式GTFSで出している ja-Hrkt をそのまま使う
        "停の読み": ふりがな,
        # ★同じ名前で読みが2通りある停（どちらで言われても当たるように）
        "別の読み": {n: [読みの数字を開く(x) for x in v] for n, v in 別の読み.items()},
        "読みの出典": "宍粟市 しーたんバス GTFS-JP translations.txt（language=ja-Hrkt）"
                      "＋不足分は shiso_goi.json の地名読み（MapFan＋日本郵便ken_all）から"
                      "町名の接頭辞を機械的に外して導出。推測では埋めていない",
        "読みが無い停": 読み無し,
        "運休日": G運休,
        "座標の出典": "宍粟市 しーたんバス GTFS-JP（api.gtfs-data.jp/v2/organizations/shisocity）",
        "問い合わせ": "ウイング神姫 山崎営業所 0790-62-1720",
        "頁": 頁たち,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{頁数}ページ・文章合計{総}字（文の無い頁 {空}）／格子 {格子頁}頁・停留所のべ{停総}・便{便総}"
          f" → {出力}（{出力.stat().st_size//1024}KB）")
    if 頁数 < 20:
        print("★注意: ページ数が例年（32）より大幅に少ない。PDFの作りが変わった疑い", file=sys.stderr)

    # ★地区（町）の玄関口を実データから決めて書き足す（2026-08-27）。
    #   ここで呼ばないと、時刻表を取り直すたびに「地区の玄関」が消え、
    #   「波賀まで」と言われた時に寄せ先が分からなくなる。
    #   ★人が決めた表を持たないための仕掛け。詳しくは build_bus_genkan.py
    import importlib.util as _iu
    _g = _iu.spec_from_file_location("genkan",
                                     pathlib.Path(__file__).resolve().parent / "build_bus_genkan.py")
    _m = _iu.module_from_spec(_g); _g.loader.exec_module(_m)
    # ★戻り値は7つ（2026-08-29に食い違いを発見）。3つで受けていたため
    #   ValueError で落ち、**「地区の玄関」「町の停」「町の停の組」が
    #   まるごと書かれないまま資料が保存されていた**。
    #   バスの案内（地区ごとの一覧・玄関口）が丸ごと死ぬ重い不具合
    _bus, _表, _中心, _町の停, _町の組, _便, _経過 = _m.決める()
    _欠 = [t for t, v in _表.items() if not v.get("停")]
    if _欠:
        print(f"★玄関口が決まらない町がある: {_欠}", file=sys.stderr)
    _bus["地区の玄関"] = {"中心の停": _中心, "町": _表}
    _bus["町の停"] = _町の停
    _bus["町の停の組"] = _町の組
    出力.write_text(json.dumps(_bus, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    print("  地区の玄関: " + " / ".join(f"{t}→{v['停']}" for t, v in _表.items()))
    print("  町の停: " + " / ".join(f"{t}{len(v)}停" for t, v in _町の停.items()))
    # ★予約制の交通（ちくさええとこバス等）も、ここで書き足す（2026-08-29）。
    #   別の道具を手で走らせる作りだったため、時刻表を作り直すたびに
    #   **まるごと消えていた**。玄関口と同じく本体から呼ぶ
    import subprocess as _sp
    _y = pathlib.Path(__file__).resolve().parent / "build_bus_yoyaku.py"
    if _y.exists():
        _r = _sp.run([sys.executable, str(_y)], capture_output=True, text=True)
        if _r.returncode != 0:
            print("★予約制の交通を作れない:\n" + (_r.stderr or "")[-500:], file=sys.stderr)
        else:
            print("  " + (_r.stdout or "").strip().split("\n")[-1])

    # ★書けたことを必ず数で確かめる（絶対ルール：取り込んだら検算する）
    _確 = json.loads(出力.read_text(encoding="utf-8"))
    for _k in ("地区の玄関", "町の停", "町の停の組", "停の座標", "停の読み", "予約制の交通"):
        if not _確.get(_k):
            print(f"★{_k} が資料に書けていない", file=sys.stderr); sys.exit(1)
