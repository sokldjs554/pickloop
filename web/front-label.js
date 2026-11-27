// Read the product title relative to a centered, three-line God Morgon mark.
function words(tsv) {
  return tsv.split('\n').flatMap((line) => {
    const a = line.split('\t');
    if (a[0] !== '5' || !a[11]) return [];
    const [x, y, w, h, conf] = a.slice(6, 11).map(Number);
    return [
      {
        text: a[11].toUpperCase().replace(/^[^A-Z0-9]+|[^A-Z0-9]+$/g, ''),
        x,
        y,
        w,
        h,
        conf,
        cx: x + w / 2,
        cy: y + h / 2,
      },
    ];
  });
}

function one(list, token, floor = 65) {
  const matches = list.filter((w) => w.text === token && w.conf >= floor);
  return matches.length === 1 ? matches[0] : null;
}

function pairOnLine(a, b) {
  return (
    a &&
    b &&
    b.x >= a.x + 0.8 * a.w &&
    b.x - a.x - a.w < 2.8 * a.h &&
    Math.abs(a.cy - b.cy) < 0.65 * Math.max(a.h, b.h)
  );
}

function below(a, b) {
  return (
    a &&
    b &&
    b.y > a.y + 0.45 * a.h &&
    b.y < a.y + 3 * a.h &&
    Math.abs(b.cx - a.cx) < 0.62 * Math.max(a.w, b.w)
  );
}

function png(canvas) {
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
    .then((blob) => blob.arrayBuffer())
    .then((buffer) => new Uint8Array(buffer));
}

function canvasFor(w, h) {
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  return canvas;
}

function printedLogo(data, brand) {
  // The third logo line has a yellow orange in place of the O. Check the
  // dark backing in each of the three rows and the colored glyph in the last.
  const { x, y, w } = brand;
  for (const offset of [0, 0.34, 0.69]) {
    let dark = 0,
      yellow = 0,
      n = 0;
    for (let j = Math.round(y + offset * w); j < Math.round(y + (offset + 0.32) * w); j += 2) {
      for (let i = x; i < x + w; i += 2) {
        const k = 4 * (j * data.width + i);
        const r = data.data[k],
          g = data.data[k + 1],
          b = data.data[k + 2];
        if (Math.max(r, g, b) < 129) dark++;
        if (r > 90 && g > 65 && b < 0.65 * r && b < 0.82 * g) yellow++;
        n++;
      }
    }
    if (dark / n < 0.31 || (offset === 0.69 ? yellow / n < 0.07 : yellow / n > 0.08)) return false;
  }
  return true;
}

function connectedFace(data, brand, endY) {
  // A bright gap across the title column separates labels on adjoining packs.
  const half = 0.56 * brand.w;
  for (let y = Math.round(brand.y + brand.w); y < endY; y += 2) {
    let white = 0,
      n = 0;
    for (let x = Math.round(brand.cx - half); x < brand.cx + half; x += 2) {
      const i = 4 * (y * data.width + x);
      if (Math.min(data.data[i], data.data[i + 1], data.data[i + 2]) > 215) white++;
      n++;
    }
    if (white / n > 0.82) return false;
  }
  return true;
}

async function cropWords(ctx, box, read, curve = 0, mode = 'block', zoom = 2) {
  const [x, y, w, h] = box.map(Math.round);
  if (w <= 0 || h <= 0 || x < 0 || y < 0 || x + w > ctx.canvas.width || y + h > ctx.canvas.height)
    return [];
  const crop = canvasFor(w, h),
    dst = crop.getContext('2d');
  dst.fillStyle = 'white';
  dst.fillRect(0, 0, w, h);
  if (curve) {
    // Flatten the upward bend of a title wrapped around a cylindrical bottle.
    for (let col = 0; col < w; col++) {
      const dy = Math.round((curve * (col - 0.37 * w) ** 2) / w);
      dst.drawImage(ctx.canvas, x + col, y - dy, 1, h, col, 0, 1, h);
    }
  } else dst.drawImage(ctx.canvas, x, y, w, h, 0, 0, w, h);
  const enlarged = canvasFor(w * zoom, h * zoom),
    ec = enlarged.getContext('2d');
  ec.imageSmoothingQuality = 'high';
  ec.drawImage(crop, 0, 0, enlarged.width, enlarged.height);
  return words(await read(await png(enlarged), mode));
}

