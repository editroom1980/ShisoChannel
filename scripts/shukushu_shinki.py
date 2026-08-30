# -*- coding: utf-8 -*-
"""神姫バスなど、市の公式GTFSに入っていない路線バスを集める（2026-08-30に新設）。

★なぜ要るか（この日に発覚した、資料の根本的な穴）
  それまでの資料は「宍粟市が公開しているGTFS（しーたんバス）」と
  「市が出しているPDFの時刻表」だけで作っていた。ところが宍粟市には
  **神姫バスの路線が29系統以上**走っており、山崎から千種・西河内へ行ける。
  それが1系統も入っていなかったため、
    ・千種町のバス停を4か所しか知らず
    ・行き先が千種だと何でも「ちくさええとこバス（予約制）」に流していた
  ご指摘：「バス停の行き先が千種だと、なんでもかんでもちくさええとこバスの
  案内を出すな。山崎やその他の地域からバスが出て、行けるところもたくさんある」

★調べ方の反省（これを二度とやらない）
  「市の公式データを読み込めたか」だけを確かめ、
  **「宍粟市を走るバスを全部把握できたか」を一度も確かめていなかった。**
  以後は必ず**2つ以上の独立した情報源で件数を突き合わせて**から「揃った」と言う。

出どころ
  ・NAVITIME バス路線図（停留所の順番・座標・乗換路線）
  ・NAVITIME バス時刻表（停留所の読み＝ruby、発車時刻）
  ・駅探（ekitan）路線一覧（突き合わせ用）
"""
import io, json, os, re, ssl, subprocess, sys, time, urllib.parse, urllib.request

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
控え = os.path.join("/tmp", "navitime_cache")
os.makedirs(控え, exist_ok=True)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
間 = 0.7          # 相手のサーバーに負担をかけない間隔（秒）
最後に取った = [0.0]

# ★「市内かどうか」は四角では切れない（2026-08-30の実測）。
#   宍粟市は南北に細長く、四角で囲うと たつの市・上郡町・姫路市北部まで入る。
#   実際 34.93〜35.33／134.40〜134.70 でやったら播磨科学公園都市の路線を拾った。
#   ★市が公式GTFSで出している283停の座標を「市の形」として使い、
#     そこから3km以内にある停を市内とみなす。バス路線の実際の形に沿う
市の停 = None
近いとみなす距離m = 3000


def 市の停を読む():
    global 市の停
    if 市の停 is not None: return 市の停
    b = json.load(io.open(os.path.join(根, "shiso_bus.json"), encoding="utf-8"))
    市の停 = [(v[0], v[1]) for v in (b.get("停の座標") or {}).values()]
    return 市の停


def 距離m(a, b):
    import math
    dy = (a[0] - b[0]) * 111000.0
    dx = (a[1] - b[1]) * 111000.0 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def 取る(url):
    鍵 = os.path.join(控え, re.sub(r"[^0-9A-Za-z]", "_", url)[-150:] + ".html")
    if os.path.exists(鍵) and os.path.getsize(鍵) > 500:
        return io.open(鍵, encoding="utf-8", errors="replace").read()
    待ち = 間 - (time.time() - 最後に取った[0])
    if 待ち > 0: time.sleep(待ち)
    最後に取った[0] = time.time()
    # ★このMacのPythonは証明書の束を持っていないので curl で取る（実測で確認）
    r = subprocess.run(["curl", "-sL", "--max-time", "45", "-A", UA, url],
                       capture_output=True)
    s = r.stdout.decode("utf-8", "replace")
    if len(s) < 500:
        raise RuntimeError(f"中身が短すぎる（{len(s)}バイト）")
    io.open(鍵, "w", encoding="utf-8").write(s)
    return s


def 路線を読む(路線id):
    """路線図のページから、停留所の順番と乗換路線を取り出す"""
    s = 取る(f"https://www.navitime.co.jp/bus/route/{路線id}/")
    名 = re.search(r"<title>(.*?)のバス路線図", s)
    停ら = []
    # ★属性の間に改行が入る（実データで確認）。\s+ で受ける
    for m in re.finditer(
            r'<dd class="node_frame"\s+data-no="(\d+)"\s+data-name="([^"]*)"\s+'
            r'data-lat="([-0-9.]*)"\s+data-lon="([-0-9.]*)"', s):
        番, 名前, la, lo = m.group(1), m.group(2), m.group(3), m.group(4)
        id_ = None
        あと = s[m.end():m.end() + 1200]
        n = re.search(r"/poi\?node=(\d+)", あと)
        if n: id_ = n.group(1)
        停ら.append({"順": int(番), "名": 名前, "id": id_,
                     "緯度": float(la) if la else None, "経度": float(lo) if lo else None})
    路線ら = {}
    for m in re.finditer(r'href="/bus/route/(\d+)/([^"]*)"[^>]*>([^<]*)</a>', s):
        路線ら[m.group(1)] = m.group(3)
    return {"id": 路線id, "名": 名.group(1) if 名 else "", "停": 停ら, "つながる路線": 路線ら}


def 市内の停の数(路線):
    ら = 市の停を読む()
    n = 0
    for t in 路線["停"]:
        if t["緯度"] is None: continue
        p = (t["緯度"], t["経度"])
        if any(距離m(p, q) <= 近いとみなす距離m for q in ら): n += 1
    return n


def 市内を通るか(路線):
    """1停でも市内にあれば資料に入れる（姫路行き・三宮行きも市民は使う）"""
    return 市内の停の数(路線) >= 1


