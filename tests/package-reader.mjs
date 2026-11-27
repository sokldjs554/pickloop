import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
let reader;
try { reader = await import('../web/package-reader.js'); } catch (error) {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
}
const registered = {'7310865074225':'God-Morgon-Apple-Juice'};
const symbol = (text, format='EAN-13') => ({text, format, isValid:true});
test('only a distinct verified optical barcode can claim a registry match', () => {
  assert.ok(reader, 'package photo reader must be implemented');
  assert.equal(reader.describeBarcodes([symbol('7310865074225')], registered).kind, 'registered');
  assert.equal(reader.describeBarcodes([symbol('7310865074225'), symbol('7310865074225')], registered).kind, 'registered');
  assert.equal(reader.describeBarcodes([symbol('7310865074225'), symbol('3123349011227')], registered).kind, 'multiple');
  assert.equal(reader.describeBarcodes([symbol('7310865074226'), symbol('7310865074225','QRCode')], registered).kind, 'empty');
  assert.equal(reader.describeBarcodes([{...symbol('7310865074225'), isValid:false}], registered).kind, 'empty');
  assert.equal(reader.describeBarcodes([symbol('036000291452','UPC-A')], registered).codes[0], '0036000291452');
  assert.equal(reader.describeBarcodes([symbol('3123349011227')], registered).kind, 'unregistered');
});
test('reads short retail codes, rejects bad checksums and blocks mixed-package orders', () => {
  const short = symbol('48512343', 'EAN-8');
  const upce = symbol('0012345000065', 'UPC-E');
  assert.deepEqual(reader.describeBarcodes([short], registered), {kind:'unregistered', codes:['48512343']});
  assert.equal(reader.describeBarcodes([short, symbol('0000048512343')], registered).codes.length, 1);
  assert.equal(reader.describeBarcodes([short], {'0000048512343':'short SKU'}).product, 'short SKU');
  assert.deepEqual(reader.describeBarcodes([upce, symbol('012345000065','UPC-A')], registered).codes, ['0012345000065']);
  assert.equal(reader.describeBarcodes([symbol('48512344','EAN-8')], registered).kind, 'empty');
  const several = reader.describeBarcodes([short, symbol('7310865074225')], registered);
  assert.equal(several.kind, 'multiple');
  assert.equal(reader.photoDecision(several, {product:registered['7310865074225']}, '').kind, 'hold');
});
test('the shipped optical decoder sees both retail barcodes on the same raster', async () => {
  const png = await readFile(new URL('./fixtures/two-retail-codes.png', import.meta.url));
  const wasm = await readFile(new URL('../web/vendor/package-reader/zxing_reader.wasm', import.meta.url));
  const symbols = await reader.decodeSymbols(png, wasm);
  assert.deepEqual(reader.describeBarcodes(symbols, registered),
    {kind:'multiple', codes:['48512343', '7310865074225']});
});
test('enforces pixel limits before creating a browser bitmap', () => {
  assert.ok(reader);
  const header = Uint8Array.from([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,0,0,0,24,0,0,0,16]);
  assert.deepEqual(reader.imageDimensions(header), {width:24,height:16});
  header.fill(255,16);
  assert.throws(()=>reader.imageDimensions(header));
  assert.throws(()=>reader.imageDimensions(new Uint8Array([0xff,0xd8,0xff,0xc0,0,1])));
  assert.throws(()=>reader.imageDimensions(new TextEncoder().encode('<svg/>')));
});
test('browser registry adds a distinct 250 mL carton to the three order SKUs', async () => {
  const registry = JSON.parse(await readFile(new URL('../web/vendor/package-reader/registry.json',import.meta.url)));
  const source = await readFile(new URL('../src/pickloop/pack_barcode.py',import.meta.url),'utf8');
  const declared = Object.fromEntries([...source.matchAll(/"(\d{13})": "(God-Morgon-[^"]+)"/g)].map(match=>match.slice(1)));
  assert.equal(Object.keys(declared).length,3);
  assert.deepEqual(registry,{...declared,'6415130089834':'God-Morgon-Orange-Juice-250ml'});
  assert.equal(reader.describeBarcodes([symbol('6415130089834')],registry).product, 'God-Morgon-Orange-Juice-250ml');
  assert.equal(reader.describeBarcodes([symbol('6415130089834')],declared).kind,'unregistered');
});
test('UPC-A cannot supply a registered EAN-13 with a nonzero country prefix', ()=>{
  assert.equal(reader.describeBarcodes([symbol('7310865074225','UPC-A')],registered).kind, 'empty');
});
test('reads ordinary JPEG and each supported WebP dimension header', ()=>{
  const jpeg = Uint8Array.from([255,216,255,224,0,4,1,1,255,192,0,8,8,0,17,0,33,1]);
  assert.deepEqual(reader.imageDimensions(jpeg), {width:33,height:17});
  function webp(chunk) {
    const header = new Uint8Array(30);
    header.set(Buffer.from('RIFF'),0); header.set(Buffer.from('WEBP'+chunk),8); return header;
  }
  const extended = webp('VP8X'); extended[24]=100; extended[27]=50;
  assert.deepEqual(reader.imageDimensions(extended), {width:101,height:51});
  const lossy = webp('VP8 '); lossy.set([157,1,42,80,0,60,0],23);
  assert.deepEqual(reader.imageDimensions(lossy), {width:80,height:60});
  const lossless = webp('VP8L'); lossless.set([47,99,64,12,0],20);
  assert.deepEqual(reader.imageDimensions(lossless), {width:100,height:50});
});
test('cancelling while OCR initializes terminates its worker', async ()=>{
  const previous = globalThis.Worker;
  let terminated = false;
  globalThis.Worker = class { postMessage() {} terminate() {terminated=true;} };
  try {
    const abort = new AbortController();
    const pending = reader.opticalText(new Uint8Array(),abort.signal);
    abort.abort();
    await assert.rejects(pending,{name:'AbortError'});
    assert.equal(terminated,true);
  } finally {
    globalThis.Worker=previous;
  }
});
test('choosing a different file suppresses an older pending read and a large file stays local', async ()=>{
  class Element extends EventTarget {
    textContent = '';
    hidden = false;
    disabled = false;
    setAttribute() {}
    removeAttribute() {}
  }
  const ids = Object.fromEntries(['reader','photo','cancel','status','barcode','text','result','example','credit','confirm','confirm-credit','submit'].map(id=>[id,new Element()]));
  ids.reader.querySelector=()=>ids.submit;
  const previous = Object.fromEntries(['document','window','HTMLCanvasElement','HTMLImageElement','fetch'].map(id=>[id,globalThis[id]]));
  globalThis.document={getElementById:id=>ids[id.replace('package-','')]};
  globalThis.window=Object.assign(new EventTarget(),{Worker:class {},AbortController,URL});
  globalThis.HTMLCanvasElement=class {toBlob() {}};
  globalThis.HTMLImageElement=class {decode() {}};
  try {
    await import('../web/package-reader.js?dom-fixture');
    ids.example.dataset = {src:'media/new-photos/grapefruit-front.jpg'};
    let sampleSignal;
    globalThis.fetch = (path, {signal}) => {
      assert.equal(path, ids.example.dataset.src);
      sampleSignal = signal;
      return new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => reject(signal.reason), {once:true});
      });
    };
    ids.example.dispatchEvent(new Event('click'));
    assert.ok(sampleSignal && !sampleSignal.aborted);
    assert.equal(ids.example.disabled, true);
    ids.cancel.dispatchEvent(new Event('click'));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sampleSignal.aborted, true);
    assert.match(ids.status.textContent, /취소/);
    assert.equal(ids.result.hidden, true);
    globalThis.fetch = async () => ({ok:false});
    ids.example.dispatchEvent(new Event('click'));
    await new Promise(resolve => setImmediate(resolve));
    assert.match(ids.status.textContent, /예시 사진을 불러오지 못했습니다/);
    assert.equal(ids.example.disabled, false);
    let finish;
    ids.photo.files=[{size:6,arrayBuffer:()=>new Promise(resolve=>{finish=resolve;})}];
    ids.reader.dispatchEvent(new Event('submit',{cancelable:true}));
    assert.equal(ids.submit.disabled,true);
    ids.photo.files=[{size:16*1024*1024}];
    ids.photo.dispatchEvent(new Event('change'));
    ids.reader.dispatchEvent(new Event('submit',{cancelable:true}));
    await new Promise(resolve=>setImmediate(resolve));
    assert.match(ids.status.textContent,/15 MiB/);
    finish(new Uint8Array([1,2]).buffer);
    await new Promise(resolve=>setImmediate(resolve));
    assert.match(ids.status.textContent,/15 MiB/);
    assert.equal(ids.submit.disabled,false);
    assert.equal(ids.barcode.textContent,'');
  } finally {
    for (const [key,value] of Object.entries(previous)) {
      if (value===undefined) delete globalThis[key]; else globalThis[key]=value;
    }
  }
});
test('validated image preview uses a disposable local URL and clears on cancel', async ()=>{
  class Element extends EventTarget {
    textContent=''; hidden=true;
    querySelector() {return elements.submit;}
    removeAttribute(key) {delete this[key];}
    setAttribute() {}
  }
  const elements=Object.fromEntries(['reader','photo','cancel','status','barcode','text','result','example','credit','confirm','confirm-credit','submit','preview'].map(id=>[id,new Element()]));
  const names=['document','window','Worker','Image','HTMLImageElement','HTMLCanvasElement'];
  const originals=Object.fromEntries(names.map(key=>[key,globalThis[key]]));
  const bytes=Uint8Array.from([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,0,0,0,16,0,0,0,12]);
  try {
    globalThis.Worker=class { postMessage() {} terminate() {} };
    globalThis.Image=class {naturalWidth=16; naturalHeight=12; async decode() {}};
    globalThis.HTMLImageElement=globalThis.Image;
    globalThis.HTMLCanvasElement=class {
      getContext() {return {fillRect(){},drawImage(){}};}
      toBlob(done) {done(new Blob([bytes],{type:'image/png'}));}
    };
    globalThis.document={getElementById:key=>elements[key.replace('package-','')],createElement:()=>new HTMLCanvasElement()};
    globalThis.window=Object.assign(new EventTarget(),{Worker,AbortController,URL});
    await import('../web/package-reader.js?preview-fixture');
    elements.photo.files=[new Blob([bytes],{type:'image/png'})];
    elements.reader.dispatchEvent(new Event('submit',{cancelable:true}));
    await new Promise(resolve=>setImmediate(resolve));
    const local=elements.preview.src;
    assert.equal(elements.preview.hidden,false);
    assert.match(local,/^blob:/);
    assert.equal((await fetch(local)).ok,true);
    elements.cancel.dispatchEvent(new Event('click'));
    assert.equal(elements.preview.hidden,true);
    assert.equal(elements.preview.src,undefined);
    await assert.rejects(fetch(local));
  } finally {
    elements.cancel.dispatchEvent(new Event('click'));
    for (const [key,value] of Object.entries(originals)) {
      if (value===undefined) delete globalThis[key]; else globalThis[key]=value;
    }
  }
});

