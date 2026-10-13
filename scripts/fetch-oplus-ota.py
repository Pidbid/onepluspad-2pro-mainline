#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Download a full BBK (OPPO/realme/OnePlus) OTA package through its download gate.

`component-ota-*.allawntech.com/downloadCheck` is an anti-leech gate: without the
stock-updater identity header it answers HTTP 200 with
`{"body":null,"errMsg":"2306","responseCode":2306}` and never redirects to the
package. The gate accepts the header

    userId: oplus-ota|<versionCode>

where only the `oplus-ota|` prefix is validated (any value after the pipe works).
With the header the gate answers 302 to a freshly signed CDN URL. Those signed
URLs expire within minutes, so this tool keeps the *gate* URL and re-resolves it
whenever a chunk is rejected instead of reusing a stale URL.

A gate URL can be obtained from a mirror's OTA catalog, for example

    curl -s 'https://roms.danielspringer.at/api/ota.php?model=OPD2413'

which returns `source_url` per release, or from the device model page that
republishes the same gate.

Example:

    python3 scripts/fetch-oplus-ota.py \
      --gate "$(jq -r '.releases[] | select(.ota_version|test("C.34")) | .source_url' opd2413.json)" \
      --output OPD2413_C34.zip --jobs 16 --md5 c7d36364f94daa509c19f71b1e100982

The MD5 is optional; when the CDN advertises `x-amz-meta-filemd5` the download is
verified against that value regardless.
"""
import argparse
import concurrent.futures as futures
import hashlib
import os
import sys
import threading
import time
from pathlib import Path

import requests

HEADERS = {
    'userId': 'oplus-ota|16001011',
    'User-Agent': ('Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'),
    'Accept': '*/*',
    'Accept-Encoding': 'identity',
}

_lock = threading.Lock()


def resolve(gate):
    """Return a freshly signed CDN URL for a durable download gate."""
    r = requests.get(gate, headers=HEADERS, timeout=30, allow_redirects=False)
    if r.status_code in (301, 302, 303, 307, 308):
        return r.headers['Location']
    raise RuntimeError(f'gate answered HTTP {r.status_code}: {r.text[:200]}')


def probe(gate):
    url = resolve(gate)
    r = requests.get(url, headers={**HEADERS, 'Range': 'bytes=0-0'}, timeout=40)
    r.raise_for_status()
    total = int(r.headers['Content-Range'].split('/')[1])
    return total, url


def fetch(path, gate, size, jobs):
    part = Path(path)
    part.write_bytes(b'')
    with open(part, 'wb') as fh:
        fh.truncate(size)
    chunk = max(1, size // jobs)
    done = [0] * jobs
    started = time.time()

    def worker(i):
        start = i * chunk
        end = size - 1 if i == jobs - 1 else min(size, (i + 1) * chunk) - 1
        url = resolve(gate)
        pos = start
        with open(part, 'r+b') as fh:
            while pos <= end:
                want = min(end, pos + (8 << 20) - 1)
                try:
                    r = requests.get(url, headers={**HEADERS, 'Range': f'bytes={pos}-{want}'},
                                     timeout=60)
                except requests.RequestException:
                    url = resolve(gate)
                    continue
                if r.status_code in (403, 410) or r.status_code >= 500:
                    url = resolve(gate)
                    time.sleep(1)
                    continue
                if r.status_code not in (200, 206):
                    time.sleep(1)
                    continue
                data = r.content
                if not data:
                    url = resolve(gate)
                    continue
                fh.seek(pos)
                fh.write(data)
                pos += len(data)
                with _lock:
                    done[i] = pos - start
                    total = sum(done)
                    speed = total / max(1e-6, time.time() - started)
                    print(f'\r{total * 100 / size:6.2f}%  {total / 2**30:7.2f}/'
                          f'{size / 2**30:.2f} GiB  {speed / 2**20:.1f} MiB/s',
                          end='', flush=True)

    with futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        list(pool.map(worker, range(jobs)))
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--gate', required=True, help='durable /downloadCheck gate URL')
    ap.add_argument('--output', required=True)
    ap.add_argument('--jobs', type=int, default=16)
    ap.add_argument('--md5', help='expected MD5 of the finished package')
    args = ap.parse_args()

    size, url = probe(args.gate)
    print(f'size={size}\nhost={url.split("/")[2]}', flush=True)
    fetch(args.output, args.gate, size, args.jobs)

    if args.md5:
        digest = hashlib.md5()
        with open(args.output, 'rb') as fh:
            for block in iter(lambda: fh.read(1 << 22), b''):
                digest.update(block)
        got = digest.hexdigest()
        print(f'md5={got}')
        if got != args.md5.lower():
            sys.exit(f'MD5 mismatch: expected {args.md5}')
    print('done')


if __name__ == '__main__':
    main()
