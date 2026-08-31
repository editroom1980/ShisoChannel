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
上限本数 = 100000    # ★2026-08-30：枠で切らない。切った時は下で必ず知らせる      # ★2026-08-28：手数料・所信表明・レシピを拾うようにしたら
                   #   候補が497本になり、320本の枠で新しい資料が丸ごと切れていた。
                   #   （枠に収まった分だけ処理して「320本」と表示するので気づきにくい）
                   #   ★枠に当たったら知らせる（下の 候補を選ぶ の末尾）
                   # （2026-08-27にも同じことが起きている：200本の枠から
                   #   バス時刻表6分割が全部消え、236→184件になった）
上限バイト = 20 * 1024 * 1024      # ★2026-08-30に12MB→20MBへ。12MBで外していた49本を
                                   #   一覧にしたところ、市民に要る物が入っていた：
                                   #     小学校の社会科副読本「わたしたちの宍粟」（全2冊）
                                   #     HPVワクチン 保護者向けの詳細版
                                   #     人権啓発冊子「そよ風」／国際交流協会だより
                                   #   20MBを超えるのは決算書・冊子の結合版だけになる
# ══ 容量について（2026-08-30にユーザー承認）══════════════════
#   いまの shiso_pdf.json は約71MB。GitHubは1ファイル50MBで警告・100MBで拒否する。
#   ★「このまま（案A）」で進めることをユーザーが決めた（2026-08-30）。
#     ・テレビは71MBを5.5秒で読み込めることを実機で確認済み
#     ・1件1行で書くので、毎週の自動更新で履歴に積まれるのは変わった行だけ
#   ★50MBの警告が出たら、または70MBを大きく超えたら、
#     ファイルを分ける（案B：6分割で各12MB）に切り替えること。
#     中身を削る（案C）は情報が減るので最後の手段。
取り出しの版 = 2   # ★上げると、指紋が同じ資料でも作り直す（作り方を変えた時に使う）
                   #   版2（2026-08-30）＝表を行ごとに組み直して足すようにした
短すぎる = 70                      # これ未満の文字しか取れなかった資料は入れない
                                   # ★120→70に下げた（2026-08-30）。捨てた物の名前を
                                   #   残すようにして初めて、枠のすぐ下に
                                   #   『一宮音頭 歌詞』78字・『いちのみや行進曲 歌詞』78字・
                                   #   『多目的トイレマップ（千種町）』106字・
                                   #   『ごはんのレシピ』109字（防災クッキング）といった、
                                   #   まさに地元のための中身があると分かった。
                                   #   ★捨てた物は名前と字数を必ず残す（下の 捨てた）
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
# ══ どのPDFを取り込むか（2026-08-30に全7292本を数え直して作り直した）══════
# ★以前は「ガイド・時刻・料金…」など**名前に読み物の語がある物だけ拾う**方式で、
#   7292本のうち6720本（92%）を名前だけで捨てていた。中身は見ていなかった。
#   実測でその中に、ウォーキングマップ全5コース・ごみの減量とリサイクル・
#   国際交流協会だより・新病院の市民アンケート・工場適地など、
#   市民が知りたい資料が丸ごと入っていた。
# ★方式を逆にする：**行政の内部書類だけを除き、残りは全部取り込む**。
#   除く物は、どれも「市民が読んで役に立つ場面が無い」と数えて確かめた分類だけ。
拾う = re.compile(r".")          # ★全部通す（残すかどうかは下の「除く」で決める）

除く = re.compile(
    # 議会・委員会の記録（1407本）。市民向けの説明会の記録は下で救う
    r"会議録|議事録|議事概要|会議次第|委員名簿|答申|意見書|議案|議会だより"
    r"|傍聴|政策会議|審議会|協議会だより|部会資料"
    # 決算・予算・財政（781本）
    r"|決算|予算書|予算案|当初予算|補正予算|財務書類|財政状況|健全化判断"
    r"|入札|落札|契約状況|指名停止|見積書|積算"
    # 申請の様式（477本）。「手引」が付く物は説明書なので残す
    r"|様式|記入例|記載例|届出書|委任状|同意書|申告書|申請書|チェックシート"
    # 図面・位置図（19本）
    r"|図面|位置図|平面図|求積図|求積表|設計図|配置図"
    # 監査・統計の生データ
    r"|監査結果|監査報告|統計表|集計表$|人口動態表"
)
# ★市民向けの記録は、上の「除く」に当たっても救い上げる
#   （2026-08-28の実測：会議録を除いたら『新病院市民説明会 開催記録』5片まで消えた）
救う = re.compile(r"市民説明会|住民説明会|開催記録|市民アンケート|パブリックコメントの結果"
                  r"|手引|てびき|ガイド|しおり|マップ|時刻|カレンダー|一覧|Q&A|よくある")