test('visual identification preserves the separation from barcode-confirmed orders and blocks contradictions', () => {
  const apple = registered['7310865074225'];
  const panel = {product: apple, view: 'front', inliers: 23};
  const empty = {kind: 'empty', codes: []};
  const barcode = {kind: 'registered', product: apple, codes: ['7310865074225']};
  assert.equal(reader.photoDecision(empty, panel, '100% Apple juice · per 100 ml').kind, 'photo');
  assert.equal(reader.photoDecision(empty, panel, 'NAHRWERTANGABEN PER/PRO 180 ML: Energie 183 kJ').kind, 'photo');
  assert.equal(reader.photoDecision(barcode, null, '').kind, 'barcode');
  assert.equal(reader.photoDecision(empty, panel, null).kind, 'hold');
  assert.equal(reader.photoDecision(barcode, {...panel, product: 'God-Morgon-Orange-Juice'}, '').reason, 'mismatch');
  for (const kind of ['multiple', 'unregistered', 'unchecked']) {
    assert.equal(reader.photoDecision({kind}, panel, 'apple').kind, 'hold');
  }
  for (const status of ['ambiguous', 'incompatible']) {
    assert.equal(reader.photoDecision(barcode, {status}, 'apple').kind, 'hold');
  }
  for (const print of ['250ml', '1,75 liter', '6 × 1 L', '500 ml x 2']) {
    assert.equal(reader.photoDecision(empty, panel, print).reason, 'size');
    assert.equal(reader.photoDecision(barcode, panel, print).reason, 'size');
  }
  assert.equal(reader.photoDecision(empty, panel, 'apelsinjuice').reason, 'flavour');
  assert.equal(reader.photoDecision(empty, null, 'God Morgon Apple 1L').kind, 'hold');
  assert.equal(reader.conflictingPrint('God-Morgon-Orange-Juice-250ml', '250 mL • per 100 ml'), null);
});

