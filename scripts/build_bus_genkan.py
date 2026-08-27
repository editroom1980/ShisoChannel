#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地区（町）の名前で聞かれた時に案内する「玄関口の停留所」を、実データから決める。
出力: shiso_bus.json に「地区の玄関」を書き足す

なぜ作るか（2026-08-27 ユーザー指摘）：
  「山崎から波賀までのバス」と言うと「やまさきから“やすが”まででよろしいですか」と返した。
  「波賀」を「安賀」に当てていた。聞き手には**聞き間違い**にしか聞こえない。

  調べたら、玄関口はJavaの中に人が手で書いた表で決まっていた。
  その表には「千種の停留所は1便しか無い」と書いてあったが、
  実データでは千種は4つの表に30便ある＝**注記が事実と違っていた**。

  そこで、人の判断を挟まず、実データだけで決める形にする。

決め方（この順に、すべて実データから）：
  1. その町名と同じ名前の停留所があるなら、それを使う（寄せない）
     … 千種・山崎はこれ。存在する停を別の停に置き換える理由が無い
  2. 無いなら、その町の「市民協働センター」の停を中心とみなす
  3. 中心の停に山崎からの直通便があるなら、それを玄関口にする（一宮はこれ）
  4. 直通が無いなら、中心にいちばん近くて直通のある停を玄関口にする（波賀はこれ）
     … 同じくらい近いものが複数あるときは便数の多い方

※「山崎」を起点に測るのは、山崎が全302停のうち最も便が多い乗り継ぎの中心だから
  （実測 429便。次点の69便の6倍）。ここも人が決めずデータで選ぶ。
"""
import json, math, re, sys, pathlib, collections

根 = pathlib.Path(__file__).resolve().parent.parent
BUS = 根 / "shiso_bus.json"
GOI = 根 / "shiso_goi.json"
町ら = ["山崎町", "一宮町", "波賀町", "千種町"]
空 = ("", "-", "ー", "―", "‐", "｜", "|", "・")


def 読む():
    return (json.loads(BUS.read_text(encoding="utf-8")),
            json.loads(GOI.read_text(encoding="utf-8")))


def 便を数える(表ら):
    数 = collections.Counter()
    for t in 表ら:
        停 = t["停"]
        for 列 in t["便"]:
            for i, s in enumerate(停):
                if i < len(列) and str(列[i]).strip() not in 空:
                    数[s] += 1
    return 数


def 直通(表ら, 甲, 乙):
    n = 0
    for t in 表ら:
        停 = t["停"]
        if 甲 in 停 and 乙 in 停:
            i, j = 停.index(甲), 停.index(乙)
            for 列 in t["便"]:
                if i < len(列) and j < len(列):
                    a, b = str(列[i]).strip(), str(列[j]).strip()
                    if a not in 空 and b not in 空:
                        n += 1
    return n


def 距離km(座, a, b):
    if a not in 座 or b not in 座:
        return None
    (y1, x1), (y2, x2) = 座[a], 座[b]
    return math.hypot((y1 - y2) * 111.0, (x1 - x2) * 91.0)


def 大字の町(goi):
    出 = {}
    for a, _ in goi["地名読み"]:
        m = re.match(r"(山崎町|一宮町|波賀町|千種町)(.+)$", a)
        if m:
            出[m.group(2)] = m.group(1)
    return 出


def 決める():
    bus, goi = 読む()
    表ら = [t for p in bus["頁"] for t in p.get("表", [])]
    全停 = set(s for t in 表ら for s in t["停"])
    座 = bus["停の座標"]
    便 = 便を数える(表ら)
    大字 = 大字の町(goi)

    # 乗り継ぎの中心＝いちばん便の多い停（人が決めない）
    中心停 = 便.most_common(1)[0][0]

    def 町(s):
        素 = re.sub(r"[（(].*?[）)]", "", s).strip()
        for k in sorted(大字, key=len, reverse=True):
            if 素.startswith(k):
                return 大字[k]
        return None

    出 = {}
    for t in 町ら:
        素町 = t.replace("町", "")
        if 素町 in 全停:                      # 1. 町名そのものの停がある
            出[t] = {"停": 素町, "理由": "町名と同じ名前の停留所が実在する",
                     "寄せた": False, "便": 便[素町],
                     "中心からの直通": 直通(表ら, 中心停, 素町)}
            continue
        # 2. その町の市民協働センターの停＝中心とみなす
        中心 = None
        for s in 全停:
            if 素町 in s and "市民協働センター" in s:
                中心 = s; break
        if 中心 is None:
            出[t] = {"停": None, "理由": "町名の停も市民協働センターの停も無い"}
            continue
        d = 直通(表ら, 中心停, 中心)
        if d > 0:                              # 3. 中心に直通がある
            出[t] = {"停": 中心, "理由": "町の市民協働センターの停に直通便がある",
                     "寄せた": True, "便": 便[中心], "中心からの直通": d}
            continue
        # 4. 中心にいちばん近くて直通のある停
        候, 座標なし = [], []
        for s in 全停:
            if s == 中心 or 町(s) != t:
                continue
            n = 直通(表ら, 中心停, s)
            if n <= 0:
                continue
            km = 距離km(座, 中心, s)
            if km is None:
                # ★座標の無い停は距離で比べられない。黙って落とすと
                #   「なぜ候補に入らないのか」が分からなくなるので、必ず名前を残す
                座標なし.append(f"{s}（{便[s]}便）")
                continue
            候.append((round(km, 2), -便[s], s, n))
        候.sort()
        if not 候:
            出[t] = {"停": None, "理由": "その町に直通のある停が無い"}
            continue
        km, m便, s, n = 候[0]
        出[t] = {"停": s, "理由": f"市民協働センターの停（{中心}）に直通が無いため、"
                                  f"そこから最も近く直通のある停",
                 "寄せた": True, "便": -m便, "中心からの直通": n,
                 "中心の停": 中心, "中心からの距離km": km,
                 "次点": [f"{x[2]}（{x[0]}km・{-x[1]}便）" for x in 候[1:4]],
                 "座標が無くて比べられなかった停": 座標なし}
    return bus, 出, 中心停


if __name__ == "__main__":
    bus, 表, 中心停 = 決める()
    欠 = [t for t, v in 表.items() if not v.get("停")]
    print(f"乗り継ぎの中心（便が最多の停）: {中心停}")
    for t, v in 表.items():
        print(f"  {t} → {v['停']}")
        print(f"      理由: {v['理由']}")
        print(f"      便{v.get('便','?')} ／ {中心停}からの直通 {v.get('中心からの直通','?')}便"
              + (f" ／ 中心から {v['中心からの距離km']}km" if "中心からの距離km" in v else ""))
        if v.get("次点"):
            print(f"      次点: {' / '.join(v['次点'])}")
        if v.get("座標が無くて比べられなかった停"):
            print(f"      ※座標が無く比べられなかった停: "
                  f"{' / '.join(v['座標が無くて比べられなかった停'])}")
    if 欠:
        print(f"！ 玄関口が決まらない町がある: {欠}"); sys.exit(1)

    bus["地区の玄関"] = {"中心の停": 中心停, "決め方": __doc__.split("決め方（")[1].strip(),
                        "町": 表}
    BUS.write_text(json.dumps(bus, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"\n○ shiso_bus.json に「地区の玄関」を書いた（{BUS.stat().st_size//1024}KB）")
