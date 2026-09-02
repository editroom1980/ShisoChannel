# -*- coding: utf-8 -*-
"""いまある資料の一覧を出す（何に答えられるかの見取り図）

なぜ：
  資料が39種を超え、何がどこにあるか分からなくなってきた。
  10月の説明でも「何に答えられるのか」を聞かれる。
  ★件数はその場で数える。手で書いた数を持たない（すぐ古くなる）。
"""
import json, pathlib, sys
from datetime import datetime

根 = pathlib.Path(__file__).resolve().parent.parent

説明 = {
    "kb": "市公式サイトの記事（全文・表・添付つき）",
    "koho": "広報しそう（現行の号）",
    "koho_kako": "広報しそう（古い号。アーカイブから回収）",
    "pdf": "市の主要PDFの中身（手引き・料金表・時刻表など）",
    "syakyo": "宍粟市社会福祉協議会のページ",
    "gikaidayori": "宍粟市議会だより（議案・賛否・討論・一般質問）",
    "bunka": "しそうの逸話・民話と山崎文化協会の催し",
    "bus": "しーたんバスの時刻表・停留所・座標",
    "jinko": "人口の移り変わり（平成16年度〜・地区別・年齢別）",
    "rekishi": "宍粟 歴史 再発見（連載44回）",
    "reiki": "条例・規則の索引",
    "bunbetsu": "ごみの分別（50音順早見表）",
    "faq": "市の「よくある質問」",
    "kanko": "観光スポット（しそうツーリズムガイド）",
    "matsuri": "市内のお祭り",
    "ichi": "施設の位置と最寄りのバス停",
    "bunkazai": "国・県・市の指定文化財",
    "goi": "聞き取りの言葉（地名・読み・言い直し）",
    "shisetsu": "学校・こども園などの施設一覧",
    "zatsugaku": "宍粟の豆知識（由来・日本酒発祥など）",
    "gyousei": "行政区（自治会）ごとの人口・世帯数",
    "gakko": "今ある学校と、閉校・閉園した学校",
    "gomi": "ごみの収集地区とカレンダー",
    "hinanjo": "指定避難所",
    "gikai": "市議会の議員名簿",
    "iryo": "休日当番医と医療機関",
    "yama": "宍粟50名山と標高",
    "kihon": "市の基本（面積・市の花と木・合併・市歌・将来像）",
    "shinbyoin": "新病院（開院時期・建設地・工事の進み）",
    # ★説明を実体に直した（2026-09-01）。中身は方言ではなく、
    #   市役所・病院・警察・道の駅などの連絡先13件だった
    "local": "地元の主な施設・店の連絡先（手作り・出典つき）",
    "yubin": "郵便局",
    "tokusan": "特産品",
    "koban": "交番・駐在所",
    "yosan": "市の予算・決算・地方債",
    "shigai": "市の外の窓口（パスポートなど）",
    "josei": "助成・補助・給付",
    "soudan": "相談窓口",
    "kokyo": "公共施設（開館時間・電話・バリアフリー）",
    "access": "市外から宍粟市への行き方",
    "tesuryo": "証明書の手数料（住民票・戸籍・印鑑証明など）",
    # ★2026-09-01に追加した資料
    "janru": "ジャンルの木（探すボタン・聞き取れなかった時に出す9分類）",
    "katachi": "宍粟市の外周（地図の下敷き。国土数値情報 N03 由来）",
}

def 数(d):
    if isinstance(d, list): return len(d)
    if not isinstance(d, dict): return 1
    for k in ("項目", "月ごと", "今ある学校"):
        if k in d and isinstance(d[k], (list, dict)): return len(d[k])
    return 1

def 主():
    行 = []
    for f in sorted(根.glob("shiso_*.json")):
        名 = f.stem.replace("shiso_", "")
        d = json.loads(f.read_text(encoding="utf-8"))
        n = 数(d)
        if 名 == "gakko":
            n = len(d.get("今ある学校", [])) + len(d.get("閉校・閉園した学校園", []))
        行.append({"名": 名, "件数": n, "KB": f.stat().st_size // 1024,
                   "説明": 説明.get(名, "（説明が未記入）")})
    未 = [x["名"] for x in 行 if x["説明"].startswith("（")]
    合 = sum(x["件数"] for x in 行)
    MB = sum(x["KB"] for x in 行) / 1024
    print(f"資料 {len(行)}種・{合:,}件・{MB:.1f}MB")
    print(f"{'資料':<14}{'件数':>8}{'大きさ':>9}  何に答えるか")
    for x in sorted(行, key=lambda y: -y["KB"]):
        print(f"{x['名']:<14}{x['件数']:>8,}{x['KB']:>7}KB  {x['説明']}")
    if 未:
        print(f"\n！ 説明が書かれていない資料 {len(未)}件: {未}")
        return 1
    先 = 根 / "shiryo_ichiran.json"
    先.write_text(json.dumps({
        "作った日": datetime.now().strftime("%Y-%m-%d"),
        "資料の数": len(行), "件数の合計": 合,
        "資料": sorted(行, key=lambda y: y["名"])}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"\n○ 一覧 → {先}")
    return 0

if __name__ == "__main__":
    sys.exit(主())