test('a recovered front needs fruit-region matches and a foreground panel', async () => {
  const {createContext, runInContext} = await import('node:vm');
  const worker = createContext({self: {}, importScripts() {}});
  const source = await readFile(new URL('../web/vendor/package-reader/panel-worker.js', import.meta.url), 'utf8');
  runInContext(source, worker);
  const primary = {gtin: '7310865074225', view: 'front', hasIdentityText: true, inliers: 36, votes: [19, 8],
    cover: .3, score: 5, appearance: .95, areaFraction: .25, centerDistance: .03};
  const decide = (...candidates) => worker.panelDecision(candidates, registered, true);
  assert.equal(decide(primary).product, registered[primary.gtin]);
  assert.equal(decide({...primary, hasIdentityText: false}), null);
  const blackFlap = {id: 'ARLA-55f09abff8b47d20', width: 100, height: 100};
  assert.equal(worker.frontIdentityEvidence(blackFlap, [[10,38],[20,38],[30,38],[40,38]]), true);
  assert.equal(worker.frontIdentityEvidence(blackFlap, [[10,38],[11,38],[12,38],[13,38]]), false);
  assert.equal(worker.frontIdentityEvidence(blackFlap, [[10,58],[20,58],[30,58],[40,58]]), false);
  assert.equal(decide({...primary, votes: [26, 0]}).product, undefined);
  assert.equal(decide({...primary, centerDistance: -.3, areaFraction: .055}).product, undefined);
  const sibling = {...primary, gtin: 'another-volume', score: 4.8};
  assert.equal(decide(primary, sibling).status, 'ambiguous');
});

