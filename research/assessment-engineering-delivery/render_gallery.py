"""Build a fixed local public-reference gallery; no participant or credential data."""
import html
import json
from pathlib import Path
from validate_content import validate, CONTENT, ROOT

WORK = ROOT / 'work/assessment-real-data-20261004'

def render():
    validate()
    decisions = json.loads((CONTENT / 'content-decisions.json').read_bytes())
    illustrations = json.loads((CONTENT / 'illustrations.json').read_bytes())
    assets = json.loads((WORK / 'references/assets.json').read_bytes())
    by_word = {a['word']: a for a in assets['assets']}
    cards = []
    for image in illustrations['illustrations']:
        word = image['word']
        rows = [d for d in decisions['decisions'] if d['word'] == word]
        asset = by_word.get(word)
        reference = '<p class="reference">Reference download pending</p>'
        if asset:
            reference = '<audio controls aria-label="Reference audio: ' + html.escape(word, quote=True) + '" preload="none" src="/audio/' + html.escape(asset['sourceWord']) + '.wav"></audio>'
            reference += '<p class="reference">' + html.escape(asset['declaredVariety']) + ' · <a href="' + html.escape(asset['sourcePageUrl'], quote=True) + '">' + html.escape(asset['author']) + '</a> · <a href="' + html.escape(asset['licenseUrl'], quote=True) + '">' + html.escape(asset['licenseId']) + '</a></p>'
        detail = '; '.join(d['targetPhone'] + ' · ' + d['position'] for d in rows)
        if word == 'treasure': detail += ' · assessment unavailable for ZH'
        if word == 'banana': detail += ' · first middle N selected'
        cards.append('<article><div class="picture">' + (CONTENT / image['path']).read_text() + '</div><h2>' + html.escape(word) + '</h2><p class="target">' + html.escape(detail) + '</p>' + reference + '</article>')
    body = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Speech assessment · engineering reference pack</title><style>
*{box-sizing:border-box}body{margin:0;color:#252522;background:#f5f3ed;font:16px/1.5 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:48px 32px}header{max-width:780px;margin-bottom:34px}.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#64645a}h1{font-size:38px;line-height:1.12;letter-spacing:-.035em;margin:10px 0 18px;font-weight:650}header p{color:#5b5a52}nav{display:flex;gap:12px;flex-wrap:wrap;font-size:13px}nav span{border:1px solid #d8d5ca;border-radius:20px;padding:6px 12px;background:#faf9f5}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}article{background:#fff;border:1px solid #dedbd1;border-radius:14px;padding:18px;min-width:0}.picture{height:160px;display:flex;align-items:center;justify-content:center}.picture svg{height:150px;width:180px}h2{font-size:21px;margin:16px 0 3px;font-weight:600}.target{font-size:12px;min-height:36px;color:#6d6a60;margin:0 0 12px}audio{width:100%;height:32px}.reference{font-size:11px;line-height:1.45;overflow-wrap:break-word;color:#767367;min-height:32px}.reference a:last-child{white-space:nowrap}a{color:#605b41;text-underline-offset:3px}footer{border-top:1px solid #d8d5ca;margin-top:36px;padding-top:18px;font-size:13px;color:#68655c;max-width:860px}@media(max-width:1000px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:700px){main{padding:30px 18px}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}h1{font-size:30px}}
</style></head><body><main><header><div class="eyebrow">Speech assessment / reference pack</div><h1>Pictures, words &amp; reference audio</h1><p>Preview the pictures and reference audio for the assessment. Recording and replay of your own response happen in the assessment screen. A caregiver can read the word aloud and operate those controls.</p><nav><span>15 engineering prompts</span><span>13 original illustrations</span><span>Professional review: after the product is finished</span></nav></header><section class="grid">'''
    body += ''.join(cards)
    body += '</section><footer>Engineering content accepted through model review. Reference audio was converted to WAV without trimming, normalization or speed changes. Source attribution and licenses are retained, including share-alike terms where applicable. These recordings have unknown speaker ages and do not establish child accuracy or produced-phone truth. No scores, corrective instruction or diagnosis are provided.</footer></main></body></html>'
    (WORK / 'gallery.html').write_text(body)
    (WORK / 'gallery.html').chmod(0o600)
    return body

if __name__ == '__main__':
    render()
    print('gallery written')
