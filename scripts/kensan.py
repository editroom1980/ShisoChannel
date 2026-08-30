# -*- coding: utf-8 -*-
"""資料の件数が黙って減らないようにする歯止め（2026-08-30に新設）。

★なぜ要るか（この日に見つけた3つの誤りに共通する型）
  ・知識ベースが施設ページ16校を捨て → 開校中の学校を「閉校」と答えていた
  ・交番の取り出しが区画の最後の1件を落とし → 引原駐在所が抜けていた
  ・バスは神姫バス29系統が丸ごと入っていなかった
  どれも「件数を印字していたが、誰も前回と比べていなかった」。
  **印字は検算ではない。** 前回より減ったら止める。

使い方:
    from kensan import 件数を守る
    件数を守る("交番・駐在所", len(一覧))
  減っていたら、その場で止まる（sys.exit(1)）。
  意図して減らす時は data_src/kensuu.json のその行を手で直す（理由を書く）。
"""
import io, json, os, sys, time

台帳 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data_src", "kensuu.json")


def _読む():
    try: return json.load(io.open(台帳, encoding="utf-8"))
    except Exception: return {}


def 件数を守る(名, 実際, 許す減り=0):
    """前回より減っていたら止める。増えていれば台帳を更新する。"""
    d = _読む()
    前 = d.get(名, {}).get("件数")
    if 前 is not None and 実際 < 前 - 許す減り:
        print(f"★『{名}』が {前}件 → {実際}件 に減った。取りこぼしの疑いがあるので止める。",
              file=sys.stderr)
        print(f"  意図した減少なら {台帳} の『{名}』を直してから、もう一度実行すること。",
              file=sys.stderr)
        sys.exit(1)
    if 前 is None or 実際 > 前:
        os.makedirs(os.path.dirname(台帳), exist_ok=True)
        d[名] = {"件数": 実際, "更新": time.strftime("%Y-%m-%dT%H:%M:%S+09:00")}
        io.open(台帳, "w", encoding="utf-8").write(
            json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True))
        if 前 is not None:
            print(f"  検算: 『{名}』{前}件 → {実際}件（増えた）", file=sys.stderr)
        else:
            print(f"  検算: 『{名}』{実際}件を基準として記録した", file=sys.stderr)
    else:
        print(f"  検算: 『{名}』{実際}件（前回と同じ）", file=sys.stderr)
    return 実際
