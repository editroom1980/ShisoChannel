/* しそチャンNET：番組の間のCMの入り方（2026-11-21）
 *
 * ★ページ（lab.html・index.html）と管理アプリ（kanri.html）が、同じこのファイルを読む。
 *   同じ計算を2か所に書くと必ずずれる（CLAUDE.md 第2部署）。テレビのデモも保存して使う。
 *
 * 決まり（依頼者 2026-11-21「どのCMをどこに入れるか、1日に何回流すか、頻度は…設定できるように」「番組1本ごと」「番組表には入れない」）
 *  ・CMは番組と番組の間にだけ入る。1回の休みに流すのは1本
 *  ・その日の流れは「放送開始の時刻から、番組 → (CM) → 番組 …」を順に積み上げて決める。
 *    同じ設定・同じ日付なら、どの端末でも同じ流れになる（時刻だけで決まる）
 *  ・CMの時間も流れに含めるので、CMのあとの番組は頭から始まる
 *  ・CMの条件：
 *      on        … false なら流さない
 *      from / to … 流す期間（'YYYY-MM-DD'。空なら限らない。両端を含む）
 *      tFrom/tTo … 流す時間帯（'HH:MM'。休みの始まりの時刻がこの間なら流す。空なら限らない）
 *      every     … 番組◯本ごと（その日の何本目のあとか。1＝毎回）
 *      max       … 1日の上限（0か空なら上限なし）
 *      after     … この番組のあとだけ（番組の見分け名の並び。空なら、どの番組のあとでもよい）
 *  ・条件に合うCMが複数ある時は、その日まだ流れた回数の少ないものを選ぶ（同じなら一覧の上から）＝順番に替わる
 *  ・その日に入るCMが1本も無い時は null を返す。ページは今までの計算（CMの無い計算）をそのまま使う
 */
(function (g) {
  'use strict';
  function hm(s) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(String(s || ''));
    if (!m) return null;
    var h = +m[1], mi = +m[2];
    if (h > 24 || mi > 59) return null;
    return h * 3600 + mi * 60;
  }
  function plenOf(p) {
    return (p && typeof p.sec === 'number' && p.sec > 0) ? p.sec : ((p && typeof p.dur === 'number' && p.dur > 0) ? p.dur * 60 : 0);
  }
  // 番組の見分け名。ページの progKey・管理アプリの progKeyK と同じ（YouTube の ID が無ければ own~動画保管庫の名前）
  function keyOf(p) {
    if (!p) return '';
    if (p.ytId && String(p.ytId).indexOf('own~') !== 0) return String(p.ytId);
    if (p.vid) return 'own~' + p.vid;
    return p.ytId ? String(p.ytId) : '';
  }
  function vidOk(s) { return typeof s === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(s); }
  function cmOk(c) { return !!c && c.on !== false && typeof c.id === 'string' && c.id.length > 0 && vidOk(c.vid) && typeof c.sec === 'number' && c.sec > 0 && c.sec <= 600; }
  function inDays(c, day) { return (!c.from || c.from <= day) && (!c.to || day <= c.to); }
  function inTime(c, t) {
    var a = hm(c.tFrom), b = hm(c.tTo);
    if (a != null && t < a) return false;
    if (b != null && t >= b) return false;
    return true;
  }
  // 1日の流れ。cycle＝番組の並び／airS・airE＝放送の時（0〜24）／cms＝CMの設定の並び／day＝'YYYY-MM-DD'
  // 戻り値：null（CMの入らない日）か {day, seg:[…], cms:{id:回数}}
  //   seg の1つ：番組 {k:'p', p:番号, c:何周目, st:始まり(0時からの秒), len:長さ}
  //              CM   {k:'c', id, vid, title, sponsor, p:直前の番組の番号, c:直前の番組の周, n:その日の何本目の番組のあとか, st, len}
  function build(cycle, airS, airE, cms, day) {
    if (!cycle || !cycle.length) return null;
    var act = (cms || []).filter(function (c) { return cmOk(c) && inDays(c, day); });
    if (!act.length) return null;
    var lens = cycle.map(plenOf), keys = cycle.map(keyOf);
    for (var i = 0; i < lens.length; i++) if (!(lens[i] > 0)) return null;   // 長さの分からない番組がある日は組まない（今までの計算）
    var t = airS * 3600, end = airE * 3600, seg = [], c = 0, p = 0, n = 0, cnt = {}, any = false, guard = 0;
    while (t < end && guard++ < 20000) {
      seg.push({ k: 'p', p: p, c: c, st: t, len: lens[p] });
      t += lens[p]; n++;
      if (t < end) {
        var best = null, bestCnt = 0;
        for (var j = 0; j < act.length; j++) {
          var m = act[j], every = Math.max(1, Math.floor(+m.every || 1)), max = Math.floor(+m.max || 0), got = cnt[m.id] || 0;
          if (n % every !== 0) continue;
          if (max > 0 && got >= max) continue;
          if (!inTime(m, t)) continue;
          if (m.after && m.after.length && m.after.indexOf(keys[p]) < 0) continue;
          if (best === null || got < bestCnt) { best = m; bestCnt = got; }
        }
        if (best) {
          seg.push({ k: 'c', id: best.id, vid: best.vid, title: best.title || '', sponsor: best.sponsor || '', p: p, c: c, n: n, st: t, len: best.sec });
          cnt[best.id] = (cnt[best.id] || 0) + 1; any = true;
          t += best.sec;
        }
      }
      p++; if (p >= cycle.length) { p = 0; c++; }
    }
    if (!any) return null;
    return { day: day, seg: seg, cms: cnt };
  }
  // t（0時からの秒）に流れている区切りの番号（無ければ -1）
  function segAt(plan, t) {
    if (!plan) return -1;
    var s = plan.seg, lo = 0, hi = s.length - 1, r = -1;
    while (lo <= hi) { var mid = (lo + hi) >> 1; if (s[mid].st <= t) { r = mid; lo = mid + 1; } else hi = mid - 1; }
    return r;
  }
  function dayOf(d) {
    function p2(x) { return (x < 10 ? '0' : '') + x; }
    return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate());
  }
  g.CMPLAN = { build: build, segAt: segAt, keyOf: keyOf, plenOf: plenOf, hm: hm, cmOk: cmOk, dayOf: dayOf };
})(typeof window !== 'undefined' ? window : globalThis);
