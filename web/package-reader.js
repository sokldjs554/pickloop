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
  const valid = new Map();
  for (const {format, text, isValid} of symbols) {
    if (!isValid) continue;
    let code = text;
    if (format === 'EAN-8') {
      if (!/^\d{8}$/.test(code)) continue;
    } else if (format === 'UPC-A' || format === 'UPC-E') {
      // ZXing returns a UPC-E expanded to its GTIN, with an optional EAN leading zero.
      if (/^\d{12}$/.test(code)) code = '0' + code;
      if (!/^0\d{12}$/.test(code) || (format === 'UPC-E' && !/^0[01]/.test(code))) continue;
    } else if (format !== 'EAN-13' || !/^\d{13}$/.test(code)) {
      continue;
    }
    const key = code.padStart(14, '0');
    const sum = [...key].reduce((total, digit, i) => total + Number(digit) * (i % 2 ? 1 : 3), 0);
    if (sum % 10 === 0 && (!valid.has(key) || valid.get(key).length > code.length)) valid.set(key, code);
  }
  const codes = [...valid.values()].sort();
  if (codes.length === 0) return {kind: 'empty', codes};
  if (codes.length > 1) return {kind: 'multiple', codes};
  if (!registry) return {kind: 'unchecked', codes};
  const product = registry[codes[0]] || registry[codes[0].padStart(13, '0')];
  return product ? {kind: 'registered', codes, product} : {kind: 'unregistered', codes};
}

const productLabels = {
  'God-Morgon-Orange-Juice-250ml': 'God Morgon 오렌지 주스 250mL',
  'God-Morgon-Apple-Juice': 'God Morgon 사과 주스 1 L',
  'God-Morgon-Orange-Juice': 'God Morgon 오렌지 주스 1 L',
  'God-Morgon-Orange-Red-Grapefruit-Juice': 'God Morgon 오렌지·레드자몽 주스 1 L',
};

// An OCR reading can veto a visually similar carton, including a registered barcode
// photographed beside conflicting print. Serving-size and per-100 mL rows are common.
export function conflictingPrint(product, text) {
  const words = text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
  const expected = product.endsWith('250ml') ? 250 : 1000;
  const units = {ml: 1, cl: 10, dl: 100};
  for (const match of words.matchAll(/(?<![\w.,/])(\d{1,4}(?:[.,]\d{1,3})?)\s*[-–]?\s*(ml|cl|dl|litres?|liters?|l)\b/g)) {
    const before = words.slice(0, match.index);
    const after = words.slice(match.index + match[0].length);
    if (/(?:\b(?:per|pro|par|por|pr|serving size|portion|serving)\s*[:=]?|\/|\d\s*[.,])\s*$/.test(before)
        || /^\s*(?:\/|(?:of\s+)?water\b)/.test(after)) continue;
    if (Number(match[1].replace(',', '.')) * (units[match[2]] || 1000) !== expected) return 'size';
  }
  if (/\b(?:[2-9]|\d{2,})\s*[x×]\s*\d|\bpack of\s*(?:[2-9]|\d{2,})\b|(?:ml|cl|dl|litres?|liters?|l)\s*[x×]\s*(?:[2-9]|\d{2,})\b/.test(words)) return 'size';
  if (/\b(?:ne[ck]tar|mango|pineapple|ananas|blood orange|blodapelsin|pear|smoothie|bravo|tropicana|innocent|utan fruktkott)\b/.test(words)) return 'flavour';
  const apple = /\b(?:apple|appel|omena)(?:juice|mehu)?\b/.test(words);
  const orange = /\b(?:orange|apelsin|appelsiini)(?:juice|mehu)?\b/.test(words);
  const grapefruit = /\b(?:grapefruit|grapefrukt|verigreippi)(?:juice|mehu)?\b/.test(words);
  if (product.includes('-Apple-') ? orange || grapefruit : apple || (grapefruit && !product.includes('-Grapefruit-'))) return 'flavour';
  return null;
}