// Find bright character boxes on a dark footer. Read the number and its smaller
// adjacent unit separately to accommodate different font sizes on the same line.
function footerGlyphs(image, left, top, width, height) {
  const mask = new Uint8Array(width * height);
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      const i = 4 * ((top + y) * image.width + left + x),
        p = image.data;
      mask[y * width + x] = 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2] > 145;
    }
  const boxes = [];
  for (let seed = 0; seed < mask.length; seed++) {
    if (!mask[seed]) continue;
    const todo = [seed];
    mask[seed] = 0;
    let x0 = width,
      x1 = 0,
      y0 = height,
      y1 = 0;
    while (todo.length) {
      const at = todo.pop(),
        x = at % width,
        y = Math.floor(at / width);
      x0 = Math.min(x0, x);
      x1 = Math.max(x1, x);
      y0 = Math.min(y0, y);
      y1 = Math.max(y1, y);
      for (let yy = Math.max(0, y - 1); yy <= Math.min(height - 1, y + 1); yy++) {
        for (let xx = Math.max(0, x - 1); xx <= Math.min(width - 1, x + 1); xx++) {
          const next = yy * width + xx;
          if (mask[next]) {
            mask[next] = 0;
            todo.push(next);
          }
        }
      }
    }
    boxes.push({ x: left + x0, y: top + y0, w: x1 - x0 + 1, h: y1 - y0 + 1 });
  }
  return boxes.sort((a, b) => a.x - b.x);
}

async function outsideCapacity(ctx, original, brand, read) {
  const u = brand.w,
    left = Math.max(0, Math.round(brand.cx - 2 * u)),
    right = Math.round(brand.cx - 0.5 * u);
  const top = Math.round(brand.y + 5.6 * u),
    bottom = Math.min(original.height, Math.round(brand.y + 7.2 * u));
  if (bottom <= top || right <= left) return false;
  const boxes = footerGlyphs(original, left, top, right - left, bottom - top);
  const digits = boxes.filter(
    (b) => b.h > 0.14 * u && b.h < 0.32 * u && b.w >= 0.12 * b.h && b.w < 1.05 * b.h,
  );
  for (let i = 2; i < digits.length; i++) {
    const [a, b, c] = digits.slice(i - 2, i + 1);
    if (
      Math.max(Math.abs(b.y - a.y), Math.abs(c.y - a.y)) > 0.25 * a.h ||
      Math.max(Math.abs(b.h - a.h), Math.abs(c.h - a.h)) > 0.28 * a.h ||
      b.x <= a.x + a.w ||
      b.x - a.x - a.w > a.h ||
      c.x <= b.x + b.w - 1 ||
      c.x - b.x - b.w > 0.65 * a.h
    )
      continue;
    const unit = boxes.filter(
      (v) =>
        v.x >= c.x + c.w &&
        v.x < c.x + c.w + 2.5 * a.h &&
        v.h >= 0.19 * a.h &&
        v.h <= 0.55 * a.h &&
        Math.abs(v.y + v.h - (c.y + c.h)) < 0.22 * a.h,
    );
    if (unit.length < 4 || unit.length > 6) continue;
    const span = (list, px, py) => {
      const x = Math.min(...list.map((v) => v.x)) - px,
        y = Math.min(...list.map((v) => v.y)) - py;
      return [
        x,
        y,
        Math.max(...list.map((v) => v.x + v.w)) - x + px,
        Math.max(...list.map((v) => v.y + v.h)) - y + py,
      ];
    };
    const numeric = await cropWords(ctx, span([a, b, c], 0.23 * a.h, 0.24 * a.h), read, 0, 'line', 5);
    if (!numeric.some((v) => /^(1,75|1\.75)$/.test(v.text) && v.conf >= 65)) continue;
    const [ux, uy, uw, uh] = span(unit, 0.2 * a.h, 0.22 * a.h).map(Math.round);
    const field = canvasFor(uw + 8, uh + 8),
      fc = field.getContext('2d');
    fc.fillStyle = 'white';
    fc.fillRect(0, 0, field.width, field.height);
    const patch = fc.createImageData(uw, uh);
    for (let j = 0; j < uh; j++)
      for (let k = 0; k < uw; k++) {
        const q = 4 * ((j + uy) * original.width + ux + k),
          v = 4 * (j * uw + k),
          p = original.data;
        // Remove characters above/below this unit's own baseline.
        const inUnit = unit.some(
          (b) => ux + k >= b.x && ux + k < b.x + b.w && uy + j >= b.y && uy + j < b.y + b.h,
        );
        const ink = inUnit && 0.299 * p[q] + 0.587 * p[q + 1] + 0.114 * p[q + 2] > 120;
        patch.data[v] = patch.data[v + 1] = patch.data[v + 2] = ink ? 0 : 255;
        patch.data[v + 3] = 255;
      }
    fc.putImageData(patch, 4, 4);
    const units = await cropWords(fc, [0, 0, field.width, field.height], read, 0, 'line', 6);
    if (units.some((v) => /^(LITER|LITRE)$/.test(v.text) && v.conf >= 55)) return true;
  }
  return false;
}

