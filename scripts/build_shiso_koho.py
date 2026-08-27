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
import json, re, sys, time, html, math, subprocess, shutil, pathlib, urllib.request

根 = pathlib.Path(__file__).resolve().parent.parent
出力 = 根 / "shiso_koho.json"
名乗り = "ShisochanNET-KB/2.0 (+https://shisochan.net/; citizen broadcast app)"
一覧 = "https://www.city.shiso.lg.jp/soshiki/shichokoshitsu/hishokoho/tantojoho/kohoshiso/index.html"
年度一覧 = "https://www.city.shiso.lg.jp/soshiki/shichokoshitsu/hishokoho/tantojoho/kohoshiso/backnumber/"
何冊 = int(sys.argv[1]) if len(sys.argv) > 1 else 999  # 既定は全冊
一片 = 6000
最大片 = 30   # ★1冊を切り捨てないための上限。切ったら下の検算が知らせる
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


# ★案内の題に混ぜてはいけない語（2026-08-27）。
#   これが題に入ると、記事そのものが「案内に使えない」と判定されて丸ごと消える
題に入れない = re.compile(r"(計画|委員会|審議会|議事|パブリックコメント|実施結果|"
                          r"募集結果|選考|入札|指名|適用除外|取り扱い|取扱い|特例|"
                          r"経過措置|事業者向け|経営戦略|登録者数|名簿|様式|不適切|"
                          r"調査結果|処分|事案|報告書|義援金|募金|お見舞い)")


# ★広報のどの号にも出る決まり文句。題に付けても「その片らしさ」にならない
器の言葉 = set("""
募集 対象 日時 会場 申込 申込方法 専用 コチラ 令和 月号 今月 担当 問合 問合せ
時間 場所 内容 定員 費用 無料 詳細 電話 開催 案内 参加 実施 申請 受付 締切
市民 宍粟 宍粟市 皆さん 皆様 場合 必要 確認 information インフォメーション
ホームページ フォーム センター 広報紙 広報部門 年目 表紙 出版社 今回 以下
""".split())


def 特徴語(片, 文書頻度, 全片数, 何語=25):
    """この片にしか出てこない言葉を選ぶ（TF-IDF）。
    ★なぜ要るか（2026-08-27の実測）：
      広報の片の題は「広報しそう 2024年5月号（2/4）」だけ。
      記事を1件に絞る仕組みは『質問の重い語が題に入っていること』を条件にするため、
      広報はどれだけ中身が濃くても**永久に選ばれない**。
      「消防団に入るには」の答えが広報に載っているのに、AI行きになっていた。
    ★1冊の中だけで数えると「募集・日時・会場」ばかりになった（最初の失敗）。
      211片すべてを見比べて、その片にしか出ない言葉を選ぶ。
    ★言葉は本文から拾う。こちらで作った言葉は1つも足さない"""
    数 = {}
    for w in re.findall(r"[一-龥]{2,6}|[ァ-ヴー]{3,10}", 片):
        if 題に入れない.search(w) or w in 器の言葉:
            continue
        数[w] = 数.get(w, 0) + 1
    点 = []
    for w, n in 数.items():
        df = 文書頻度.get(w, 1)
        if df > 全片数 * 0.25:      # 4分の1を超える片に出る語は、その片らしさが無い
            continue
        点.append((n * math.log(全片数 / df), w))
    点.sort(reverse=True)
    出, 済 = [], []
    for _, w in 点:
        if any(w in x or x in w for x in 済):   # 「消防団」と「消防」を両方は出さない
            continue
        済.append(w); 出.append(w)
        if len(出) >= 何語:
            break
    return 出


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
    # ★バックナンバーの一覧ページも必ず見る（2026-08-28の実測で判明）。
    #   広報のトップには**直近5年度分しかリンクが無く**、
    #   令和3年度（12冊）を丸ごと取り逃していた。
    #   「全ての項目を見る」の先が本当の一覧
    頁ら = [一覧, 年度一覧 + "index.html"]
    for 元頁 in list(頁ら):
        try:
            h = 取る(元頁)
        except Exception as e:
            print(f"  一覧が読めない {元頁} {e}", file=sys.stderr); continue
        time.sleep(間)
        for m in re.finditer(r'href="([^"]*backnumber/\d+\.html)"', h):
            u = URLを直す(m.group(1))
            if u not in 頁ら:
                頁ら.append(u)
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


