#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""宍粟市社会福祉協議会（社協）のサイトを集める。
出力: shiso_syakyo.json

なぜ作るか（2026-08-27）：
  「配食サービスはありますか」「高齢者の家事を手伝ってもらえますか」
  「ひとり暮らしの見守りは」に答えられなかった。市のサイトを探しても
  『配食』は本文にすら0件。調べたら、こういう暮らしの手助けは
  **市ではなく社会福祉協議会がやっている**。市の資料だけでは永久に届かない。

  社協は市とは別の法人で、サイトも別（www.shiso-wel.or.jp）。
  高齢者の生活支援・ボランティア・介護サービス・貸付が載っている。

取り決め：
  ・取得の作法は本体の収集器から読み込んで使う（同じ処理を2か所に持たない）
  ・市の資料と混ぜない。出典を「宍粟市社会福祉協議会」と明記して答える
"""
import json, re, sys, time, pathlib, urllib.parse, importlib.util

根 = pathlib.Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("kb", 根/'scripts'/'build_shiso_kb.py')
kb = importlib.util.module_from_spec(_s); _s.loader.exec_module(kb)

元 = "https://www.shiso-wel.or.jp"
出力 = 根 / "shiso_syakyo.json"
間 = 0.8
上限 = int(sys.argv[1]) if len(sys.argv) > 1 else 200

# ★画像も落とす。.jpeg と .bmp を書き忘れたせいで、写真を文字として取り込み、
#   1件92万字という化け物ができた（2026-08-27の検算で発覚）
除く = re.compile(r"(\.pdf|\.docx?|\.xlsx?|\.zip|\.jpe?g|\.png|\.gif|\.bmp|\.webp|\.svg|"
                  r"\.css|\.js|\.ico|\.xml|\.txt|download\.cgi|/cgi-bin/|/imgdata/|/atdata/)", re.I)


def 題を取る(h, 予備):
    for 型 in (r'(?is)<h1[^>]*>(.*?)</h1>', r'(?is)<title[^>]*>(.*?)</title>'):
        m = re.search(型, h)
        if m:
            t = kb.文字だけ(m.group(1))
            t = re.sub(r'[｜|]\s*宍粟市社会福祉協議会\s*$', '', t).strip()
            if len(t) >= 2:
                return t
    return 予備


def 中身を取る(h):
    t = kb.文字だけ(h)
    # 冒頭のメニュー（ホーム 〜）を落とす
    for 目印 in ["ホーム ", "現在の位置"]:
        j = t.find(目印)
        if 0 <= j < 300:
            t = t[j + len(目印):]
            break
    t = re.sub(r"(ページの先頭へ|サイトマップ|個人情報保護方針|Copyright.*)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def 走る():
    # ★事業紹介の子ページは入口に直接書く（2026-08-27の検算で3本の漏れが判明）。
    #   介護サービス・介護予防・その他の事業は、暮らしの手助けの本体が載っている
    待ち = ["/index.html", "/project/index.html", "/organization/map.html",
            "/news/index.php", "/event/index.html",
            "/project/corporation.html", "/project/community.html",
            "/project/volunteer.html", "/project/nursing_service.html",
            "/project/nursing_prevent.html", "/project/etc.html",
            "/guide/index.html", "/consultation/index.html"]
    見た, 集め = set(), []
    while 待ち and len(集め) < 上限:
        u = urllib.parse.urljoin(元, 待ち.pop(0)).split("#")[0]
        if u in 見た or not u.startswith(元):
            continue
        見た.add(u)
        try:
            h = kb.取る(u)
        except Exception as e:
            print(f"  ！取れない {u} … {e}")
            continue
        time.sleep(間)
        # ★HTMLでないものは捨てる（画像を文字として読んでしまう事故を二度とやらない）
        if "<html" not in h.lower() and "<body" not in h.lower():
            print(f"  …HTMLでないので捨てる {u[-50:]}")
            continue
        for m in re.finditer(r'href="([^"]+)"', h):
            v = urllib.parse.urljoin(u, m.group(1)).split("#")[0]
            if v.startswith(元) and v not in 見た and not 除く.search(v):
                待ち.append(v)
        題 = 題を取る(h, u.rsplit("/", 1)[-1])
        中 = 中身を取る(h)
        if len(中) < 80:
            continue
        # ★出会いサポートセンターの個別イベント告知が40本以上あり、
        #   ほかの資料を押しのけていた。事業の説明1本だけ残す（2026-08-27の検算）
        if "出会いサポート" in 題 and "/deai/" in u and not u.rstrip("/").endswith(("index.html", "deai")):
            continue
        # ★「社協ニュース」は全部同じ題。号や日付を足して別物にする。
        #   足さないと、まとめる時に147本が1本に潰れる（2026-08-27の検算で発覚）
        if 題 in ("社協ニュース", "ニュース", ""):
            日 = re.search(r"(令和\s*\d+\s*年\s*\d+\s*月|\d{4}年\d{1,2}月)", 中)
            号 = re.search(r"(\d{3,})", u)
            題 = "社協ニュース " + (日.group(1) if 日 else (号.group(1) if 号 else u[-12:]))
        電話 = re.findall(r"0790[-−－]?\d{2,3}[-−－]?\d{3,4}", 中)
        集め.append({
            "題": 題, "文": 中, "url": u,
            "電話": list(dict.fromkeys(電話))[:3],
            "表": kb.表を取る(h),
        })
        print(f"  {len(集め):3d}. {題[:48]}  ({len(中)}字)")
    return 集め, len(見た)


if __name__ == "__main__":
    始 = time.time()
    集め, 見た数 = 走る()
    # ★まとめる鍵はURL（題ではない）。題で束ねると同じ題の別記事が消える
    束 = {}
    for x in 集め:
        if x["url"] not in 束:
            束[x["url"]] = x
    項目 = sorted(束.values(), key=lambda x: x["題"])
    # ★照合のためだけの言葉を付ける（2026-08-27）。
    #   社協の題は「事業紹介」「困り事・悩み事を相談したい」のように中身を表さず、
    #   題で絞る仕組みに届かなかった（「高齢者の家事を手伝ってもらえますか」が
    #   正しい社協のページを1位に選べていたのに、題に『高齢者』が無くて落ちた）。
    #   ★広報と同じ処理を使う。同じ仕組みを2か所に持たない
    _k = importlib.util.spec_from_file_location("koho", 根/'scripts'/'build_shiso_koho.py')
    koho = importlib.util.module_from_spec(_k); _k.loader.exec_module(koho)
    koho.見出しを付ける(項目, 題も変える=False)
    出 = {"説明": "宍粟市社会福祉協議会のサイト。市ではなく社協がやっている暮らしの手助け",
          "出典": 元, "件数": len(項目), "項目": 項目}
    出力.write_text(json.dumps(出, ensure_ascii=False, indent=1), encoding="utf-8")
    字 = sum(len(x["文"]) for x in 項目)
    最長 = max((len(x["文"]) for x in 項目), default=0)
    if 最長 > 60000:
        print(f"！ 1件で {最長:,}字 は多すぎる。HTML以外を取り込んでいる疑い")
    print(f"\n○ {len(項目)}件（重複前 {len(集め)}）/ 見たURL {見た数}")
    print(f"  いちばん長い1件 {最長:,}字")
    print(f"  本文 合計 {字:,}字 / 平均 {字//max(len(項目),1)}字")
    print(f"  電話つき {sum(1 for x in 項目 if x['電話'])}件 / {time.time()-始:.0f}秒")
