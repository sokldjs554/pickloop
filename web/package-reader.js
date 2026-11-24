// This ES module also runs in a disposable module worker for the barcode pass.
const vendor = new URL('./vendor/package-reader/', import.meta.url);
const asset = name => new URL(name, vendor).href;
const tooLarge = '이미지가 너무 큽니다. 긴 변이 16,384픽셀 이하이고 4천만 화소 이하인 사진을 선택해 주세요.';
const unreadable = '손상되었거나 지원하지 않는 이미지입니다. JPEG, PNG, WebP 사진을 선택해 주세요.';
const maxFileSize = 15 * 1024 * 1024;

function checkedSize(width, height) {
  if (!width || !height) throw new Error(unreadable);
  if (width * height > 40_000_000 || Math.max(width, height) > 16384) throw new Error(tooLarge);
  return {width, height};
}

// Read only metadata first, so a small file claiming giant dimensions never reaches a canvas.
export function imageDimensions(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const size = bytes.length;
  const tag = offset => String.fromCharCode(...bytes.subarray(offset, offset + 4));
  if (size >= 24 && view.getUint32(0) === 0x89504e47 && view.getUint32(4) === 0x0d0a1a0a &&
      view.getUint32(8) === 13 && tag(12) === 'IHDR') {
    return checkedSize(view.getUint32(16), view.getUint32(20));
  }
  if (size >= 30 && tag(0) === 'RIFF' && tag(8) === 'WEBP') {
    const chunk = tag(12);
    if (chunk === 'VP8X') {
      const uint24 = at => bytes[at] + bytes[at + 1] * 256 + bytes[at + 2] * 65536;
      return checkedSize(uint24(24) + 1, uint24(27) + 1);
    }
    if (chunk === 'VP8L' && bytes[20] === 0x2f) {
      const bits = view.getUint32(21, true);
      return checkedSize((bits & 0x3fff) + 1, ((bits >>> 14) & 0x3fff) + 1);
    }
    if (chunk === 'VP8 ' && bytes[23] === 0x9d && bytes[24] === 1 && bytes[25] === 0x2a) {
      return checkedSize(view.getUint16(26, true) & 0x3fff, view.getUint16(28, true) & 0x3fff);
    }
  }
  if (size >= 4 && bytes[0] === 0xff && bytes[1] === 0xd8) {
    let offset = 2;
    while (offset + 4 <= size && bytes[offset++] === 0xff) {
      while (offset < size && bytes[offset] === 0xff) offset++;
      const marker = bytes[offset++];
      if (marker === 0xd9 || marker === 0xda || offset + 2 > size) break;
      if (marker === 1 || (marker >= 0xd0 && marker <= 0xd7)) continue;
      const length = view.getUint16(offset);
      if (length < 2 || offset + length > size) break;
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker) && length >= 8) {
        return checkedSize(view.getUint16(offset + 5), view.getUint16(offset + 3));
      }
      offset += length;
    }
  }
  throw new Error(unreadable);
}

export function describeBarcodes(symbols, registry) {
  const valid = new Set();
  for (const {format, text, isValid} of symbols) {
    if (!isValid || !['EAN-13', 'UPC-A'].includes(format)) continue;
    const value = format === 'UPC-A' && /^\d{12}$/.test(text) ? '0' + text : text;
    if (!/^\d{13}$/.test(value) || (format === 'UPC-A' && value[0] !== '0')) continue;
    const sum = [...value].reduce((total, digit, i) => total + Number(digit) * (i % 2 ? 3 : 1), 0);
    if (sum % 10 === 0) valid.add(value);
  }
  const codes = [...valid].sort();
  if (codes.length === 0) return {kind: 'empty', codes};
  if (codes.length > 1) return {kind: 'multiple', codes};
  if (!registry) return {kind: 'unchecked', codes};
  const product = registry[codes[0]];
  return product ? {kind: 'registered', codes, product} : {kind: 'unregistered', codes};
}

const productLabels = {
  'God-Morgon-Orange-Juice-250ml': 'God Morgon 오렌지 주스 250mL',
  'God-Morgon-Apple-Juice': 'God Morgon 사과 주스 1 L',
  'God-Morgon-Orange-Juice': 'God Morgon 오렌지 주스 1 L',
  'God-Morgon-Orange-Red-Grapefruit-Juice': 'God Morgon 오렌지·레드자몽 주스 1 L',
};

function barcodeMessage(result) {
  const digits = result.codes.join(' · ');
  switch (result.kind) {
    case 'registered': return '상품 확정 · ' + (productLabels[result.product] || result.product) + ' · 등록 바코드 ' + digits;
    case 'unregistered': return '상품 확정 보류 · 미등록 바코드 ' + digits;
    case 'multiple': return '상품 확정 보류 · 서로 다른 바코드가 여러 개 보입니다. ' + digits;
    case 'unchecked': return '상품 확정 보류 · 등록 목록을 불러오지 못했습니다. 읽은 바코드 ' + digits;
    default: return '상품 확정 보류 · 바코드를 읽지 못했습니다';
  }
}

