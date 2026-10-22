# -*- coding: utf-8 -*-
"""動画保管庫の変換（GitHub の自動処理 vault-convert.yml から動く）。
1. 受付係に「変換待ち」を1本もらう（無ければ何もせず終わる）
2. 元の動画を受け取り、Mac の hls_encode.sh と同じ作り（1080p/720p/480p・2秒ごとのキーフレーム・6秒ずつ）に変換する
3. できたファイルを受付係へ送る（受付係が動画保管庫に置く）
4. 長さを添えて「終わった」と知らせる（受付係が目録 catalog.json に1行足す）
失敗したら「失敗」と知らせる（受付係が1回までやり直しに回す）。
証明書（OIDC）は数分で切れるので、使うたびに取り直す。"""
import json, os, re, subprocess, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

API = 'https://vault.shisochan.net'
AUD = 'shisochan-vault'
_tok = {'v': '', 't': 0}

def token():
    if time.time() - _tok['t'] < 120 and _tok['v']:
        return _tok['v']
    u = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'] + '&audience=' + AUD
    r = urllib.request.Request(u, headers={'Authorization': 'bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    v = json.load(urllib.request.urlopen(r, timeout=30))['value']
    print('::add-mask::' + v)
    _tok.update(v=v, t=time.time())
    return v

def call(method, path, body=None, ctype='application/json', timeout=120):
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + token(), 'Content-Type': ctype,
                                        # ★Python の標準の名乗り（Python-urllib）は Cloudflare の入口で403（1010）にされ、受付係まで届かない
                                        'User-Agent': 'shisochan-vault-convert/1.0'})
    try:
        return urllib.request.urlopen(r, timeout=timeout)
    except urllib.error.HTTPError as e:
        # 受付係の答え（断った理由）を記録に残す
        raise RuntimeError('%s %s → %d %s' % (method, path, e.code, e.read().decode('utf-8', 'replace')[:300]))

def main():
    res = call('GET', '/act/next')
    if res.status == 204:
        print('変換待ちはありません'); return
    job = json.load(res); vid = job['vid']
    print('変換する:', vid, job['title'], job['size'], 'バイト')
    try:
        run(job)
    except Exception as e:
        msg = '%s: %s' % (type(e).__name__, e)
        print('失敗:', msg)
        try: call('POST', '/act/fail', {'vid': vid, 'msg': msg[:300]})
        except Exception as e2: print('失敗の知らせも届かない:', e2)
        sys.exit(1)

def run(job):
    vid = job['vid']
    t0 = time.time()
    subprocess.run('sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg >/dev/null',
                   shell=True, check=True)
    print(subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True).stdout.splitlines()[0])
    # 元の動画を受け取る
    with call('GET', '/act/src/' + vid, timeout=600) as r, open('src.bin', 'wb') as f:
        while True:
            b = r.read(8 << 20)
            if not b: break
            f.write(b)
    size = os.path.getsize('src.bin')
    if size != job['size']: raise RuntimeError('受け取った大きさが違う %d / %d' % (size, job['size']))
    print('受け取り: %.1f秒' % (time.time() - t0))
    # 変換（Mac の hls_encode.sh と同じ作り）
    for v in ('v0', 'v1', 'v2'): os.makedirs('out/' + v, exist_ok=True)
    t1 = time.time()
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-stats', '-y', '-i', 'src.bin',
        '-filter_complex', '[0:v:0]split=3[a][b][c];[b]scale=-2:720:flags=lanczos[b2];[c]scale=-2:480:flags=lanczos[c2]',
        '-map', '[a]', '-c:v:0', 'libx264', '-b:v:0', '5000k', '-maxrate:v:0', '5350k', '-bufsize:v:0', '7500k',
        '-map', '[b2]', '-c:v:1', 'libx264', '-b:v:1', '2800k', '-maxrate:v:1', '3000k', '-bufsize:v:1', '4200k',
        '-map', '[c2]', '-c:v:2', 'libx264', '-b:v:2', '1200k', '-maxrate:v:2', '1300k', '-bufsize:v:2', '1800k',
        '-map', '0:a:0', '-map', '0:a:0', '-map', '0:a:0', '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000',
        '-preset', 'medium', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
        '-g', '60', '-keyint_min', '60', '-sc_threshold', '0', '-force_key_frames', 'expr:gte(t,n_forced*2)',
        '-f', 'hls', '-hls_time', '6', '-hls_playlist_type', 'vod', '-hls_flags', 'independent_segments',
        '-hls_segment_type', 'mpegts', '-hls_segment_filename', 'out/v%v/seg_%04d.ts',
        '-master_pl_name', 'master.m3u8', '-var_stream_map', 'v:0,a:0 v:1,a:1 v:2,a:2', 'out/v%v/index.m3u8'],
        check=True)
    print('変換: %.1f秒' % (time.time() - t1))
    # 見本の絵（管理アプリの一覧に出す）：動画の1割の所の1コマ。作れなくても変換は失敗にしない
    try:
        dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', 'src.bin'],
                                   capture_output=True, text=True, check=True).stdout.strip() or 0)
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', '%.2f' % (dur * 0.1), '-i', 'src.bin',
                        '-frames:v', '1', '-vf', 'scale=640:-2', '-q:v', '3', 'out/thumb.jpg'], check=True)
    except Exception as e:
        print('見本の絵は作れなかった:', e)
    os.remove('src.bin')
    # 送る（目次は最後に送る＝途中で止まっても、目次だけあって中身が無い状態を作らない）
    files = []
    for root, _, names in os.walk('out'):
        for n in names: files.append(os.path.relpath(os.path.join(root, n), 'out'))
    segs = sorted(f for f in files if f.endswith('.ts'))
    lists = (['thumb.jpg'] if 'thumb.jpg' in files else []) + sorted(f for f in files if f.endswith('.m3u8') and f != 'master.m3u8') + ['master.m3u8']
    if 'master.m3u8' not in files or not segs: raise RuntimeError('変換の出来上がりが足りない')
    def put(f):
        for i in range(4):
            try:
                with open('out/' + f, 'rb') as fh: data = fh.read()
                call('PUT', '/act/obj/%s/%s' % (vid, f), data, 'application/octet-stream').read(); return
            except Exception as e:
                if i == 3: raise RuntimeError('送れない %s: %s' % (f, e))
                time.sleep(2 + i * 3)
    t2 = time.time()
    with ThreadPoolExecutor(8) as ex: list(ex.map(put, segs))
    for f in lists: put(f)
    print('送り込み: %d個 %.1f秒' % (len(segs) + len(lists), time.time() - t2))
    sec = sum(float(x) for x in re.findall(r'#EXTINF:([\d.]+)', open('out/v0/index.m3u8').read()))
    done = json.load(call('POST', '/act/done', {'vid': vid, 'sec': sec}))
    print('完了:', done['title'], '%.3f秒' % sec, '全体 %.1f秒' % (time.time() - t0))

if __name__ == '__main__':
    main()
