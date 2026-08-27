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


def 停の注記(bus, 停名):
    """その停が何なのかを、時刻表の本文に書いてあることだけから一言にする。
    ★ご指摘（2026-08-28）「山崎は一番大きなバス停のことか？
      だとすれば名称は山崎だけだとわかりにくくないか？」
      時刻表の本文に「神姫バス山崎待合所」「蔦沢線・大谷線は山崎停留所でのみ
      乗り継げます」と書いてある。市の資料の言葉をそのまま使う。
    ★書いていない停には何も付けない（作り話をしない）"""
    文 = " ".join(p.get("文", "") for p in bus["頁"])
    if 停名 + "待合所" in 文 or "神姫バス" + 停名 + "待合所" in 文:
        return "バスの待合所・乗り継ぎの中心"
    return ""


def 町ごとの停(表ら, 全停, 大字, 座):
    """停留所を町に割り当て、案内に出す順に並べる。
    ★①大字で種をまき、②路線上で隣り合う停へ広げる（2026-08-27）。
      大字だけでは92停が決まらず、千種町は1停しか拾えなかった。
      隣り合わせは**実際の路線の並び順**なので、推測ではない。
    ★東河内は一宮町、西河内は千種町（郵便番号の地名で確認済み）。
    ★並べ方（2026-08-28のご指示「主要な施設を先に案内し、次に地区ごとに紹介しろ」）：
      便の多い順にしたら、西五十波・神野小学校前が上位に来た。
      便数は「そこを通る本数」であって「行き先としての大切さ」ではない。
      名前に入っている施設で分けて、行き先になりやすい順に並べる"""
    町ら = ["山崎町", "一宮町", "波賀町", "千種町"]
    def 素(s):
        return re.sub(r"[（(].*?[）)]", "", s).strip()
    割, 地区 = {}, {}
    for s in 全停:                                  # ① 種まき
        e = 素(s)
        当 = None
        for k in sorted(大字, key=len, reverse=True):
            if e.startswith(k):
                当 = 大字[k]; 地区[s] = k; break
        if 当 is None:
            for t in 町ら:
                if t.replace("町", "") in s:
                    当 = t; 地区[s] = t.replace("町", ""); break
        if 当:
            割[s] = 当
    種数 = len(割)
    隣 = collections.defaultdict(collections.Counter)
    for t in 表ら:
        停 = t["停"]
        for i, s in enumerate(停):
            for j in (i - 1, i + 1):
                if 0 <= j < len(停) and 停[j] != s:
                    隣[s][停[j]] += 1
    周 = 0
    for 周 in range(1, 21):                          # ② 隣へ広げる
        変 = 0
        for s in 全停:
            if s in 割:
                continue
            票 = collections.Counter()
            for n, w in 隣[s].items():
                if n in 割:
                    票[割[n]] += w
            if 票:
                当 = 票.most_common(1)[0][0]
                割[s] = 当; 変 += 1
                # 地区の名前も、決め手になった隣の停から受け継ぐ
                for n, _ in 隣[s].most_common():
                    if 割.get(n) == 当 and n in 地区:
                        地区[s] = 地区[n]; break
        if not 変:
            break
    残 = [s for s in 全停 if s not in 割]
    出 = {t: [s for s in 全停 if 割.get(s) == t] for t in 町ら}
    return 出, 地区, 種数, 周, 残