# ══ 会議に配る資料は除く（2026-08-30に実データで数えて足した）════════
# ★候補3545本のうち1066本（30%）が委員会・会議の配布物だった。
#   市民が尋ねることのない書類で、量も食う。
# ★ただし「会議」という語だけで切らない。実データを見て確かめた例：
#     残すべき … 家族防災会議ガイドブック／子育て相談チラシ（北部会場）
#     除くべき … 第3回◯◯委員会次第／01.資料1◯◯／09_宍粟市の人口動態
#   そこで「会議体の名前」と「配る物の目印」が**両方そろった時だけ**除く。
#   さらに、読み物（ガイド・手引・チラシ・マップ）は必ず残す
会議体 = re.compile(r"会議|委員会|部会|検討会|懇話会|審議会|協議会|懇談会")
配布物 = re.compile(r"次第|資料\d|議事|意見・提案|素案|当日配布|委員名簿|委員会名簿"
                    r"|開催結果|第\d+回|意見票|質問票|報告事項|協議事項|設置要綱|開催要項"
                    # ★「01-4.」「09_」のような番号の頭は、会議に配る資料の目印
                    r"|^\d{1,2}[-_.]")
# ★社会福祉協議会は市民の相談先。「協議会」で巻き込まないよう名指しで守る
会議でも残す = re.compile(r"社会福祉協議会|市民説明会|住民説明会|開催記録|市民アンケート"
                          r"|ガイドブック|ガイド|手引|チラシ|しおり|マップ")

# ★広報しそうの各号（409本）は取り込まない。**別の資料として全65冊・
#   140万字を既に持っている**ため、ここで入れると同じ物が二重になる
広報 = re.compile(r"広報しそう|お知らせ版|議会だより")




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
    外れ = __import__("collections").Counter()
    for x in kb["項目"]:
        for a in x.get("添付", []):
            u, 名 = a["url"], a["名"]
            if not u.lower().endswith(".pdf") or u in 見た:
                continue
            見た.add(u)
            # ★判定は「名前＋親記事の題」でする。名前が『全コース』のように
            #   それだけでは何か分からない添付が多いため（2026-08-30に実測）
            判 = 名 + " " + x.get("題", "")
            if 広報.search(判):                      # 別資料で全65冊を持っている
                外れ["広報しそう（別に全65冊を持っている）"] += 1; continue
            if 除く.search(判) and not 救う.search(判):
                外れ["行政の内部書類"] += 1; continue
            if (会議体.search(判) and 配布物.search(判)
                    and not 会議でも残す.search(判)):
                外れ["会議に配る資料"] += 1; continue
            # 大きさの見立て（名前の「(PDFファイル: 7.7MB)」から）
            mb = re.search(r"([\d.]+)\s*MB", 名)
            if mb and float(mb.group(1)) > 上限バイト / 1024 / 1024:
                外れ["12MBを超える"] += 1; continue
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
    # ★何を外したかを必ず数で残す（絶対ルール29②：捨てた分は何で何故かを数で残す）
    print(f"  添付PDF {len(見た)}本 → 候補 {len(out)}本", file=sys.stderr)
    for k, v in 外れ.most_common():
        print(f"    外した {k}: {v}本", file=sys.stderr)
    return out[:上限本数]


# ══ 体系的に整理する（2026-08-31にユーザー指示）════════════════
#   なぜ：全文をそのまま載せたら71MBになり、テレビ（アプリ1つ分の上限384MB）が
#   読み込みで強制終了した。**量を減らしてから載せる**のが先。
#   ★「答えに出るかどうか」は判断基準にしない（質問の作り方と順位付けに依存する）。
#     資料の**種類**という、内容そのものの性質で分ける。
#   ★捨てない。低優先の全文は data_src/pdf_zenbun.json に退避して残す。
高い = re.compile(r"手引|てびき|しおり|ガイド|マップ|時刻表|ダイヤ|料金|手数料|使用料|利用料"
                  r"|一覧|カレンダー|早見|レシピ|献立|チラシ|申込|Q&A|よくある|相談|窓口"
                  r"|注意|気をつけ|予定表|日程|パンフ|読本|使い方|届出|証明")
低い = re.compile(r"計画|方針|構想|戦略|ビジョン|パブリックコメント|（案）|\(案\)|委員会|審議会"
                  r"|報告書|調査結果|アンケート|統計|要覧|人口動態|予算|決算|施政方針|主要施策"
                  r"|財政|行政改革|指標|検証|評価|水質検査|対応記録|実施結果|実績報告|入札|経営")
