// 宍粟市観光協会「しそうツーリズムガイド」RSS(/news/feed) から「イベント」を取得し、
// Firestore の broadcast/city_news に書き込む中継スクリプト。
// GitHub Actions で定期実行する想定。認証は環境変数 FB_EMAIL / FB_PASSWORD（GitHub Secrets）。
// ※ apiKey はWeb公開前提の識別子（秘密ではない）。書込防御はFirestoreルール側（管理者メールのみ許可）。
//
// 依存ゼロ（Node 20+ の組み込み fetch を使用）。ローカル試験:
//   FB_EMAIL=... FB_PASSWORD=... node scripts/fetch-city-news.mjs

const PROJECT = 'shisochan-net';
const API_KEY = 'AIzaSyCrgNeYr8vLUHzEJMFIgSDm-WheRCPVS3Q';
const RSS_URL = 'https://shiso.or.jp/news/feed/';
const EMAIL = process.env.FB_EMAIL;
const PASS  = process.env.FB_PASSWORD;
const MAX_ITEMS = 6;              // 表示は最新6件まで
// このRSSはカテゴリ情報を持たない(news一覧)。タイトルのキーワードで「イベント/お知らせ」を判定する。
const EVENT_RE = /祭|花火|イベント|大会|ライド|フェス|マルシェ|ライブ|コンサート|マラソン|ウォーク/;

function decode(s){
  return String(s || '')
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#0?39;/g, "'").replace(/<[^>]+>/g, '')
    .replace(/\s+/g, ' ').trim();
}

function parseItems(xml){
  const out = [];
  const re = /<item>([\s\S]*?)<\/item>/g;
  let m;
  while ((m = re.exec(xml))) {
    const block = m[1];
    const tag = (t) => {
      const mm = block.match(new RegExp('<' + t + '[^>]*>([\\s\\S]*?)<\\/' + t + '>'));
      return mm ? decode(mm[1]) : '';
    };
    const title = tag('title');
    const pub = tag('pubDate');
    let date = '';
    if (pub) { const d = new Date(pub); if (!isNaN(d)) date = (d.getMonth() + 1) + '月' + d.getDate() + '日'; }
    if (title) {
      out.push({ type: EVENT_RE.test(title) ? 'event' : 'notice', title, date });
    }
  }
  return out.slice(0, MAX_ITEMS);
}

async function signIn(){
  const r = await fetch('https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=' + API_KEY, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASS, returnSecureToken: true })
  });
  const j = await r.json();
  if (!j.idToken) throw new Error('signIn failed: ' + JSON.stringify(j));
  return j.idToken;
}

async function writeFirestore(idToken, items){
  const fields = {
    items: { arrayValue: { values: items.map(it => ({ mapValue: { fields: {
      type:  { stringValue: it.type },
      title: { stringValue: it.title },
      date:  { stringValue: it.date }
    }}}))}},
    source:    { stringValue: '出典：しそうツーリズムガイド（宍粟市観光協会）' },
    updatedAt: { stringValue: new Date().toISOString() }
  };
  const url = 'https://firestore.googleapis.com/v1/projects/' + PROJECT +
    '/databases/(default)/documents/broadcast/city_news' +
    '?updateMask.fieldPaths=items&updateMask.fieldPaths=source&updateMask.fieldPaths=updatedAt';
  const r = await fetch(url, {
    method: 'PATCH',
    headers: { 'Authorization': 'Bearer ' + idToken, 'Content-Type': 'application/json' },
    body: JSON.stringify({ fields })
  });
  if (!r.ok) throw new Error('write failed: ' + r.status + ' ' + await r.text());
}

async function main(){
  if (!EMAIL || !PASS) { console.log('FB_EMAIL / FB_PASSWORD 未設定のためスキップ（GitHub Secrets登録後に有効化）'); return; }
  const xml = await (await fetch(RSS_URL, { headers: { 'User-Agent': 'shisochan-net-bot' } })).text();
  const items = parseItems(xml);
  console.log('取得イベント: ' + items.length + '件');
  items.forEach(it => console.log(' - [' + it.date + '] ' + it.title));
  if (!items.length) { console.log('イベントが0件のため書き込みをスキップ'); return; }
  const idToken = await signIn();
  await writeFirestore(idToken, items);
  console.log('Firestore broadcast/city_news に ' + items.length + '件 書き込み完了');
}

main().catch(e => { console.error(e); process.exit(1); });