# ★停の名前から「どんな場所か」を見る。行き先になりやすい順（2026-08-28のご指示）。
#   上から順に当てはめる。細かいものを先に置く（自治会館は文化施設ではなく地区の集会所）
施設の並び = [
    ("集会所",   r"自治会館|集会所|公民館|詰所|会所"),
    ("病院",     r"病院|診療所|医院|クリニック|保健"),
    ("市の窓口", r"市役所|市民局|出張所|支所|役場|市民協働センター|はがてらす"),
    ("買い物",   r"イオン|スーパー|マルナカ|道の駅|ショッピング|商店|マーケット"),
    ("文化",     r"図書館|文化会館|ホール|美術|博物|資料館|学遊館"),
    ("温泉・運動", r"温泉|の湯|プール|体育|グラウンド|運動|公園|エーガイヤ|スポニック"),
    ("駅",       r"駅$|駅前"),
    ("郵便・金融", r"郵便局|農協|ＪＡ|JA|銀行|信用"),
    ("学校",     r"小学校|中学校|高校|大学|学校|こども園|幼稚園|保育"),
]
# 案内に出す順（数字が小さいほど先）。ご指示：病院→市役所→買い物→図書館
施設の順 = {"病院": 1, "市の窓口": 2, "買い物": 3, "文化": 4,
            "温泉・運動": 5, "駅": 6, "郵便・金融": 7, "学校": 8, "集会所": 99}


def 場所の種類(停名):
    for 名, pat in 施設の並び:
        if re.search(pat, 停名):
            return 名
    return None


def 案内の順に並べる(停ら, 玄関, 地区, 便):
    """主な施設 → 地区ごと、の順に並べ、それぞれの組の名前も返す"""
    組 = {}
    施設, 残り = [], []
    for s in 停ら:
        k = 場所の種類(s)
        if s == 玄関:
            施設.append((0, -便.get(s, 0), s)); 組[s] = "主な施設"
        elif k and 施設の順.get(k, 99) < 99:
            施設.append((施設の順[k], -便.get(s, 0), s)); 組[s] = "主な施設"
        else:
            残り.append(s)
    施設.sort()
    # 地区ごと。地区の中は便の多い順。地区の並びは「その地区でいちばん便の多い停」の順
    区分 = collections.defaultdict(list)
    for s in 残り:
        区分[地区.get(s, "そのほか")].append(s)
    区順 = sorted(区分.items(), key=lambda kv: -max(便.get(x, 0) for x in kv[1]))
    出 = [x[2] for x in 施設]
    for 区, v in 区順:
        v.sort(key=lambda x: (-便.get(x, 0), x))
        for s in v:
            組[s] = 区 + "地区"
        出.extend(v)
    return 出, 組


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
                     "中心からの直通": 直通(表ら, 中心停, 素町),
                     "注記": 停の注記(bus, 素町)}
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
    町の停, 地区, 種数, 周, 残 = 町ごとの停(表ら, 全停, 大字, 座)
    # ★案内に出す順に並べ替える（主な施設 → 地区ごと）
    並, 組 = {}, {}
    for t, v in 町の停.items():
        玄 = 出.get(t, {}).get("停")
        並[t], 組[t] = 案内の順に並べる(v, 玄, 地区, 便)
    return bus, 出, 中心停, 並, 組, 便, {"種まき": 種数, "広げた周": 周, "残り": 残}


if __name__ == "__main__":
    bus, 表, 中心停, 町の停, 町の組, 便, 経過 = 決める()
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

    print()
    print(f"町ごとの停留所（種まき{経過['種まき']}停 → {経過['広げた周']}周で全部）")
    for t, v in 町の停.items():
        主 = [s for s in v if 町の組[t].get(s) == "主な施設"]
        print(f"  {t}: {len(v)}停（主な施設 {len(主)}）")
        print(f"      案内の先頭: {' / '.join(v[:10])}")
    if 経過["残り"]:
        print(f"！ 町が決まらない停: {経過['残り']}")
    bus["地区の玄関"] = {"中心の停": 中心停, "決め方": __doc__.split("決め方（")[1].strip(),
                        "町": 表}
    bus["町の停"] = 町の停
    bus["町の停の組"] = 町の組      # 停ごとの見出し（主な施設／〇〇地区）
    bus["停の便数"] = dict(便)
    BUS.write_text(json.dumps(bus, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"\n○ shiso_bus.json に「地区の玄関」を書いた（{BUS.stat().st_size//1024}KB）")