test('same-face visual uncertainty holds an orange name while preserving an independent optical identity', async () => {
  const {createContext, runInContext} = await import('node:vm');
  const worker = createContext({self: {}, importScripts() {}});
  runInContext(await readFile(new URL('../web/vendor/package-reader/panel-worker.js', import.meta.url), 'utf8'), worker);
  const gtin = '7310860007372', product = 'God-Morgon-Orange-Juice';
  const registry = {...registered, [gtin]: product};
  const footprint = [[.3,.2],[.5,.2],[.5,.8],[.3,.8]];
  const visual = {gtin, view:'front', inliers:100, votes:[100,4], score:10, appearance:.98, footprint,
    centerDistance:.1, areaFraction:.25};
  const rival = {...visual, gtin:'6415130050490', score:5, appearance:.975, inliers:51, votes:[50,1]};
  const resolve = other => worker.panelDecision([visual, other], registry);
  const pending = resolve(rival);
  const currentReader = reader;
  assert.equal(pending.status, 'market_unverified');
  assert.equal(resolve({...rival, appearance:.95}).product, product);
  const anotherFace = footprint.map(([x,y]) => [x+.4, y]);
  assert.equal(resolve({...rival, footprint:anotherFace}).product, product);
  assert.equal(currentReader.photoDecision({kind:'empty',codes:[]}, pending, 'orange').kind, 'hold');
  const barcode = {kind:'registered',codes:[gtin],product};
  assert.equal(currentReader.photoDecision(barcode, pending, 'orange').kind, 'barcode');
  assert.equal(currentReader.photoDecision(barcode, {product:'God-Morgon-Apple-Juice'}, '').reason, 'mismatch');
  const unrelated = {kind:'registered', codes:['7310865074225'], product:'God-Morgon-Apple-Juice'};
  assert.equal(currentReader.photoDecision(unrelated, pending, '').reason, 'mismatch');
});

test('compact capacity OCR is evaluated only with the concentrate footer and visual front', async () => {
  const currentReader = reader;
  const product = 'God-Morgon-Orange-Juice';
  const panel = {product, view:'front', inliers:80};
  const empty = {kind:'empty', codes:[]};
  const printed = '1751\n\nJUICE FROM CONCENTRATE WITH JUICY BTS';
  assert.equal(currentReader.photoDecision(empty, panel, printed).reason, 'size');
  assert.equal(currentReader.photoDecision(empty, panel, '1251\nJuice partly from concentrate').kind, 'photo');
  assert.equal(currentReader.photoDecision(empty, panel, '1001\nJuice from concentrate').kind, 'photo');
  assert.equal(currentReader.photoDecision(empty, panel, '1751\nOrange juice\nJuice from concentrate').kind, 'photo');
  assert.equal(currentReader.photoDecision(empty, {...panel, view:'ingredients'}, printed).kind, 'photo');
  const barcode = {kind:'registered', product, codes:['7310860007372']};
  assert.equal(currentReader.photoDecision(barcode, panel, printed).kind, 'barcode');
});

test('a slanted EAN read identifies the photo while standard order checks and printed size still apply', () => {
  const gtin = '7310865074225';
  const panel = {view: 'oblique-ean', product: registered[gtin], gtin, scanLines: 2};
  const empty = {kind: 'empty', codes: []};
  assert.deepEqual(reader.photoDecision(empty, panel, ''), {...panel, kind: 'photo'});
  assert.equal(reader.photoDecision(empty, panel, '1.75 L').reason, 'size');
  assert.equal(reader.photoDecision({kind: 'unregistered'}, panel, '').kind, 'hold');
  const differentOptical = {kind: 'registered', product: 'God-Morgon-Orange-Juice'};
  assert.equal(reader.photoDecision(differentOptical, panel, '').reason, 'mismatch');
});