export function drinkFamily(label, u) {
  const apple = one(label, 'APPLE'),
    elder = one(
      label.filter((v) => below(apple, v)),
      'ELDERFLOWER',
    ),
    pear = one(label, 'PEAR'),
    kiwi = one(label, 'KIWI'),
    lime = one(label, 'LIME');
  if (below(apple, elder) && Math.abs(apple.x - elder.x) < 0.2 * u && elder.w > u)
    return '사과·엘더플라워';
  if (
    pairOnLine(apple, pear) &&
    pairOnLine(kiwi, lime) &&
    below(apple, kiwi) &&
    below(pear, lime) &&
    one(label, 'CRUSH', 25)
  )
    return '사과·배·키위·라임';
  const morning = one(label, 'MORNING');
  if (below(one(label, 'ORANGE'), morning) && morning.w > u) return '오렌지 모닝';

  return null;
}

export async function frontLabel(image, read, signal) {
  const im = await createImageBitmap(image);
  const h = Math.min(im.height, 1440),
    w = Math.round((im.width * h) / im.height);
  if (w < 80 || w / h > 0.85 || w / h < 0.22) {
    im.close();
    return null;
  }
  const canvas = canvasFor(w, h),
    ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.fillStyle = 'white';
  ctx.fillRect(0, 0, w, h);
  try {
    ctx.drawImage(im, 0, 0, w, h);
  } finally {
    im.close();
  }
  const original = ctx.getImageData(0, 0, w, h);
  const luminance = ctx.createImageData(w, h);
  for (let i = 0; i < original.data.length; i += 4) {
    luminance.data[i] = luminance.data[i + 1] = luminance.data[i + 2] = original.data[i];
    luminance.data[i + 3] = 255;
  }
  ctx.putImageData(luminance, 0, 0);
  const all = words(await read(await png(canvas), 'sparse'));
  const brand = one(all, 'GOD', 80);
  if (!brand || signal.aborted) return null;
  const u = brand.w;
  if (
    u / h < 0.06 ||
    u / h > 0.16 ||
    Math.abs(brand.cx / w - 0.5) > 0.15 ||
    brand.y < h * 0.15 ||
    brand.y > h * 0.7 ||
    !printedLogo(original, brand)
  )
    return null;
  const label = all.filter(
    (v) =>
      v.y >= brand.y + 1.03 * u &&
      v.y <= brand.y + 3.5 * u &&
      Math.abs(v.cx - brand.cx) < 1.32 * u &&
      v.h >= 0.1 * u,
  );
  if (!connectedFace(original, brand, Math.min(h, brand.y + 2.7 * u))) return null;

  const flavor = drinkFamily(label, u);
  if (flavor) return flavor;

  if ((one(label, 'CARROT') || label.some((v) => v.text.startsWith('MANDA'))) && w / h < 0.55) {
    const crop = await cropWords(
      ctx,
      [brand.cx - 0.78 * u, brand.y + 1.61 * u, 2.2 * u, 0.83 * u],
      read,
      0.4,
    );
    const a = one(crop, 'APPLE', 50),
      m = one(crop, 'MANDARIN', 50),
      c = one(crop, 'CARROT', 50);
    if (pairOnLine(a, m) && below(a, c)) return '사과·만다린·당근';
  }
  if (one(label, 'CITRUS') && one(label, 'GRAPEFRUIT') && !label.some((v) => v.text === 'ORANGE')) {
    const crop = await cropWords(
      ctx,
      [brand.cx - 1.12 * u, brand.y + 1.2 * u, 2.24 * u, 1.52 * u],
      read,
    );
    const red = one(crop, 'RED'),
      grapefruit = one(crop, 'GRAPEFRUIT');
    if (
      one(crop, 'CITRUS', 15) &&
      (one(crop, 'SELECTED', 35) || one(crop, 'ELECTED', 35)) &&
      below(red, grapefruit) &&
      !crop.some((v) => v.text === 'ORANGE')
    )
      return '레드자몽 단일 맛';
  }
  if (one(label, 'SMOOTH') && w / h < 0.55) {
    const title = await cropWords(ctx, [brand.cx - u, brand.y + 1.05 * u, 2 * u, 1.06 * u], read);
    if (
      !below(one(title, 'SMOOTH'), one(title, 'ORANGE')) ||
      !connectedFace(original, brand, Math.min(h, brand.y + 6.95 * u))
    )
      return null;
    if (await outsideCapacity(ctx, original, brand, read)) return '스무스 오렌지와 미등록 용량 1.75 L';
  }
  return null;
}