def 追いかけるか(路線):
    """★つながる路線まで追うのは、市内に2停以上ある路線だけ。
    1停だけ掠める路線から先へ広げると、姫路市内のバス網まで際限なく広がる"""
    return 市内の停の数(路線) >= 2


def 集める(種, 上限=400):
    見た, 結果, 待ち = set(), {}, list(種)
    while 待ち and len(見た) < 上限:
        r = 待ち.pop(0)
        if r in 見た: continue
        見た.add(r)
        try:
            路線 = 路線を読む(r)
        except Exception as e:
            print(f"  路線{r} が取れない: {e}", file=sys.stderr); continue
        if not 路線["停"]:
            continue
        if not 市内を通るか(路線):
            print(f"  路線{r} {路線['名']} … 範囲の外なので追わない", file=sys.stderr); continue
        結果[r] = 路線
        市 = 市内の停の数(路線)
        追 = 追いかけるか(路線)
        print(f"  ◯ {r} {路線['名']}（{len(路線['停'])}停・うち市内{市}）"
              + ("" if 追 else " ※市内1停だけなので、この先は追わない"), file=sys.stderr)
        if 追:
            for x in 路線["つながる路線"]:
                if x not in 見た: 待ち.append(x)
    return 結果


if __name__ == "__main__":
    種 = sys.argv[1:] or ["00033832"]      # 山崎-千種-西河内[神姫バス]
    路線ら = 集める(種)
    停 = {}
    for r in 路線ら.values():
        for t in r["停"]:
            if t["id"]: 停.setdefault(t["id"], {"名": t["名"], "緯度": t["緯度"], "経度": t["経度"], "路線": []})
            if t["id"]: 停[t["id"]]["路線"].append(r["名"])
    出 = os.path.join("/tmp", "shinki_routes.json")
    json.dump({"路線": 路線ら, "停": 停}, io.open(出, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n路線 {len(路線ら)}件 ／ 停留所 {len(停)}種 → {出}")


def 読みを集める(停ら):
    """停留所ごとの読み（ふりがな）を NAVITIME の poi ページから取る。
    ★HTMLの <ruby>名前<rp>(<rt>よみ</rt> の形で入っている（実データで確認）"""
    出 = {}
    for i, (id_, v) in enumerate(sorted(停ら.items()), 1):
        try:
            s = 取る(f"https://www.navitime.co.jp/poi?node={id_}")
            m = re.search(r"<ruby>([^<]*)<rp>.*?<rt>([^<]*)</rt>", s, re.S)
            if m:
                出[v["名"]] = {"読み": m.group(2).strip(), "見出し": m.group(1).strip(), "id": id_}
        except Exception as e:
            print(f"  {v['名']}({id_}) が取れない: {e}", file=sys.stderr)
        if i % 50 == 0:
            print(f"  読み {i}/{len(停ら)}件…", file=sys.stderr)
    return 出


# ══ 時刻表の収集（2026-08-30）════════════════════════════════
#  ★取り方
#    ① 路線の起点の停で時刻表ページを開き、**便のID**を全部拾う
#       （平日・土曜・日曜祝日 × 方向2つ）
#    ② 便IDごとに /diagram/stops/{路線}/{便}/ を開くと、
#       その便の**停留所と時刻が全部**出る（お送りいただいた画面と同じもの）
#    これで「停ごとに時刻表を取る」より少ない回数で全部そろう
曜日名 = {0: "平日", 1: "土曜", 2: "日曜祝日"}


def 便を拾う(路線id, 停id, 年月日):
    """時刻表ページから、方向×曜日ごとの便ID一覧を取る"""
    y, m, d = 年月日
    s = 取る(f"https://www.navitime.co.jp/diagram/bus/{停id}/{路線id}/0/")
    出 = {}
    for mm in re.finditer(r'<div id="d_(\d)_(\d)"[^>]*>(.*?)(?=<div id="d_\d_\d"|\Z)', s, re.S):
        向, 曜 = int(mm.group(1)), int(mm.group(2))
        中 = mm.group(3)
        便ら = []
        for h in re.finditer(r"<dt>(\d{1,2})</dt>(.*?)</dl>", 中, re.S):
            時 = int(h.group(1))
            for t in re.finditer(
                    r'href="/diagram/stops/(\d+)/([0-9a-f]+)/\?node=(\d+)[^"]*"'
                    r'.*?<div style="text-align: left;text-decoration: underline;">(\d{1,2})</div>',
                    h.group(2), re.S):
                便ら.append({"便": t.group(2), "時": 時, "分": int(t.group(4))})
        if 便ら: 出[(向, 曜)] = 便ら
    return 出


def 便の停と時刻(路線id, 便id, 停id, 年月日):
    y, m, d = 年月日
    s = 取る(f"https://www.navitime.co.jp/diagram/stops/{路線id}/{便id}/"
             f"?node={停id}&year={y}&month={m:02d}&day={d:02d}")
    t = re.sub(r"<script.*?</script>", "", s, flags=re.S)
    題 = re.search(r"<title>([^<]*)</title>", s)
    出 = []
    for mm in re.finditer(r">([^<>]{2,30}?)</a>\s*</dt>.*?(\d{1,2}):(\d{2})\s*([発着])", t, re.S):
        出.append({"停": mm.group(1).strip(), "時": int(mm.group(2)),
                   "分": int(mm.group(3)), "発着": mm.group(4)})
    return {"題": 題.group(1) if 題 else "", "停": 出}
