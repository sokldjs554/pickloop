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
    ids.example.dataset = {src:'media/new-photos/apple-back-original.jpg'};
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
