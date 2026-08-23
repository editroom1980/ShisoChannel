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
        "url": url, "指紋": 指紋, "頁数": 頁数,
        # 検収（daikensa）が保存量を独立に検算するための欄（検収三原則②）
        "便数": 便総, "表数": 表総, "停のべ数": 停総,
        "祝日": 祝日たち,
        "問い合わせ": "ウイング神姫 山崎営業所 0790-62-1720",
        "頁": 頁たち,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{頁数}ページ・文章合計{総}字（文の無い頁 {空}）／格子 {格子頁}頁・停留所のべ{停総}・便{便総}"
          f" → {出力}（{出力.stat().st_size//1024}KB）")
    if 頁数 < 20:
        print("★注意: ページ数が例年（32）より大幅に少ない。PDFの作りが変わった疑い", file=sys.stderr)
