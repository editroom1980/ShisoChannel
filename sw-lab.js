// しそチャンNET（検証版 lab）の「新番組のお知らせ」の受け皿（2026-10-22）
// ★役目は通知を受け取ることだけ。ページを溜め込む役目（fetch の横取り）は一切持たない
//   ＝アプリは今までどおり「開けば必ず最新」。番組表を直したのに古い画面が出る事故を起こさない
// 届く知らせの中身は空。受付係の /push/latest を読みに行き「新番組：○○」を出す
var API = 'https://vault.shisochan.net';
var PAGE = 'lab.html?src=home';      // 通知を押した時に開くページ（本番の sw.js では './?src=home'）

self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });

// アイコンの数字は「まだ見ていない新番組の数」。アプリを開くと、アプリがこの数を正しい値に直す
function bumpBadge() {
  return caches.open('sc-ntf').then(function (c) {
    return c.match('/__badge').then(function (m) { return m ? m.text() : '0'; })
      .then(function (t) {
        var n = (parseInt(t, 10) || 0) + 1;
        return c.put('/__badge', new Response(String(n))).then(function () { return n; });
      });
  }).catch(function () { return 1; });
}

self.addEventListener('push', function (e) {
  e.waitUntil(
    fetch(API + '/push/latest', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; })
      .then(function (info) {
        return bumpBadge().then(function (n) {
          try { if (self.navigator.setAppBadge) self.navigator.setAppBadge(n).catch(function () {}); } catch (_) {}
          var url = PAGE + (info.key ? '&prog=' + encodeURIComponent(info.key) : '');
          // ★iPhone は、知らせが届いたら必ず通知を出さないと受け取りを止められる＝中身が読めなくても出す
          return self.registration.showNotification('しそチャンNET', {
            body: info.title ? '新番組：' + info.title : '新しい番組が入りました',
            icon: 'icon-192.png',
            tag: 'shisochan-new',
            renotify: true,
            data: { url: url }
          });
        });
      })
  );
});

// 通知を押した：アプリが開いていればそれを前に出して新番組のページへ、無ければ開く
self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var url = new URL((e.notification.data && e.notification.data.url) || PAGE, self.registration.scope).href;
  e.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (cs) {
      for (var i = 0; i < cs.length; i++) {
        var c = cs[i];
        if (c.url.indexOf(self.registration.scope) === 0 && 'focus' in c) {
          return c.focus().then(function (w) { return w && w.navigate ? w.navigate(url) : null; }).catch(function () {});
        }
      }
      return self.clients.openWindow ? self.clients.openWindow(url) : null;
    })
  );
});