// On a front, the short line immediately before the concentrate statement is
// a net-capacity field. OCR can merge its decimal and read the L as a one.
function compactFrontCapacityConflict(product, transcript) {
  return product === 'God-Morgon-Orange-Juice' &&
    /^[ \t]*1[.,]?75[ \t]*[l1][ \t]*(?:\r?\n[ \t]*)+juice (?:partly )?from concentrate\b/im.test(transcript);
}

export function photoDecision(barcodes, panel, transcript) {
  if (barcodes?.kind === 'unregistered') return {kind: 'hold', reason: 'unregistered_code'};
  if (!barcodes || !['empty', 'registered'].includes(barcodes.kind)) return {kind: 'hold', reason: 'barcode'};
  if (panel?.status === 'incompatible' || panel?.status === 'ambiguous') {
    return {kind: 'hold', reason: panel.status};
  }
  const panelCandidate = panel?.product || panel?.marketCandidate;
  if (barcodes.kind === 'registered' && panelCandidate && panelCandidate !== barcodes.product) {
    return {kind: 'hold', reason: 'mismatch'};
  }
  const product = barcodes.product || panel?.product;
  if (!product) return {kind: 'hold', reason: 'no_panel'};
  const conflict = conflictingPrint(product, transcript || '');
  if (conflict) return {kind: 'hold', reason: conflict};
  if (barcodes.kind === 'registered') return {kind: 'barcode', product};
  if (panel.view === 'front' && compactFrontCapacityConflict(product, transcript || '')) {
    return {kind: 'hold', reason: 'size'};
  }
  if (transcript == null) return {kind: 'hold', reason: 'ocr_failed'};
  if (panel.view === 'side-ean-bands') {
    return {kind: 'photo', product, view: panel.view, gtin: panel.gtin, scanBands: panel.scanBands};
  }
  if (panel.view === 'oblique-ean') {
    return {kind: 'photo', product, view: panel.view, gtin: panel.gtin, scanLines: panel.scanLines};
  }
  return {kind: 'photo', product, view: panel.view, inliers: panel.inliers};
}

