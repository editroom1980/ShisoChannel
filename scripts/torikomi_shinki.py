# -*- coding: utf-8 -*-
"""集めた神姫バスの時刻表を、アプリが読む形（停の並び＋便ごとの時刻）へ変換して足す。

★なぜ要るか（2026-08-30に発覚）
  資料は宍粟市の公式GTFS（しーたんバス）と市のPDF時刻表だけで作っていた。
  ところが宍粟市には**神姫バスの路線が29系統以上**走っており、
  山崎から千種・西河内・姫路・新宮・神戸へ行ける。それが1系統も入っていなかった。
  ご指摘：「バス停の行き先が千種だと、なんでもかんでもちくさええとこバスの案内を
  出すな。山崎やその他の地域からバスが出て、行けるところもたくさんあるだろうが」

出どころ
  NAVITIME バス路線図（停の順番・座標）／バス時刻表（便ごとの停と時刻）
  取り方は scripts/shukushu_shinki.py（0.7秒間隔）
"""
import io, json, os, re, sys, time

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kensan import 件数を守る


def 素(n):
    """NAVITIMEの但し書き「（兵庫県）」「（宍粟市）」「［…］」を外し、英数字の全角を半角へ。

    ★全角と半角を揃えないと、同じ停が2つになる（2026-08-30に実際に起きた：
      市の資料は『JA城下支店』、NAVITIMEは『ＪＡ城下支店』で、
      読みの無い停が1つ増えていた）
    """
    n = re.sub(r"[（(][^）)]*[）)]$", "", n).strip()
    # ★〔…〕（U+3014）も外す。NAVITIMEは同じ名前の停を
    #   「上垣内〔宍粟市一宮町西安積〕」のように括って区別している。
    #   これを外さなかったため、同じ停が2つになっていた（2026-08-30に検査が検出）
    n = re.sub(r"[〔［\[][^〕］\]]*[〕］\]]$", "", n).strip()
    return n


def 幅をゆるく(n):
    """全角と半角の違いを消した「ゆるい鍵」。突き合わせにだけ使う"""
    return "".join(chr(ord(c) - 0xFEE0) if "！" <= c <= "～" else c for c in n)


def 市の表記に寄せる(n, 市の停ら, 読み索引=None, 読み=None):
    """市の資料に同じ停があれば、**市の書き方**を正とする。

    ★2026-08-30の失敗：全角を一律に半角へ直したら、
      市が『三谷１』と書いている停が『三谷1』になって二重になり、
      読みの無い停が81件も増えた。**片方に寄せるのではなく、市に合わせる。**
    """
    if isinstance(市の停ら, dict) and n in 市の停ら.values(): return n
    k = 幅をゆるく(n)
    if isinstance(市の停ら, dict) and k in 市の停ら: return 市の停ら[k]
    # ★字が1つだけ違って読みが同じなら、市の書き方を正とする。
    #   実データ：市『鍛冶屋橋』／NAVITIME『鍛治屋橋』（冶と治）。
    #   別の停として持つと、音が同じ停が2つになり取り違える（検査が検出）
    if 読み索引 and 読み:
        よ = 読み.get(n) or 読み.get(n + "(兵庫県)") or 読み.get(n + "(宍粟市)")
        if よ:
            for 市名 in 読み索引.get(幅をゆるく(よ), []):
                if len(市名) == len(n) and sum(1 for a, b in zip(市名, n) if a != b) <= 1:
                    return 市名
    return n