def 見出しを付ける(項目, 題も変える=True):
    """全片がそろってから、片ごとの特徴語を題に足す。
       ★1冊だけで数えると器の言葉しか出ない。全片を見比べる必要がある"""
    語ら = []
    for x in 項目:
        語ら.append(set(re.findall(r"[一-龥]{2,6}|[ァ-ヴー]{3,10}", x["文"])))
    文書頻度 = {}
    for s_ in 語ら:
        for w in s_:
            文書頻度[w] = 文書頻度.get(w, 0) + 1
    for x in 項目:
        出 = 特徴語(x["文"], 文書頻度, len(項目), 25)
        x["見出し語"] = 出
        基 = x["題"].split("｜")[0]
        # ★画面に出す題は短く（4語まで）。読み上げの題が長いと聞きづらい。
        #   ★もともと中身を表す題を持つ資料（社協など）は題を変えない
        if 題も変える:
            x["題"] = 基 + ("｜" + "・".join(出[:4]) if 出 else "")
        # ★照合用の索引は長く持つ（25語）。
        #   「献血はいつありますか」の『献血』は、5片にしか出ない代わりに
        #   1片あたり2回しか出ないので、上位4語には入らない。
        #   索引に入れておけば、題で絞る仕組みに届く
        x["索引"] = "・".join(索引語(x["文"], 文書頻度, len(項目)))
    return 項目


def 索引語(片, 文書頻度, 全片数, 割合 = 0.15):
    """照合のためだけに持つ言葉。画面には出さない。
    ★上位25語では足りなかった（2026-08-27の実測）。
      「献血」は5片にしか出ない代わりに1片で1〜2回しか出ないので、
      点の高い順に並べると25位に入らず、題で絞る仕組みに永久に届かなかった。
      そこで「その片らしい言葉すべて」＝全片の15%以下にしか出ない語を全部入れる。
      よく出る語（防災は70片に出る）は、その片らしさが無いので入れない"""
    上 = 全片数 * 割合
    出 = []
    for w in sorted(set(re.findall(r"[一-龥]{2,6}|[ァ-ヴー]{3,10}", 片))):
        if 題に入れない.search(w) or w in 器の言葉:
            continue
        if 文書頻度.get(w, 1) <= 上:
            出.append(w)
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
    取込 = 捨 = 0
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
        # ★号の名前はURLの年月から。無ければ**題名の元号**から西暦に直す
        #   （2026-08-28の実測：0214kohoshiso.pdf のようにURLに年月が無い号が2冊あり、
        #     「広報しそう令和7年2月号」がそのまま号名になって年で並ばなかった）
        m = re.search(r"(20\d{2})(\d{2})", r["url"])
        if m:
            号 = f"{m.group(1)}年{int(m.group(2))}月号"
        else:
            g = re.search(r"(平成|令和)\s*(\d+|元)\s*年\s*(\d+)\s*月", r["名"])
            if g:
                元 = 1 if g.group(2) == "元" else int(g.group(2))
                西 = (1988 + 元) if g.group(1) == "平成" else (2018 + 元)
                号 = f"{西}年{int(g.group(3))}月号"
            else:
                号 = r["名"]
        片ら = 分ける(文)
        保存 = sum(len(x) for x in 片ら)
        if 保存 < len(文) * 0.98:
            捨 += len(文) - 保存
            print(f"  ！{号} は {len(文):,}字のうち {保存:,}字しか保存できていない"
                  f"（{100*保存//max(len(文),1)}%）", file=sys.stderr)
        取込 += len(文)
        for k, 片 in enumerate(片ら, 1):
            付 = "" if len(片ら) == 1 else f"（{k}/{len(片ら)}）"
            項目.append({"題": f"広報しそう {号}{付}", "号": 号,
                         "文": 片, "url": r["url"]})
        print(f"  {i+1}/{len(号ら)} {号} … {len(文):,}字", file=sys.stderr)

    if not 項目:
        print("★中身を取り出せなかった", file=sys.stderr)
        sys.exit(1)
    見出しを付ける(項目)
    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "宍粟市公式サイト「広報しそう」",
        "冊数": len({x["号"] for x in 項目}),
        "件数": len(項目),
        "項目": 項目,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    字 = sum(len(x["文"]) for x in 項目)
    # ★検算（2026-08-27の取り決め）：入力何字→保存何字→捨てた分は何字か
    print(f"{len({x['号'] for x in 項目})}冊・{len(項目)}片・{字:,}字 → {出力}"
          f"（{出力.stat().st_size//1024}KB）")
    print(f"検算: PDFから取り出した {取込:,}字 / 保存 {字:,}字 / 捨てた {捨:,}字"
          f"（{100*字//max(取込,1)}%を保存）")
    if 捨 > 0:
        print("！ 捨てた分がある。最大片を増やすこと", file=sys.stderr)