function identityMessage(result) {
  if (result.kind === 'barcode') return '';
  if (result.kind === 'photo') {
    if (result.view === 'side-ean-bands') {
      return '등록 상품 사진 판정 · ' + productLabels[result.product] + ' · 옆면 바코드 ' + result.gtin +
        ' · 떨어진 두 영역에서 같은 13자리를 판독했습니다.';
    }
    if (result.view === 'oblique-ean') {
      return '등록 상품 사진 판정 · ' + productLabels[result.product] + ' · 옆면 바코드 ' +
        result.gtin + ' · ' + result.scanLines + '개 선에서 같은 번호를 읽었습니다.';
    }
    if (result.view === 'orange-nutrition-values') {
      return '등록 상품 사진 판정 · ' + productLabels[result.product] +
        ' · 앞면 오렌지 표기와 옆면 영양표에서 가려지지 않은 네 줄의 끝을 대조했습니다.';
    }
    if (result.view === 'orange-rear-print') {
      return '등록 상품 사진 판정 · ' + productLabels[result.product] +
        ' · 접힌 윗면의 orange 글자, 뒷면 문단과 이어진 옆면 영양표를 확인했습니다.';
    }
    if (result.view === 'orange-nutrition-heading') {
      return '등록 상품 사진 판정 · ' + productLabels[result.product] +
        ' · 오렌지 표기와 옆면 영양표의 제목·수치 행 배치를 확인했습니다.';
    }
    if (result.view === 'orange-adjoining-panels') {
      return '등록 상품 사진 판정 · ' + productLabels[result.product] +
        ' · 같은 팩에서 앞면과 이어진 옆면 인쇄를 확인했습니다.';
    }
    if (result.view === 'split-fruit-collar') {
      return '등록 상품 사진 판정 · ' + productLabels[result.product] +
        ' · 같은 팩에서 브랜드와 뚜껑 아래의 두 과일 무늬를 확인했습니다.';
    }
    const view = {lettering: '브랜드·맛 표기', front: '앞면', nutrition: '영양 표시', ingredients: '성분 표시'}[result.view] || '포장 면';
    return '등록 상품 사진 판정 · ' + productLabels[result.product] + ' · 기준 사진과 ' + view + ' 특징 ' + result.inliers + '곳 일치';
  }
  return ({
    unregistered_code: '미등록 상품 · 읽은 바코드가 등록 목록에 없습니다.',
    size: '상품 판정 보류 · 읽힌 용량 또는 묶음 수량이 등록 규격과 다릅니다.',
    flavour: '상품 판정 보류 · 포장에 적힌 품목 또는 맛이 등록 상품과 다릅니다.',
    mismatch: '상품 판정 보류 · 읽힌 바코드와 포장 사진이 서로 다른 상품을 가리킵니다.',
    incompatible: '상품 사진 판정 보류 · 등록 목록 밖의 유사 포장과 일치합니다.',
    ambiguous: '상품 사진 판정 보류 · 등록 규격과 다른 규격의 포장을 구별하기 어렵습니다.',
    no_panel: '상품 사진 판정 보류 · 등록 포장을 구별할 특징이 부족합니다.',
    ocr_failed: '상품 사진 판정 보류 · 포장 표기의 충돌 여부를 확인할 수 없습니다.',
  })[result.reason] || '';
}

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
  return zxing.readBarcodes(png, {formats: ['EAN-13', 'UPC-A', 'EAN-8', 'UPC-E'], tryRotate: true, tryHarder: true, maxNumberOfSymbols: 255});
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
    return describeBarcodes(symbols, registry);
  } finally {
    worker.terminate();
  }
}

