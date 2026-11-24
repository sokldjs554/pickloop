// Offline smoke test for the pinned browser workers. Run with local PNG photo paths.
// The Node worker adapts browser messaging, file loading and importScripts. Recognition
// still uses the shipped WASM engines and exactly the page's text/barcode options.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {readFileSync} from 'node:fs';
import {Worker, isMainThread, parentPort, workerData} from 'node:worker_threads';
import vm from 'node:vm';
import {opticalText, decodeSymbols, describeBarcodes} from '../web/package-reader.js';

const vendor = new URL('../web/vendor/package-reader/', import.meta.url);
if (!isMainThread) {
  function localURL(url) {
    const target = new URL(url);
    assert.ok(target.href.startsWith(vendor.href), 'unexpected non-local worker request');
    return target;
  }
  const context = vm.createContext({
    setTimeout, clearTimeout, console, URL, Blob, atob, btoa, TextDecoder, TextEncoder, WebAssembly,
    performance, WorkerGlobalScope: class {}, location: {href:workerData}, navigator:{hardwareConcurrency:1},
    fetch: async url => new Response(await readFile(localURL(url))),
    importScripts: url => vm.runInContext(readFileSync(localURL(url),'utf8'), context),
    postMessage: value => parentPort.postMessage(value),
    addEventListener: (event, callback) => {
      if (event === 'message') parentPort.on('message', data => callback({data}));
    },
  });
  context.self = context;
  vm.runInContext(readFileSync(localURL(workerData), 'utf8'), context);
} else {
  // Node's standards-based transfer API has a different message-event shape.
  globalThis.Worker = class {
    constructor(source) {
      this.worker = new Worker(new URL(import.meta.url), {workerData: String(source)});
      this.worker.on('message', data => {
        if (data.status === 'reject') console.error('Worker error:', data.action, data.data);
        this.onmessage?.({data});
      });
      this.worker.on('error', error => this.onerror?.(error));
    }
    postMessage(data) { this.worker.postMessage(data); }
    terminate() { return this.worker.terminate(); }
  };
  const registry = JSON.parse(await readFile(new URL('registry.json', vendor)));
  const wasm = await readFile(new URL('zxing_reader.wasm', vendor));
  const paths = process.argv.slice(2);
  if (!paths.length) throw new Error('Pass at least one PNG input image');
  for (const path of paths) {
    const bytes = new Uint8Array(await readFile(path));
    const abort = new AbortController();
    const timer = setTimeout(()=>abort.abort(), 120_000);
    try {
      const symbols = await decodeSymbols(bytes, wasm);
      const barcode = describeBarcodes(symbols, registry);
      const text = await opticalText(bytes, abort.signal);
      console.log(JSON.stringify({path, barcode, text}));
    } finally { clearTimeout(timer); }
  }
}