要点の長さ = 1500          # 低優先の資料から残す冒頭の字数


def 優先度(題):
    """資料の種類で分ける。高＝市民が直接聞くもの／低＝行政の内部資料"""
    if 高い.search(題): return "高"
    if 低い.search(題): return "低"
    return "中"


def 体系的に整理する(項目):
    """重複をまとめ、低優先は冒頭の要点だけにする。捨てた全文は返り値の2つ目"""
    import hashlib
    # ① 年度違いの重複は、字数がいちばん多い1本だけ残す
    def 年を剥ぐ(t):
        t = re.sub(r"令和\d+年度?|平成\d+年度?|[HR]\d+年度?|\d{4}年度?", "", t)
        return re.sub(r"[（(]\d+/\d+[）)]$|\s+", "", t)
    本 = {}
    for r in 項目:
        本.setdefault(r["url"], []).append(r)
    組 = {}
    for u, ら in 本.items():
        組.setdefault(年を剥ぐ(ら[0]["題"]), []).append((u, sum(len(x.get("文", "")) for x in ら)))
    残すurl = set()
    for 鍵, ら in 組.items():
        残すurl.add(max(ら, key=lambda x: x[1])[0])
    消えた年度 = [u for u in 本 if u not in 残すurl]

    出, 退避 = [], []
    畳む = {}
    for u in 残すurl:
        ら = 本[u]
        級 = 優先度(ら[0]["題"])
        if 級 == "低":
            畳む[u] = ら
        else:
            出.extend(ら)
    for u, ら in 畳む.items():
        ら.sort(key=lambda x: x["題"])
        退避.extend(ら)
        文 = "\n".join(x.get("文", "") for x in ら)[:要点の長さ]
        元 = dict(ら[0])
        元["題"] = re.sub(r"[（(]\d+/\d+[）)]$", "", 元["題"])
        元["文"] = 文
        元["要点だけ"] = True          # ★全文は data_src/pdf_zenbun.json にある
        出.append(元)
    for u in 消えた年度:
        退避.extend(本[u])
    # ② 本文がまったく同じ片は1つにまとめる
    見た, 出2 = set(), []
    for r in 出:
        鍵 = hashlib.md5(r.get("文", "").encode("utf-8")).hexdigest()
        if len(r.get("文", "")) > 200 and 鍵 in 見た:
            退避.append(r); continue
        見た.add(鍵); 出2.append(r)
    return 出2, 退避


def 表を行ごとに直す(pdf):
    """表を「行」の形で書き出す。

    なぜ要るか（2026-08-30に実測）：
      いまの取り出しは表を**列の順**に吐くので、
      『ごみ袋の価格改定』では「改正後の価格」の4行が
      **どの袋のものか分からない数字の列**になっていた。
        ✖ もやすごみ袋（大）… 25円 500円 …（略）… 23円 19円 19円 19円
        ○ もやすごみ袋（大）（20枚入り）｜25円｜500円｜23円｜506円
      値段や時刻は、行と結びついて初めて意味を持つ。
    ★道具が無い環境（入れていないPC）では黙って何もしない
    """
    try:
        import pdfplumber
    except Exception:
        return ""
    行ら = []
    try:
        with pdfplumber.open(str(pdf)) as p:
            for 頁 in p.pages:
                for 表 in (頁.extract_tables() or []):
                    for 行 in 表:
                        枡 = [re.sub(r"\s+", " ", (c or "")).strip() for c in 行]
                        if not any(枡):
                            continue
                        行ら.append("｜".join(枡))
    except Exception:
        return ""
    return "\n".join(行ら)


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


切り捨て = []            # ★枠で捨てた資料をためる（最後に必ず知らせる）
                        #   {名, url, 捨てた字数, 全体の字数} を入れる