async function visualPanel(image, signal) {
  const worker = new Worker(asset('panel-worker.js'));
  try {
    return await request(worker, 'match', {image}, signal);
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
  const preview = byId('preview'), resultPanel = byId('result'), retake = byId('retake');
  const example = byId('example'), credit = byId('credit');
  const confirmExample = byId('confirm'), confirmCredit = byId('confirm-credit');
  const identity = byId('identity'), visualExample = byId('visual-example'), visualCredit = byId('visual-credit');
  const samples = [example, confirmExample, visualExample, byId('store-apple'), byId('store-mixed')].filter(Boolean);
  function setButtonsDisabled(disabled) {
    submit.disabled = disabled;
    for (const button of samples) button.disabled = disabled;
  }
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
    setButtonsDisabled(false);
    resultPanel.hidden = confirmCredit.hidden = credit.hidden = true;
    cancel.hidden = true;
    form.removeAttribute('aria-busy');
    status.textContent = message;
    if (retake) retake.hidden = true;
    barcode.textContent = text.textContent = '';
    if (identity) { identity.textContent = ''; delete identity.dataset.source; delete identity.dataset.product; }
    if (visualCredit) visualCredit.hidden = true;
  }
  input.addEventListener('change', () => stop(input.files?.length ? '사진을 선택했습니다. 사진 읽기를 눌러 주세요.' : ''));
  cancel.addEventListener('click', () => stop('사진 읽기를 취소했습니다.'));
  window.addEventListener('pagehide', () => stop(''));
  form.addEventListener('submit', event => {
    event.preventDefault();
    run();
  });
  for (const button of samples) button.addEventListener('click', () => run(button));

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
    setButtonsDisabled(true);
    cancel.hidden = false;
    form.setAttribute('aria-busy', 'true');
    status.textContent = sample ? '예시 사진을 여는 중입니다.' : '사진을 여는 중입니다.';
    const pendingDecision = '상품 판정 중…';
    const timer = setTimeout(() => {
      if (active === job) {
        // Keep any engine's completed result if the other times out.
        job.abort();
        if (!resultPanel.hidden) {
          if (identity && !identity.dataset.source) {
            identity.dataset.source = 'none'; identity.dataset.product = '';
            identity.textContent = '상품 사진 판정 보류 · 처리 시간이 초과되었습니다.';
          }
          if (barcode.textContent === pendingDecision || barcode.textContent.includes('확인하는 중입니다')) barcode.textContent = '상품 확정 보류 · 바코드 판독 시간이 초과되었습니다';
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
      if (visualCredit) visualCredit.hidden = sample !== visualExample;
      barcode.textContent = pendingDecision;
      if (preview) {
        previewURL = URL.createObjectURL(image);
        preview.src = previewURL;
        preview.hidden = false;
      }
      status.textContent = '기기에서 글자와 바코드를 읽는 중입니다. 처음에는 판독기 다운로드가 필요합니다.';
      const optical = opticalBarcode(png, signal).then(value => {
        if (!signal.aborted) barcode.textContent = value.kind === 'registered'
          ? '등록 바코드 ' + value.codes[0] + ' · 포장 표기를 확인하는 중입니다.' : barcodeMessage(value);
        return value;
      }).catch(() => {
        if (!signal.aborted) barcode.textContent = '상품 확정 보류 · 바코드 판독기를 실행하지 못했습니다';
        return null;
      });
      const reading = opticalText(png, signal).then(value => {
        if (!signal.aborted) text.textContent = value || '읽을 수 있는 글자가 없습니다.';
        return value;
      }).catch(() => {
        if (!signal.aborted) text.textContent = '글자 판독기를 실행하지 못했습니다. 다시 시도해 주세요.';
        return null;
      });
      const barcodes = await optical;
      if (signal.aborted) return;
      // Check the visual gallery only when optical codes do not block identification.
      // A small barcode carton is outside the three-product 1 L image gallery.
      const checkPanel = barcodes?.kind === 'empty' || (barcodes?.kind === 'registered' && !barcodes.product.endsWith('250ml'));
      const panelRead = checkPanel ? visualPanel(image, signal).catch(() => undefined) : null;
      const [panel, transcript] = await Promise.all([panelRead, reading]);
      if (signal.aborted) return;
      const decision = photoDecision(barcodes, panel, transcript);
      if (retake) retake.hidden = panel === undefined || !['no_panel', 'ambiguous'].includes(decision.reason);
      if (barcodes?.kind === 'registered') {
        barcode.textContent = decision.kind === 'barcode' ? barcodeMessage(barcodes)
          : '상품 확정 보류 · 읽은 등록 바코드 ' + barcodes.codes[0];
      }
      if (decision.kind === 'photo') barcode.textContent = ['oblique-ean', 'side-ean-bands'].includes(decision.view)
        ? '주문 규격 확정 보류 · 바코드를 정면에서 다시 확인해 주세요.'
        : '주문 규격 확정 보류 · 바코드를 읽지 못했습니다.';
      if (identity) {
        identity.dataset.source = {photo: 'visual', barcode: 'barcode', hold: 'none'}[decision.kind];
        identity.dataset.product = decision.product || '';
        identity.textContent = identityMessage(decision);
        if (panel === undefined && decision.reason === 'no_panel') {
          identity.textContent = '상품 사진 판정 보류 · 포장 비교기를 불러오지 못했습니다.';
        }
      }
      status.textContent = sample ? '예시 사진 읽기를 마쳤습니다.' : '사진 읽기를 마쳤습니다.';
    } catch (error) {
      if (!signal.aborted) status.textContent = error.message || unreadable;
    } finally {
      clearTimeout(timer);
      if (active === job) {
        active = null;
        setButtonsDisabled(false);
        cancel.hidden = true;
        form.removeAttribute('aria-busy');
      }
    }
  }
}

if (typeof document !== 'undefined') bindReader();
