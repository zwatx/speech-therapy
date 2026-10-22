"""Closed, pinned static inventory; never accepts a caller file path."""
import stat
import os
from pathlib import Path
from journey.catalog import read_owned
from mobile_admission import contract

ROOT=Path(__file__).resolve().parents[1]/'visual'
MANIFEST_SHA='ac02f689b9ec4a105f4d0e6aa4093698d3ffbf430acc4d1849426c7f0bb3ecf1'
FILES={
    '/visual/vision_bundle.mjs':('vision_bundle.mjs','text/javascript; charset=utf-8',200000),
    '/visual/wasm/vision_wasm_internal.js':('wasm/vision_wasm_internal.js','text/javascript; charset=utf-8',400000),
    '/visual/wasm/vision_wasm_internal.wasm':('wasm/vision_wasm_internal.wasm','application/wasm',12000000),
    '/visual/wasm/vision_wasm_nosimd_internal.js':('wasm/vision_wasm_nosimd_internal.js','text/javascript; charset=utf-8',400000),
    '/visual/wasm/vision_wasm_nosimd_internal.wasm':('wasm/vision_wasm_nosimd_internal.wasm','application/wasm',12000000),
    '/visual/face_landmarker.task':('face_landmarker.task','application/octet-stream',4000000),
    '/visual/public-portrait.jpg':('public-portrait.jpg','image/jpeg',1400000),
    '/visual/LICENSE.mediapipe.txt':('LICENSE.mediapipe.txt','text/plain; charset=utf-8',20000),
}


def _directory(path):
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid():raise ValueError('visual_unavailable')


def read_asset(route):
    if route not in FILES and route!='/visual/asset-manifest.json':raise ValueError('not_found')
    _directory(ROOT)
    raw=read_owned(ROOT/'asset-manifest.json',100000)
    if contract.sha(raw)!=MANIFEST_SHA:raise ValueError('visual_unavailable')
    manifest=contract.strict_json(raw);assets=manifest.get('assets')
    if type(assets) is not list or len(assets)!=len(FILES):raise ValueError('visual_unavailable')
    records={}
    for record in assets:
        if type(record) is not dict or set(record)!=set(('route','file','mediaType','bytes','sha256','sourceUrl','sourceVersion','license','purpose')):raise ValueError('visual_unavailable')
        name=record['route']
        if name not in FILES or name in records:raise ValueError('visual_unavailable')
        filename,media,limit=FILES[name]
        if record['file']!=filename or record['mediaType']!=media or type(record['bytes']) is not int or not 0<record['bytes']<=limit:raise ValueError('visual_unavailable')
        records[name]=record
    if route=='/visual/asset-manifest.json':return raw,'application/json; charset=utf-8'
    filename,media,limit=FILES[route];record=records[route]
    if filename.startswith('wasm/'):_directory(ROOT/'wasm')
    data=read_owned(ROOT/filename,limit)
    if len(data)!=record['bytes'] or contract.sha(data)!=record['sha256']:raise ValueError('visual_unavailable')
    return data,media
