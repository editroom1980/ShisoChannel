#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宍粟市の郵便局を、国土交通省「国土数値情報（郵便局データ P30）」から作る。
出力: shiso_yubin.json

なぜ作るか（2026-08-27）：
  「郵便局はどこ」に答えられなかった。市のサイトは自前の施設しか載せておらず、
  郵便局・駐在所のような他の機関の場所は資料に無かった。
  国が公開している郵便局データ（全国・出典明記で二次利用可）から作る。

出典：国土交通省 国土数値情報（郵便局データ）
  https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P30.html
  ★利用にあたっては出典の明示が求められる。答える時に必ず添える。
  ★簡易郵便局は取扱い業務が限られる。名前のとおり伝える（勝手に「郵便局」と言わない）
"""
import json, re, sys, time, io, zipfile, pathlib, urllib.request

出力 = pathlib.Path(__file__).resolve().parent.parent / "shiso_yubin.json"
名乗り = "ShisochanNET-KB/1.0 (+https://shisochan.net/; citizen broadcast app)"
元 = "https://nlftp.mlit.go.jp/ksj/gml/data/P30/P30-13/P30-13_28.zip"   # 兵庫県
市コード = "28227"      # 宍粟市


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


def 取る(url):
    最後 = None
    for 再 in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": 名乗り})
            with urllib.request.urlopen(req, timeout=60, context=_ssl文脈()) as r:
                return r.read()
        except Exception as e:
            最後 = e
            if 再 < 2:
                time.sleep(3 * (再 + 1))
    raise 最後


if __name__ == "__main__":
    生 = 取る(元)
    with zipfile.ZipFile(io.BytesIO(生)) as z:
        名 = [n for n in z.namelist() if n.endswith(".xml") and "KS-META" not in n]
        if not 名:
            print("★XMLが入っていない（配布の形が変わった可能性）", file=sys.stderr)
            sys.exit(1)
        s = z.read(名[0]).decode("utf-8", "ignore")

    出 = []
    for m in re.finditer(r"<ksj:PostOffice[^>]*>(.*?)</ksj:PostOffice>", s, re.S):
        b = m.group(1)
        区 = re.search(r"<ksj:administrativeArea[^>]*>(\d+)</ksj:administrativeArea>", b)
        if not 区 or 区.group(1) != 市コード:
            continue
        名前 = re.search(r"<ksj:name>([^<]*)</ksj:name>", b)
        住 = re.search(r"<ksj:address>([^<]*)</ksj:address>", b)
        if not 名前:
            continue
        n = 名前.group(1).strip()
        出.append({
            "名": n,
            "住所": "宍粟市" + (住.group(1).strip() if 住 else ""),
            "地区": next((t for t in ("山崎町", "一宮町", "波賀町", "千種町")
                          if 住 and t in 住.group(1)), ""),
            "簡易": "簡易郵便局" in n,
        })
    出.sort(key=lambda x: (x["簡易"], x["地区"], x["名"]))

    # ── 検算（件数だけ見て合格にしない）──
    地区あり = sum(1 for x in 出 if x["地区"])
    if len(出) < 10:
        print(f"★{len(出)}件しか取れていない。市コードか配布の形を確かめること", file=sys.stderr)
        sys.exit(1)
    if 地区あり < len(出) * 0.9:
        print(f"★地区の分からないものが多い（{len(出)-地区あり}件）", file=sys.stderr)
        sys.exit(1)

    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "国土交通省 国土数値情報（郵便局データ P30-13）"
                " https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P30.html",
        "注意": "簡易郵便局は取り扱う業務が限られます。詳しくは各局へお問い合わせください",
        "件数": len(出),
        "項目": 出,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    簡 = sum(1 for x in 出 if x["簡易"])
    print(f"{len(出)}局（うち簡易郵便局 {簡}局）→ {出力}（{出力.stat().st_size//1024}KB）")
    from collections import Counter
    for k, v in Counter(x["地区"] or "(不明)" for x in 出).most_common():
        print(f"  {k}: {v}局")
