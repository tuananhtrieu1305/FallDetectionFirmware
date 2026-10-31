"""Materialize CRC-checked UNIVRFall members, reusing 64 KiB range cache.

Pinned Zenodo v1 ZIP. Raw data stays outside the checkout. No source code runs.
Use --subset all to include OnField; laboratory is the first release dependency.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import re
import time
import threading
import zipfile

import requests

URL = 'https://zenodo.org/api/records/18346755/files/UniVrFall_Dataset.zip/content'
SIZE = 674726914
BLOCK = 65536


class CachedArchive(io.RawIOBase):
    def __init__(self, cache):
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.position = 0
        self.session = requests.Session()
        self.memory = {}

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset + (self.position if whence == 1 else SIZE if whence == 2 else 0)
        if self.position < 0:
            raise ValueError('Negative seek')
        return self.position

    def block(self, start):
        end = min(SIZE - 1, start + BLOCK - 1)
        path = self.cache / f'{start:012d}.bin'
        if start not in self.memory:
            if path.exists() and path.stat().st_size == end - start + 1:
                data = path.read_bytes()
            else:
                for attempt in range(4):
                    try:
                        with self.session.get(URL, headers={'Range': f'bytes={start}-{end}',
                                                             'Accept-Encoding': 'identity'},
                                              timeout=(15, 90), stream=True) as response:
                            response.raise_for_status()
                            if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{SIZE}':
                                raise ValueError('Unexpected source ZIP range/size')
                            data = response.content
                        if len(data) != end - start + 1:
                            raise ValueError('Truncated range')
                        path.write_bytes(data)
                        break
                    except requests.RequestException:
                        if attempt == 3:
                            raise
                        time.sleep(1 + attempt)
            # Bound RAM for OnField; cache bytes remain on disk.
            if len(self.memory) > 512:
                self.memory.clear()
            self.memory[start] = data
        return self.memory[start]

    def read(self, size=-1):
        size = min(SIZE - self.position, size if size >= 0 else SIZE - self.position)
        if size <= 0:
            return b''
        parts = []
        while size:
            start = self.position // BLOCK * BLOCK
            offset = self.position - start
            chunk = self.block(start)[offset:offset + size]
            parts.append(chunk)
            self.position += len(chunk)
            size -= len(chunk)
        return b''.join(parts)


def acquire(root, subset, ready_only=False,workers=8):
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'full_download_manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if subset == 'all' and not ready_only:
        # Small ranges avoid the extremely slow full-body transfer of this source.
        span=16*BLOCK
        missing = [start for start in range(0, SIZE, span)
                   if any(not (root/'ranges'/f'{i:012d}.bin').exists() or
                          (root/'ranges'/f'{i:012d}.bin').stat().st_size!=min(BLOCK,SIZE-i)
                          for i in range(start,min(SIZE,start+span),BLOCK))]
        local = threading.local()
        def fetch(start):
            if not hasattr(local, 'session'):
                local.session=requests.Session()
            end=min(SIZE-1,start+span-1)
            for attempt in range(5):
                try:
                    with local.session.get(URL,headers={'Range':f'bytes={start}-{end}',
                                                       'Accept-Encoding':'identity'},
                                           stream=True,timeout=(15,90)) as response:
                        if response.status_code==429:
                            time.sleep(min(60,max(1,int(response.headers.get('Retry-After','60')))))
                            continue
                        response.raise_for_status()
                        if response.status_code!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{SIZE}':
                            raise ValueError('Invalid span response')
                        position=start
                        for data in response.iter_content(BLOCK):
                            expected=min(BLOCK,end-position+1)
                            if len(data)!=expected: raise ValueError('Short span block')
                            (root/'ranges'/f'{position:012d}.bin').write_bytes(data)
                            position+=len(data)
                        if position!=end+1: raise ValueError('Incomplete span')
                    return
                except requests.RequestException:
                    if attempt==4: raise
                    time.sleep(min(30,2**attempt))
            raise RuntimeError('Source remains rate limited after five attempts')
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for done, _ in enumerate(pool.map(fetch, missing), 1):
                print(json.dumps(dict(megabyte_spans_downloaded=done, missing_spans=len(missing))), flush=True)
        digest=hashlib.md5()
        byte_count=0
        for start in range(0,SIZE,BLOCK):
            data=(root/'ranges'/f'{start:012d}.bin').read_bytes()
            digest.update(data);byte_count+=len(data)
        if byte_count!=SIZE or digest.hexdigest()!='d14190e98749bc583f69f1df3e5bafc0':
            raise ValueError('Full ZIP size/MD5 differs from pinned source')
        (root/'archive_verification.json').write_text(json.dumps(dict(bytes=byte_count,
                       md5=digest.hexdigest(),status='PASS'),indent=2),encoding='utf-8')
    reader=CachedArchive(root/'ranges')
    if ready_only:
        original_block=reader.block
        def cached_only(start):
            path=root/'ranges'/f'{start:012d}.bin'
            if not path.exists() or path.stat().st_size!=min(BLOCK,SIZE-start):
                raise FileNotFoundError(f'Range {start} not complete yet')
            return original_block(start)
        reader.block=cached_only
    materialized=0
    with zipfile.ZipFile(reader) as archive:
        entries = [e for e in archive.infolist() if not e.is_dir() and
                   ('/laboratory/' in e.filename or subset == 'all')]
        for i, entry in enumerate(entries):
            name = entry.filename
            if not re.fullmatch(r'UniVrFall_Dataset/(laboratory|OnField)/[^\\]+', name):
                raise ValueError(f'Unexpected member {name}')
            key = hashlib.sha256(name.encode()).hexdigest()[:12] + '_' + Path(name).name
            path = root / 'full_members' / key
            previous = manifest.get(name)
            if not (previous and path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == previous['sha256']):
                if ready_only:
                    start=entry.header_offset//BLOCK*BLOCK
                    end=entry.header_offset+30+len(entry.filename.encode())+len(entry.extra)+entry.compress_size+32
                    if any(not (root/'ranges'/f'{p:012d}.bin').exists() or
                           (root/'ranges'/f'{p:012d}.bin').stat().st_size!=min(BLOCK,SIZE-p)
                           for p in range(start,min(SIZE,end),BLOCK)):
                        continue
                data = archive.read(entry)  # validates ZIP CRC, including cached ranges
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                manifest[name] = dict(file=str(path.resolve()), sha256=hashlib.sha256(data).hexdigest(),
                                      bytes=len(data), crc32=f'{entry.CRC:08x}', crc_verified=True)
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            materialized+=1
            if (i + 1) % 100 == 0 or '/OnField/' in name:
                print(json.dumps(dict(materialized=i+1, total=len(entries), member=name)), flush=True)
    print(json.dumps(dict(subset=subset, materialized=materialized, expected=len(entries),
                         ready_only=ready_only,manifest=str(manifest_path))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--subset', choices=['laboratory', 'all'], default='laboratory')
    parser.add_argument('--ready-only',action='store_true',help='Materialize only complete cached members; no HTTP')
    parser.add_argument('--workers',type=int,choices=range(1,33),default=8)
    args = parser.parse_args()
    acquire(args.raw, args.subset,args.ready_only,args.workers)
