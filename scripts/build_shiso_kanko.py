#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
しそうツーリズムガイド（宍粟市観光協会 shiso.or.jp）から、
名所・旧跡・観光地・飲食店・道の駅などのスポット情報を集める。
出力: shiso_kanko.json

なぜ作るか（2026-08-21）：
  「宍粟市の飲食店・企業・名所・旧跡・観光地を網羅的に答えられるように」との指示。
  観光協会の公式ガイドには約145件のスポットがあり、各ページに
  所在地・電話番号・定休日・営業時間が定義リスト(dt/dd)で載っている。
  出典がはっきりした一次情報なので、AIの作り話を防げる。

行儀よく集めること：1ページごとに間をあけ、名乗る。
"""
import json, re, time, sys, html, urllib.request, urllib.parse, pathlib

元 = "https://shiso.or.jp"
名乗り = "ShisochanNET-KB/1.0 (+https://shisochan.net/; citizen broadcast app)"
出力 = pathlib.Path(__file__).resolve().parent.parent / "shiso_kanko.json"
間 = 0.5


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
    with urllib.request.urlopen(req, timeout=20, context=_文脈) as r:
        return r.read().decode("utf-8", "ignore")


def 文字だけ(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def スポット(h, url):
    題 = re.search(r"<title>([^<|]+)", h)
    名 = html.unescape(題.group(1)).strip() if 題 else ""
    if not 名:
        return None
    it = {"名": 名, "url": url}

    # 定義リスト（郵便番号・所在地・電話番号・定休日・営業時間・ホームページ…）
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    組 = re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", body, re.S)
    対応 = {"所在地": "住所", "電話番号": "電話", "定休日": "定休日",
           "営業時間": "営業時間", "ホームページ": "HP", "郵便番号": None,
           "駐車場": "駐車場", "料金": "料金", "アクセス": "アクセス"}
    for k, v in 組:
        k = 文字だけ(k); v = 文字だけ(v)
        if k in 対応 and 対応[k] and v:
            it[対応[k]] = v[:120]

    # 説明文：本文の段落から、それらしい長さのものを1つ
    段落 = re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)
    for p in 段落:
        t = 文字だけ(p)
        if len(t) >= 40 and "Copyright" not in t and "クッキー" not in t:
            it["説明"] = t[:300]
            break

    # ※分類はページ側から確実に取れない（サイドメニューを拾って全件同じになった）ので出さない
    return it


def 走る():
    一覧html = 取る(元 + "/highlights")
    リンク = sorted(set(re.findall(r'href="(https://shiso\.or\.jp/highlights/[^"]+)"', 一覧html)))
    リンク = [l for l in リンク if "/highlights_cat/" not in l and "?" not in l]
    print(f"スポット {len(リンク)}件を読みに行く", file=sys.stderr)
    集めた = []
    for i, u in enumerate(リンク):
        try:
            h = 取る(u)
        except Exception:
            time.sleep(3)
            try:
                h = 取る(u)          # 1回だけやり直す（たまたまの502対策）
            except Exception as e:
                print(f"  読めない {u} {e}", file=sys.stderr)
                continue
        time.sleep(間)
        it = スポット(h, u)
        if it:
            集めた.append(it)
        if (i + 1) % 25 == 0:
            print(f"  {i+1}件 … {集めた[-1]['名'][:20] if 集めた else ''}", file=sys.stderr)
    return 集めた


if __name__ == "__main__":
    集めた = 走る()
    出力.write_text(json.dumps({
        "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "出典": "しそうツーリズムガイド（宍粟市観光協会） https://shiso.or.jp/",
        "件数": len(集めた),
        "項目": 集めた,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    電話あり = sum(1 for x in 集めた if x.get("電話"))
    print(f"{len(集めた)}件（うち電話番号あり {電話あり}件）→ {出力}（{出力.stat().st_size//1024}KB）")