いま = {"名": "", "url": ""}   # ★分ける() に何の資料かを知らせる（記録に名前を残すため）


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
    切った = 0                      # ★枠に当たって捨てた字数
    # ★改行の無い長い行は、文字数で切っておく（2026-08-30に実測）。
    #   『公的個人認証サービス パンフレット』の1片が改行ゼロの14,545字になり、
    #   行で切る仕掛けでは1文字も切れなかった
    行ら = []
    for 行 in t.split("\n"):
        while len(行) > 一片:
            行ら.append(行[:一片]); 行 = 行[一片:]
        行ら.append(行)
    for i, 行 in enumerate(行ら):
        if 長さ + len(行) > 一片 and 今:
            out.append("\n".join(今)); 今, 長さ = [], 0
            if len(out) >= 最大片:
                # ★捨てた分を数える（絶対ルール29②：上限で切る時は数と理由を残す）。
                #   2026-08-30まで、ここは黙って break していた。
                #   96,000字を超える資料（計画・ガイドライン）は、
                #   超えた分が「無かったこと」になり、誰にも見えなかった
                切った = len("\n".join(行ら[i:]))
                break
        今.append(行); 長さ += len(行) + 1
    if 今 and len(out) < 最大片: out.append("\n".join(今))
    if 切った:
        # ★名前を残す（2026-08-30）。字数だけでは、どの資料が切れたのか分からず、
        #   「12片ちょうど＝切れた」と当て推量する羽目になった（実際は枠内だった）
        切り捨て.append({"名": いま["名"][:60], "url": いま["url"],
                        "捨てた字数": 切った, "全体の字数": len(t)})
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
            # ★1本のPDFは複数の片に分かれる。url を鍵にして上書きすると
            #   **最後の片しか残らず**、使い回した時に1片に縮む（2026-08-30に発覚）。
            #   実際に 5310片 → 3093片 に減り、件数を守る仕組みが止めてくれた。
            #   ★片の一覧として持つこと
            for r in json.loads(出力.read_text(encoding="utf-8")).get("項目", []):
                前回.setdefault(r["url"], []).append(r)
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

    項目, 文字なし, 捨てた = [], 0, []
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
        if (古 and 古[0].get("指紋") == 指紋
                and 古[0].get("版", 1) >= 取り出しの版):
            項目.extend(古)                      # 変わっていない＝前回の文章を全部使い回す
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
        # ★表は行ごとに組み直して後ろに足す（2026-08-30）。
        #   置き換えない。地の文にしか無い説明が消えるため
        表 = 表を行ごとに直す(一時)
        if 表:
            文 = (文 + "\n" + 表).strip()
        読み取った = False
        if len(文) < 120 and 読み取りの道具:
            try:
                o = subprocess.run([str(読み取りの道具), str(一時)],
                                   capture_output=True, timeout=900)
                文2 = 整える(o.stdout.decode("utf-8", "replace"))
                if len(文2) > len(文): 文, 読み取った = 文2, True
            except Exception as e:
                print(f"  読み取れない {r['名'][:30]} {e}", file=sys.stderr)
        if len(文) < 短すぎる:                   # それでも文章が無い
            文字なし += 1
            # ★何を捨てたかを名前と字数で残す（絶対ルール29②）。
            #   2026-08-30まで数だけ数えていたため、
            #   『多目的トイレマップ（千種町）』106字・『ごはんのレシピ』109字のように
            #   **中身のある資料**が枠のすぐ下で捨てられていたことに気づけなかった
            捨てた.append({"名": r["名"][:60], "url": r["url"], "字数": len(文),
                          "文": 文[:200]})
            continue
        # ★題に親記事の名前も含める（2026-08-22実測：題が「時刻表（…）」だけだと
        #   「バス」で探しても届かない。親「しーたんバス時刻表」が入って初めて当たる）
        題 = r["名"] if r["親"] in r["名"] else (r["親"] + " " + r["名"])
        いま["名"], いま["url"] = r["名"], r["url"]
        片たち = 分ける(文)
        for k, 片 in enumerate(片たち, 1):
            付 = "" if len(片たち) == 1 else f"（{k}/{len(片たち)}）"
            一 = {"題": "資料 " + 題 + 付, "url": r["url"], "文": 片,
                  "親": r["親"], "課": r["課"], "電話": r["電話"], "指紋": 指紋,
                  "版": 取り出しの版}
            if 読み取った: 一["読み取り"] = True
            項目.append(一)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(候補)} … {r['名'][:26]}", file=sys.stderr)

    if 切り捨て:
        合 = sum(x["捨てた字数"] for x in 切り捨て)
        print(f"！ 長すぎて枠（{一片}字×{最大片}片＝{一片*最大片:,}字）に入らず捨てた資料 "
              f"{len(切り捨て)}本・合計 {合:,}字:", file=sys.stderr)
        for x in sorted(切り捨て, key=lambda y: -y["捨てた字数"])[:15]:
            割 = 100 * x["捨てた字数"] // max(1, x["全体の字数"])
            print(f"      {x['捨てた字数']:>7,}字（全体の{割}%）を捨てた: {x['名'][:44]}",
                  file=sys.stderr)
        (根 / "data_src").mkdir(exist_ok=True)
        (根 / "data_src" / "pdf_kirisute.json").write_text(
            json.dumps({"件数": len(切り捨て), "枠": 一片 * 最大片,
                        "捨てた字数の合計": 合, "項目": 切り捨て},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        print("  枠で捨てた資料は無い", file=sys.stderr)

    # ★体系的に整理してから保存する（2026-08-31）。
    #   重複を1つにまとめ、行政の内部資料は冒頭の要点だけにする。
    #   全文は捨てずに data_src/pdf_zenbun.json へ退避する
    元の数, 元の字 = len(項目), sum(len(x.get("文", "")) for x in 項目)
    項目, 退避 = 体系的に整理する(項目)
    後の字 = sum(len(x.get("文", "")) for x in 項目)
    要点 = sum(1 for x in 項目 if x.get("要点だけ"))
    print(f"体系的に整理: {元の数:,}片 {元の字:,}字 → {len(項目):,}片 {後の字:,}字"
          f"（うち要点だけにしたもの {要点:,}本／退避 {len(退避):,}片）", file=sys.stderr)
    級 = __import__("collections").Counter(優先度(x["題"]) for x in 項目)
    print(f"  優先度の内訳: 高 {級['高']:,}片／中 {級['中']:,}片／低 {級['低']:,}片",
          file=sys.stderr)
    (根 / "data_src").mkdir(exist_ok=True)
    (根 / "data_src" / "pdf_zenbun.json").write_text(
        json.dumps({"説明": "テレビには載せない全文（低優先の資料・年度違い・重複）。"
                            "必要になったらここから戻せる",
                    "件数": len(退避), "項目": 退避},
                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  → 退避先 data_src/pdf_zenbun.json", file=sys.stderr)

    # ★数える対象を「片」から「PDFの本数」に変えた（2026-08-31）。
    #   体系的な整理で片の数は意図的に減る（低優先を要点だけにするため）が、
    #   **本数が減るのは取りこぼし**なので、そちらを見張る
    件数を守る("PDF資料の本数", len({x["url"] for x in 項目}))

    # ★1件を1行で書く（2026-08-30）。中身はまったく同じJSONだが、
    #   全部を1行にすると git が差分を取れず、**毎週の自動更新のたびに
    #   71MB分がまるごと履歴に積まれる**（年間で約3.7GB）。
    #   1行1件にすると、変わった資料の行だけが差分になる。
    #   ★見た目のためではない。リポジトリが太って push できなくなるのを防ぐため
    頭 = {
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        # ★どの知識ベースから作ったかを書き残す（2026-08-30）。
        #   これが無かったため、知識ベースを2306→2422件に取り直した日に
        #   PDFの取り込みだけ回し忘れ、8/28のまま2日間気づかなかった。
        #   検査はこの値と shiso_kb.json の「更新」を突き合わせる
        "元にした知識ベース": kb.get("更新", ""),
        "出典": "宍粟市公式サイトの添付PDF",
        "件数": len(項目),
    }
    書 = ["{"]
    for k, v in 頭.items():
        書.append(json.dumps(k, ensure_ascii=False) + ":"
                  + json.dumps(v, ensure_ascii=False) + ",")
    書.append('"項目":[')
    for i, 一 in enumerate(項目):
        書.append(json.dumps(一, ensure_ascii=False, separators=(",", ":"))
                  + ("," if i + 1 < len(項目) else ""))
    書.append("]}")
    出力.write_text("\n".join(書), encoding="utf-8")
    if 捨てた:
        近 = sorted([x for x in 捨てた if x["字数"] >= 40], key=lambda x: -x["字数"])
        print(f"！ 文字が {短すぎる}字に満たず捨てた {len(捨てた)}本。"
              f"うち 40字以上あったもの {len(近)}本（中身がある可能性）:", file=sys.stderr)
        for x in 近[:12]:
            print(f"      {x['字数']:4}字 {x['名'][:44]}", file=sys.stderr)
        # ★診断用の記録なので data_src に置く。shiso_*.json だと
        #   資料一覧（shiryo_ichiran.py）が「資料」として数えてしまう
        (根 / "data_src").mkdir(exist_ok=True)
        (根 / "data_src" / "pdf_suteta.json").write_text(
            json.dumps({"件数": len(捨てた), "しきい値": 短すぎる, "項目": 捨てた},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"      → 捨てた一覧: data_src/pdf_suteta.json", file=sys.stderr)

    print(f"{len(項目)}本の文章を保存（画像だけで飛ばした {文字なし}本）"
          f" → {出力}（{出力.stat().st_size//1024}KB）")