export async function decodeSymbols(png, wasmBinary) {
  const zxing = await import('./vendor/package-reader/zxing/reader/index.js');
  const overrides = wasmBinary ? {wasmBinary} : {locateFile: () => asset('zxing_reader.wasm')};
  zxing.prepareZXingModule({overrides});
  return zxing.readBarcodes(png, {formats: ['EAN-13', 'UPC-A'], tryRotate: true, tryHarder: true, maxNumberOfSymbols: 255});
}

if (typeof WorkerGlobalScope !== 'undefined' && self instanceof WorkerGlobalScope) {
  self.onmessage = async ({data}) => {
    try {
      const symbols = await decodeSymbols(data.payload.image);
      self.postMessage({status: 'resolve', data: symbols.map(({format, text, isValid}) => ({format, text, isValid}))});
    } catch {
      self.postMessage({status: 'reject'});
    }
  };
}

// Both engines run in terminable workers, including while downloading language data.
function request(worker, action, payload, signal) {
  return new Promise((resolve, reject) => {
    const done = (callback, value) => {
      worker.onmessage = worker.onerror = worker.onmessageerror = null;
      signal.removeEventListener('abort', cancel);
      callback(value);
    };
    const cancel = () => done(reject, new DOMException('취소', 'AbortError'));
    if (signal.aborted) return cancel();
    signal.addEventListener('abort', cancel, {once: true});
    worker.onmessage = ({data}) => {
      if (data.status === 'resolve') done(resolve, data.data);
      else if (data.status === 'reject') done(reject, new Error('판독기에 문제가 생겼습니다.'));
    };
    worker.onerror = worker.onmessageerror = () => done(reject, new Error('판독기를 불러오지 못했습니다.'));
    try {
      worker.postMessage({workerId: 'package', jobId: action, action, payload});
    } catch (error) {
      done(reject, error);
    }
  });
}

export async function opticalText(png, signal) {
  const worker = new Worker(asset('ocr-worker.js'));
  try {
    await request(worker, 'load', {options: {lstmOnly: true, corePath: asset('tesseract-core-lstm.wasm.js')}}, signal);
    const langs = ['kor', 'eng'];
    await request(worker, 'loadLanguage', {langs, options: {langPath: vendor.href, gzip: true, lstmOnly: true, cacheMethod: 'none'}}, signal);
    await request(worker, 'initialize', {langs, oem: 1, config: {}}, signal);
    await request(worker, 'setParameters', {params: {tessedit_pageseg_mode: '11'}}, signal);
    const result = await request(worker, 'recognize', {image: png, options: {}, output: {text: true}}, signal);
    return String(result.text || '').trim();
  } finally {
    worker.terminate();
  }
}

async function opticalBarcode(png, signal) {
  const worker = new Worker(import.meta.url, {type: 'module'});
  try {
    const symbols = await request(worker, 'read', {image: png}, signal);
    let registry;
    if (symbols.length) {
      try {
        const response = await fetch(asset('registry.json'), {signal, credentials: 'omit'});
        if (response.ok) registry = await response.json();
      } catch {
        // The human-readable code remains useful during a registry failure.
      }
    }
    return barcodeMessage(describeBarcodes(symbols, registry));
  } finally {
    worker.terminate();
  }
}