test('a two-band side barcode identifies only the photograph and respects conflicting evidence', () => {
  const gtin = '7310865074225';
  const panel = {view: 'side-ean-bands', product: registered[gtin], gtin, scanBands: 2};
  const empty = {kind: 'empty', codes: []};
  assert.deepEqual(reader.photoDecision(empty, panel, ''), {...panel, kind: 'photo'});
  assert.equal(reader.photoDecision(empty, panel, '1.75 L').reason, 'size');
  assert.equal(reader.photoDecision(empty, panel, null).reason, 'ocr_failed');
  assert.equal(reader.photoDecision({kind: 'multiple'}, panel, '').kind, 'hold');
  assert.equal(reader.photoDecision({kind: 'registered', product: 'another pack'}, panel, '').reason, 'mismatch');
});

test('store retry examples use the same PNG bytes as the measured uploads', async () => {
  const {createHash} = await import('node:crypto');
  const html = await readFile(new URL('../web/recognition.html', import.meta.url), 'utf8');
  const records = (await readFile(new URL('../docs/experiments/oblique-packages/landskrona/browser.jsonl', import.meta.url), 'utf8'))
    .trim().split('\n').map(line => JSON.parse(line));
  for (const [id, key] of [['L01', 'apple'], ['L02', 'mixed']]) {
    const path = html.match(new RegExp('id="package-store-' + key + '"[^>]*data-src="([^"]+)"'))[1];
    const data = await readFile(new URL('../web/' + path, import.meta.url));
    assert.equal(createHash('sha256').update(data).digest('hex'), records.find(row => row.id === id).sha256);
  }
});

test('outside titles require a heading and two aligned, legible flavor words', async () => {
  const {outsideTitle} = await import('../web/outside-title.js');
  const selected = ['SELECTED', 28, 17, 167, 48];
  const citrus = ['CITRUS', 208, 18, 123, 50];
  const blood = ['BLOOD', 109, 75, 139, 47];
  const orange = ['ORANGE', 94, 128, 168, 48];
  function read(rows) {
    const tsv = rows.map(([word, x, y, w, h, confidence = 92]) =>
      [5, 1, 1, 1, 1, 1, x, y, w, h, confidence, word].join('\t')).join('\n');
    return outsideTitle(tsv, 347);
  }
  assert.equal(read([selected, citrus, blood, orange]), '블러드오렌지');
  assert.equal(read([selected, ['BLEND', 208, 18, 123, 50], ['ORANGE', ...blood.slice(1)],
    ['MANGO', ...orange.slice(1)]]), '오렌지·망고');
  assert.equal(read([selected, citrus, blood]), null);
  assert.equal(read([citrus, blood, orange]), null);
  assert.equal(read([['ELECTED', ...selected.slice(1)], ['CITAYG', ...citrus.slice(1)], blood, orange]), null);
  assert.equal(read([selected, ['CITAYG', ...citrus.slice(1)], blood, orange]), '블러드오렌지');
  assert.equal(read([selected, citrus, blood, ['ORANGE', 230, 128, 110, 48]]), null);
  assert.equal(read([selected, citrus, blood, [...orange, 40]]), null);
  assert.equal(read([selected, citrus, blood, orange, orange]), null);
});

test('isolated foreground juice titles require all aligned flavor words', async () => {
  const {drinkFamily} = await import('../web/front-label.js');
  const word = (text, x, y, w = 38) => ({text, x, y, w, h: 12, cx: x + w/2, cy: y + 6, conf: 91});
  const elder = [word('APPLE', 21, 21), word('ELDERFLOWER', 22, 39, 84)];
  assert.equal(drinkFamily(elder, 58), '사과·엘더플라워');
  assert.equal(drinkFamily(elder.slice(1), 58), null);
  assert.equal(drinkFamily([elder[0], word('ELDERFLOWER', 85, 39, 84)], 58), null);
  const blend = [word('CRUSH', 20, 0), word('APPLE', 10, 39), word('PEAR', 57, 39),
    word('KIWI', 12, 57), word('LIME', 59, 57)];
  assert.equal(drinkFamily(blend, 58), '사과·배·키위·라임');
  assert.equal(drinkFamily(blend.slice(1), 58), null);
  assert.equal(drinkFamily(blend.slice(0, -1), 58), null);
  assert.equal(drinkFamily([...blend.slice(0, -1), word('LIME', 160, 57)], 58), null);
});