def 主():
    元 = "/tmp/shinki_jikoku.json"
    if not os.path.exists(元):
        print("！ /tmp/shinki_jikoku.json が無い。先に収集すること", file=sys.stderr); return 1
    J = json.load(io.open(元, encoding="utf-8"))
    B = json.load(io.open(os.path.join(根, "shiso_bus.json"), encoding="utf-8"))

    # ★市が使っている停の書き方の索引（ゆるい鍵 → 市の書き方）
    市の停索引 = {}
    for ら in (B.get("町の停") or {}).values():
        for n in ら: 市の停索引[幅をゆるく(n)] = n
    # NAVITIMEの読み（表記ゆれを寄せる時にも使う）
    _N0 = json.load(io.open(os.path.join(根, "data_src", "bus_navitime.json"),
                            encoding="utf-8"))
    読み = _N0.get("停の読み") or {}
    # 読み → 市の停名（字が1つ違いの表記ゆれを寄せるため）
    読み索引 = {}
    for n, よ in (B.get("停の読み") or {}).items():
        読み索引.setdefault(幅をゆるく(よ), []).append(n)

    表たち = []
    for rid, r in sorted(J.items()):
        路線名 = r["名"]
        # 曜日ごとにまとめる。停の並びは「いちばん停の多い便」を基準にする
        for 曜 in ("平日", "土曜", "日曜祝日"):
            便ら = [b for b in r["便"] if b["曜日"] == 曜]
            if not 便ら: continue
            基 = max(便ら, key=lambda b: len(b["停"]))
            停並 = [市の表記に寄せる(素(x["停"]), 市の停索引, 読み索引, 読み) for x in 基["停"]]
            # 同じ停が2度出る路線（循環）は、そのままの並びで持つ
            # ★★ 2026-08-30：時刻は**並び順で**合わせる。名前で引いてはいけない。
            #   同じ停を2回通る路線が92表あり（往復・折返し）、名前で引くと
            #   2回目に1回目の時刻が入って**時刻が逆戻り**した（検査が63本検出）。
            #   基準の並び（停並）を前から追いながら、同じ名前の次の場所へ置く
            行ら = []
            for b in 便ら:
                列 = [""] * len(停並)
                位 = 0
                for x in b["停"]:
                    名 = 市の表記に寄せる(素(x["停"]), 市の停索引, 読み索引, 読み)
                    先 = None
                    for k in range(位, len(停並)):
                        if 停並[k] == 名: 先 = k; break
                    if 先 is None:          # 基準に無い停は、この便では置き場が無い
                        continue
                    列[先] = f'{x["時"]}:{x["分"]:02d}'
                    位 = 先 + 1
                行ら.append(列)
            表たち.append({
                "停": 停並, "便": 行ら, "運行日": 曜, "路線": 路線名,
                "出典": "NAVITIME",
            })
    # 頁として足す（画像は無い。文はAIが読むための説明）
    新頁 = []
    for i, t in enumerate(表たち, 1):
        新頁.append({
            "n": f"神姫{i}",
            "文": (f"{t['路線']}の{t['運行日']}の時刻表です。"
                   f"この路線は{len(t['停'])}か所のバス停をとおり、"
                   f"{t['運行日']}は{len(t['便'])}本走ります。"
                   f"はじめの停留所は{t['停'][0]}、おわりの停留所は{t['停'][-1]}です。"
                   f"宍粟市の公式データ（しーたんバス）には無い神姫バスの路線で、"
                   f"NAVITIMEのバス時刻表から2026年8月30日に取り込みました。"),
            "表": [t],
            "運行日": t["運行日"],
        })
    # ★★ 新しく出てきた停を、町の一覧と読みにも足す（2026-08-30）。
    #   表に出るだけでは、キーで選ぶ流れにも音の照合にも出てこない。
    #   市内かどうかは**既知の停から3km以内**で判定し、
    #   いちばん近い既知の停の町に入れる（宍粟市は南北に細長く四角では切れない）
    import math
    N = json.load(io.open(os.path.join(根, "data_src", "bus_navitime.json"), encoding="utf-8"))
    座 = {}
    for r in N["路線"].values():
        for t in r["停"]:
            if t.get("緯度") is not None: 座.setdefault(素(t["名"]), (t["緯度"], t["経度"]))
    既知 = B.get("停の座標") or {}
    町の = {}
    for 町, ら in (B.get("町の停") or {}).items():
        for n in ら: 町の[n] = 町

    def 距離m(a, b):
        dy = (a[0] - b[0]) * 111000.0
        dx = (a[1] - b[1]) * 111000.0 * math.cos(math.radians(a[0]))
        return math.hypot(dx, dy)

    # ★★ 2026-08-30：市内かどうかは**市の本当の境界**で決める。
    #   「近い停の3km以内」を繰り返す方式にしたら、姫路・たつの方面の路線を
    #   たどって「ダイセル前」（たつの市）まで山崎町に入れてしまった。
    #   出典：国土交通省 国土数値情報 行政区域データ N03-20240101_28（兵庫県）
    多角形 = json.load(io.open(os.path.join(根, "data_src", "shiso_kyoukai.json"),
                               encoding="utf-8"))

    def 市内か(緯度, 経度):
        """点が多角形の中にあるか（外側の輪は入る／穴は出る）"""
        中 = False
        for 環ら in 多角形:
            for i, 環 in enumerate(環ら):
                内 = False
                j = len(環) - 1
                for k in range(len(環)):
                    x1, y1 = 環[k][0], 環[k][1]
                    x2, y2 = 環[j][0], 環[j][1]
                    if (y1 > 緯度) != (y2 > 緯度):
                        if 経度 < (x2 - x1) * (緯度 - y1) / (y2 - y1) + x1:
                            内 = not 内
                    j = k
                if i == 0: 中 = 中 or 内
                elif 内: 中 = False          # 穴の中は外
        return 中

    足した = {"山崎町": 0, "一宮町": 0, "波賀町": 0, "千種町": 0}
    外 = 0
    新停 = set()
    for t in 表たち:
        for n in t["停"]:
            if n in 町の or n in 新停: continue
            新停.add(n)
    # ★★ 1回だけでは足りない（2026-08-30の実測）。
    #   新しく足した停の隣にある停は、その回では「既知」に入っていないので拾えない。
    #   実際「三河」は『まなび舎農園前』から21mなのに、同じ回で足したため漏れた。
    #   **足せなくなるまで繰り返す。** ただし際限なく市外へ伸びないよう回数を切る
    残り = sorted(新停)
    for 周 in range(1, 6):
        次の残り = []
        この回 = 0
        for n in 残り:
            p2 = 座.get(n)
            if p2 is None: 次の残り.append(n); continue
            近, 近町 = None, None
            for k, v in 既知.items():
                d = 距離m(p2, (v[0], v[1]))
                if 近 is None or d < 近: 近, 近町 = d, 町の.get(k)
            # ★市の境界の中にあることを必ず確かめる（近いだけでは入れない）
            if not 市内か(p2[0], p2[1]):
                次の残り.append(n); continue
            if 近 is None or 近 > 5000 or not 近町:
                次の残り.append(n); continue
            B["町の停"].setdefault(近町, []).append(n)
            B.setdefault("町の停の組", {}).setdefault(近町, {})[n] = "神姫バスの停"
            B.setdefault("停の座標", {})[n] = [round(p2[0], 6), round(p2[1], 6)]
            既知[n] = [p2[0], p2[1]]      # ★次の回の基準に加える
            町の[n] = 近町
            よ = 読み.get(n) or 読み.get(n + "(兵庫県)") or 読み.get(n + "(宍粟市)")
            if よ: B.setdefault("停の読み", {})[n] = よ
            足した[近町] += 1; この回 += 1
        print(f"    {周}回目: {この回}停を足した（残り {len(次の残り)}）", file=sys.stderr)
        残り = 次の残り
        if この回 == 0: break
    外 = len(残り)
    print(f"  町の一覧に足した停: {足した}（市の外として見送り {外}件）")

    旧 = [p for p in B["頁"] if not str(p.get("n", "")).startswith("神姫")]
    B["頁"] = 旧 + 新頁
    # ★ファイルが名乗る頁数・便数も更新する（検算がここを見ている）
    B["頁数"] = len(B["頁"])
    B["便数"] = sum(len(t.get("便", [])) for p2 in B["頁"] for t in (p2.get("表") or []))
    B["表数"] = sum(len(p2.get("表") or []) for p2 in B["頁"])
    B["停のべ数"] = sum(len(t.get("停", [])) for p2 in B["頁"] for t in (p2.get("表") or []))
    B["神姫バスの出典"] = ("NAVITIME バス路線図・バス時刻表（2026-08-30取得）。"
                          "市の公式GTFSに無い路線を補うために取り込んだもので、"
                          "実際の時刻はバス会社の公表を確かめてください")
    停のべ = sum(len(t["停"]) for t in 表たち)
    便のべ = sum(len(t["便"]) for t in 表たち)
    件数を守る("神姫バスの表", len(表たち))
    io.open(os.path.join(根, "shiso_bus.json"), "w", encoding="utf-8").write(
        json.dumps(B, ensure_ascii=False, separators=(",", ":")))
    print(f"○ 神姫バスの表 {len(表たち)}枚・停のべ{停のべ}・便のべ{便のべ}を足した")
    print(f"  頁: {len(旧)}（元）＋ {len(新頁)}（神姫）= {len(B['頁'])}")
    return 0


if __name__ == "__main__":
    sys.exit(主())