async function preparePhoto(file, signal) {
  if (!file || !file.size || file.size > maxFileSize) throw new Error('15 MiB 이하의 사진 한 장을 선택해 주세요.');
  imageDimensions(new Uint8Array(await file.arrayBuffer()));
  if (signal.aborted) throw new DOMException('취소', 'AbortError');
  const image = new Image();
  const source = URL.createObjectURL(file);
  try {
    image.src = source;
    try { await image.decode(); } catch { throw new Error(unreadable); }
    if (signal.aborted) throw new DOMException('취소', 'AbortError');
    const {width, height} = checkedSize(image.naturalWidth, image.naturalHeight);
    const factor = Math.min(1, 2560 / Math.max(width, height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(width * factor));
    canvas.height = Math.max(1, Math.round(height * factor));
    const context = canvas.getContext('2d', {alpha: false});
    if (!context) throw new Error('브라우저에서 사진을 열 수 없습니다.');
    context.fillStyle = '#fff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const png = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    canvas.width = canvas.height = 1;
    if (!png) throw new Error(unreadable);
    return png;
  } finally {
    URL.revokeObjectURL(source);
  }
}

function bindReader() {
  const form = document.getElementById('package-reader');
  if (!form) return;
  const byId = id => document.getElementById('package-' + id);
  const input = byId('photo'), cancel = byId('cancel'), status = byId('status');
  const barcode = byId('barcode'), text = byId('text'), submit = form.querySelector('[type=submit]');
  const preview = byId('preview'), resultPanel = byId('result');
  const example = byId('example'), credit = byId('credit');
  const confirmExample = byId('confirm'), confirmCredit = byId('confirm-credit');
  let active, previewURL;
  function stop(message) {
    active?.abort();
    active = null;
    if (previewURL) {
      preview.hidden = true;
      preview.removeAttribute('src');
      URL.revokeObjectURL(previewURL);
      previewURL = null;
    }
    submit.disabled = confirmExample.disabled = example.disabled = false;
    resultPanel.hidden = confirmCredit.hidden = credit.hidden = true;
    cancel.hidden = true;
    form.removeAttribute('aria-busy');
    status.textContent = message;
    barcode.textContent = text.textContent = '';
  }
  input.addEventListener('change', () => stop(input.files?.length ? '사진을 선택했습니다. 사진 읽기를 눌러 주세요.' : ''));
  cancel.addEventListener('click', () => stop('사진 읽기를 취소했습니다.'));
  window.addEventListener('pagehide', () => stop(''));
  form.addEventListener('submit', event => {
    event.preventDefault();
    run();
  });
  example.addEventListener('click', () => run(example));
  confirmExample.addEventListener('click', () => run(confirmExample));

  async function run(sample) {
    stop('');
    if (!window.Worker || typeof WebAssembly !== 'object' || !window.AbortController || !window.URL?.createObjectURL ||
        !HTMLImageElement.prototype.decode || !Blob.prototype.arrayBuffer || !HTMLCanvasElement.prototype.toBlob) {
      status.textContent = '이 브라우저에서 사진 판독을 지원하지 않습니다. 최신 브라우저에서 열어 주세요.';
      return;
    }
    const job = new AbortController();
    active = job;
    const signal = job.signal;
    submit.disabled = confirmExample.disabled = example.disabled = true;
    cancel.hidden = false;
    form.setAttribute('aria-busy', 'true');
    status.textContent = sample ? '예시 사진을 여는 중입니다.' : '사진을 여는 중입니다.';
    const pendingDecision = '상품 판정 중…';
    const timer = setTimeout(() => {
      if (active === job) {
        // Keep any engine's completed result if the other times out.
        job.abort();
        if (!resultPanel.hidden) {
          if (barcode.textContent === pendingDecision) barcode.textContent = '상품 확정 보류 · 바코드 판독 시간이 초과되었습니다';
          if (!text.textContent) text.textContent = '글자 판독 시간이 초과되었습니다.';
        }
        status.textContent = '처리 시간이 초과되었습니다. 사진을 더 가까이 찍어 다시 시도해 주세요.';
      }
    }, 120_000);
    try {
      let file = input.files?.[0];
      if (sample) {
        try {
          const response = await fetch(sample.dataset.src, {signal});
          if (!response.ok) throw new Error();
          file = await response.blob();
        } catch {
          throw new Error('예시 사진을 불러오지 못했습니다. 다시 시도해 주세요.');
        }
      }
      const image = await preparePhoto(file, signal);
      const png = new Uint8Array(await image.arrayBuffer());
      if (signal.aborted) return;
      resultPanel.hidden = false;
      credit.hidden = sample !== example;
      confirmCredit.hidden = sample !== confirmExample;
      barcode.textContent = pendingDecision;
      if (preview) {
        previewURL = URL.createObjectURL(image);
        preview.src = previewURL;
        preview.hidden = false;
      }
      status.textContent = '기기에서 글자와 바코드를 읽는 중입니다. 처음에는 판독기 다운로드가 필요합니다.';
      const show = async (operation, node, empty, error) => {
        try {
          const value = await operation;
          if (!signal.aborted) node.textContent = value || empty;
          return true;
        } catch {
          if (!signal.aborted) node.textContent = error;
          return false;
        }
      };
      const result = await Promise.all([
        show(opticalBarcode(png, signal), barcode, '', '상품 확정 보류 · 바코드 판독기를 실행하지 못했습니다'),
        show(opticalText(png, signal), text, '읽을 수 있는 글자가 없습니다.', '글자 판독기를 실행하지 못했습니다. 다시 시도해 주세요.'),
      ]);
      if (!signal.aborted) {
        const finished = sample ? '예시 사진 읽기를 마쳤습니다.' : '사진 읽기를 마쳤습니다.';
        status.textContent = result.every(Boolean) ? finished : '실행한 판독기의 결과를 확인해 주세요.';
      }
    } catch (error) {
      if (!signal.aborted) status.textContent = error.message || unreadable;
    } finally {
      clearTimeout(timer);
      if (active === job) {
        active = null;
        submit.disabled = confirmExample.disabled = example.disabled = false;
        cancel.hidden = true;
        form.removeAttribute('aria-busy');
      }
    }
  }
}

if (typeof document !== 'undefined') bindReader();
