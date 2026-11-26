// A registered classic orange carton can show a flavour word on its folded roof,
// a wide rear face with multilingual copy, and a narrow adjoining nutrition face.
// The gallery and heading tests are shared with orange-nutrition.js.
function plainOrangeRoofWord(text) {
  return /^[\s\p{P}]*orange[\s\p{P}]*$/iu.test(String(text || ''));
}

// Older cartons carry several white paragraphs under the yellow rear headline.
// Check repeated cross-column ink lines in two disjoint depths and a continuous
// dark join to the nutrition face. All lengths scale with the observed word.
function orangeRearCopy(frame, word, heading) {
  const [a, b] = word;
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const ux = (b[0] - a[0]) / length,
    uy = (b[1] - a[1]) / length;
  const [start, end] = heading;
  const span = Math.hypot(end[0] - start[0], end[1] - start[1]);
  const { cols, rows, data } = frame;

  function separated() {
    for (const shift of [-0.17, -0.1, -0.05, 0, 0.05, 0.1, 0.17]) {
      for (const shear of [-0.48, -0.32, -0.16, 0, 0.16, 0.32, 0.48]) {
        let pale = 0;
        for (let i = 0; i < 31; i++) {
          const depth = 0.03 + (1.17 * i) / 30;
          const x = Math.round(start[0] + span * (shift * ux + depth * (-uy + shear * ux)));
          const y = Math.round(start[1] + span * (shift * uy + depth * (ux + shear * uy)));
          if (x < 0 || y < 0 || x >= cols || y >= rows) continue;
          const k = 4 * (y * cols + x),
            low = Math.min(data[k], data[k + 1], data[k + 2]),
            high = Math.max(data[k], data[k + 1], data[k + 2]);
          if (low > 145 && high - low < 40) pale++;
        }
        if (pale >= 24) return true;
      }
    }
    return false;
  }
  if (separated()) return false;
  function green(x, y) {
    if (x < 0 || x >= cols - 1 || y < 0 || y >= rows - 1) return NaN;
    const ix = Math.floor(x),
      iy = Math.floor(y),
      dx = x - ix,
      dy = y - iy;
    const k = 4 * (iy * cols + ix) + 1;
    return (
      (1 - dy) * ((1 - dx) * data[k] + dx * data[k + 4]) +
      dy * ((1 - dx) * data[k + 4 * cols] + dx * data[k + 4 * cols + 4])
    );
  }
  function textBand(left, right, dark, first, last) {
    if (dark < 0.25 * (last - first) * 30) return 0;
    let peaks = 0,
      previous = -10;
    const ridge = new Float32Array(last - first);
    for (let i = first + 2; i < last - 2; i++) {
      let lo = left[i] - 0.25 * (left[i - 2] + left[i - 1] + left[i + 1] + left[i + 2]);
      let ro = right[i] - 0.25 * (right[i - 2] + right[i - 1] + right[i + 1] + right[i + 2]);
      ridge[i - first] = Math.min(lo, ro);
    }
    for (let i = 2; i < ridge.length - 2; i++) {
      if (
        i > previous + 2 &&
        ridge[i] >= 3 &&
        ridge[i] > ridge[i - 1] &&
        ridge[i] >= ridge[i + 1] &&
        ridge[i] - 0.5 * (ridge[i - 2] + ridge[i + 2]) > 4
      ) {
        peaks++;
        previous = i;
      }
    }
    return peaks;
  }
  for (const width of [1.65, 2, 2.35, 2.7])
    for (const tilt of [-0.12, 0, 0.12])
      for (const shear of [-0.3, -0.12, 0.08, 0.25]) {
        const left = new Float32Array(145),
          right = new Float32Array(145),
          dark = [0, 0];
        for (let row = 0; row < 145; row++) {
          const depth = (0.18 + (1.8 * row) / 144) * length * width;
          for (let col = 0; col < 31; col++) {
            if (col === 15) continue;
            const along = -(0.22 + (0.56 * col) / 30) * length * width;
            const x = start[0] + along * (ux - tilt * uy) + depth * (-uy + shear * ux);
            const y = start[1] + along * (uy + tilt * ux) + depth * (ux + shear * uy);
            const value = green(x, y);
            if (col < 15) left[row] += value / 15;
            else right[row] += value / 15;
            if (value < 85 && row < 69) dark[0]++;
            if (value < 85 && row >= 76) dark[1]++;
          }
        }
        const first = textBand(left, right, dark[0], 0, 69),
          second = textBand(left, right, dark[1], 76, 145);
        if (first >= 6 && second >= 6) return { upper: first, lower: second };
      }
  return false;
}

const readOrangeRear = (() => {
  const percentile = (a, p) => {
    a.sort((x, y) => x - y);
    let j = p * (a.length - 1),
      i = Math.floor(j);
    return a[i] * (1 - j + i) + a[Math.min(a.length - 1, i + 1)] * (j - i);
  };
  const add = (a, b, t) => [a[0] + b[0] * t, a[1] + b[1] * t],
    sub = (a, b) => [a[0] - b[0], a[1] - b[1]],
    len = (v) => Math.hypot(...v);
  const centre = (q) => [(q[0][0] + q[2][0]) / 2, (q[0][1] + q[2][1]) / 2];
  function rect(c, u, v) {
    return [
      [-0.5, -0.5],
      [0.5, -0.5],
      [0.5, 0.5],
      [-0.5, 0.5]
    ].map(([a, b]) => add(add(c, u, a), v, b));
  }
  function crop(im, q, cols, rows, extraU, extraV) {
    const c = centre(q),
      u = sub(q[1], q[0]),
      v = sub(q[3], q[0]),
      s = new Float32Array(8),
      d = new Float32Array([0, 0, cols - 1, 0, cols - 1, rows - 1, 0, rows - 1]);
    s.set(
      rect(
        c,
        u.map((z) => z * extraU),
        v.map((z) => z * extraV)
      ).flat()
    );
    const sm = cv.matFromArray(4, 1, cv.CV_32FC2, s),
      dm = cv.matFromArray(4, 1, cv.CV_32FC2, d),
      w = cv.getPerspectiveTransform(sm, dm),
      out = new cv.Mat();
    cv.warpPerspective(im, out, w, new cv.Size(cols, rows), cols === 223 ? cv.INTER_CUBIC : cv.INTER_LINEAR);
    w.delete();
    sm.delete();
    dm.delete();
    return out;
  }
  function score(im, q) {
    const chip = crop(im, q, 84, 28, 1.22, 2.25),
      dat = chip.data,
      ink = [],
      edge = [],
      col = [];
    for (let y = 0; y < 28; y++)
      for (let x = 0; x < 84; x++) {
        const i = 4 * (84 * y + x);
        if (y < 4 || y >= 24) edge.push(dat[i + 1]);
        else if (y >= 7 && y < 22 && x >= 8 && x < 76) {
          ink.push(dat[i + 1]);
          col.push(Math.min(dat[i], dat[i + 1]) - dat[i + 2]);
        }
      }
    chip.delete();
    const bg = percentile([...edge], 0.5),
      hi = percentile([...ink], 0.82),
      mean = edge.reduce((x, y) => x + y, 0) / edge.length,
      std = Math.sqrt(edge.reduce((s, v) => s + (v - mean) ** 2, 0) / edge.length);
    let op = 0,
      n = 0;
    for (let i = 0; i < ink.length; i++)
      if (ink[i] >= hi) {
        op += col[i];
        n++;
      }
    op /= n;
    if (bg > 100 || op < 23 || hi - bg < 35) return 0;
    return (hi - bg) * Math.min(1, op / 70) * Math.max(0.1, 1 - std / 95);
  }
  // Group local yellow strokes into short text lines. Rank them by ink contrast against the surrounding dark paper.
  function proposals(im) {
    const W = im.cols,
      H = im.rows,
      p = im.data,
      y = new cv.Mat(H, W, cv.CV_32FC1),
      bl = new cv.Mat(),
      mask = new cv.Mat(H, W, cv.CV_8UC1),
      dst = new cv.Mat();
    const l = y.data32F,
      op = new Float32Array(W * H);
    for (let i = 0; i < l.length; i++) {
      const k = i * 4;
      l[i] = Math.min(255, Math.max(0, 0.6 * p[k] + 0.9 * p[k + 1] - 0.5 * p[k + 2]));
      op[i] = Math.min(p[k], p[k + 1]) - p[k + 2];
    }
    cv.GaussianBlur(y, bl, new cv.Size(0, 0), 3, 3, cv.BORDER_DEFAULT);
    const maskData = mask.data,
      blur = bl.data32F,
      slots = new Map(),
      seen = new Set();
    for (const delta of [5, 12, 24]) {
      for (let i = 0; i < l.length; i++) maskData[i] = l[i] - blur[i] > delta && op[i] > 15 && l[i] > 50 ? 255 : 0;
      for (const length of [2, 4, 7])
        for (const degrees of [0, -25, 25]) {
          const k = cv.Mat.zeros(length + 2, length + 2, cv.CV_8UC1),
            rad = (degrees * Math.PI) / 180,
            cen = (length + 1) / 2,
            dx = (length * Math.cos(rad)) / 2,
            dy = (length * Math.sin(rad)) / 2;
          const round = (a) =>
            a % 1 === 0.5 ? (Math.floor(a) % 2 === 0 ? Math.floor(a) : Math.ceil(a)) : Math.round(a);
          cv.line(
            k,
            new cv.Point(round(cen - dx), round(cen - dy)),
            new cv.Point(round(cen + dx), round(cen + dy)),
            new cv.Scalar(1),
            1
          );
          cv.morphologyEx(mask, dst, cv.MORPH_CLOSE, k);
          k.delete();
          const cs = new cv.MatVector(),
            hi = new cv.Mat();
          cv.findContours(dst, cs, hi, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
          for (let i = 0; i < cs.size(); i++) {
            const contour = cs.get(i),
              r = cv.minAreaRect(contour);
            contour.delete();
            let a = r.size.width,
              b = r.size.height,
              t = r.angle;
            if (b > a) {
              [a, b] = [b, a];
              t += 90;
            }
            if (t > 90) t -= 180;
            const cx = r.center.x,
              cy = r.center.y;
            if (
              a < 13 ||
              b < 3.5 ||
              a > W * 0.59 ||
              a / b < 2 ||
              a / b > 15 ||
              Math.max(Math.abs(cx / W - 0.5), Math.abs(cy / H - 0.5)) > 0.45
            )
              continue;
            t *= Math.PI / 180;
            const u = [a * Math.cos(t), a * Math.sin(t)],
              v = [-b * Math.sin(t), b * Math.cos(t)],
              q = rect([cx, cy], u, v);
            const k = q
              .flat()
              .map((v) => round(v / 2))
              .join(',');
            if (seen.has(k)) continue;
            seen.add(k);
            const s = score(im, q),
              id = Math.floor(cx / 9) + ',' + Math.floor(cy / 9);
            if (s > 14 && (!slots.has(id) || slots.get(id).s < s)) slots.set(id, { s, q });
          }
          hi.delete();
          cs.delete();
        }
    }
    y.delete();
    bl.delete();
    mask.delete();
    dst.delete();
    return [...slots.values()].sort((a, b) => b.s - a.s);
  }
  // Verify a contiguous yellow fold immediately above the putative nutrition heading.
  function golden(im, q) {
    const bytes = im.data,
      [a, b] = q,
      u = sub(b, a),
      l = len(u),
      n = [u[1] / l, -u[0] / l],
      count = [0, 0, 0];
    for (const [j, v] of [0.085, 0.16, 0.24].entries())
      for (let i = 0; i < 10; i++) {
        const pos = add(add(a, u, 0.14 + (0.72 * i) / 9), n, v * l).map(Math.round),
          [x, y] = pos;
        if (x < 0 || y < 0 || x >= im.cols || y >= im.rows) continue;
        const k = 4 * (im.cols * y + x),
          r = bytes[k],
          g = bytes[k + 1],
          b = bytes[k + 2];
        if (Math.min(r, g) - b >= 27 && r - b >= 46 && g >= 72 && (g - b) / Math.max(1, r - b) >= 0.45) count[j]++;
      }
    return count.every((x) => x >= 5);
  }

  // Search only to the right and below the printed word along the same roof edge.
  function side(im, pose, neighbours, source, cache) {
    const wc = centre(pose),
      axis = sub(pose[1], pose[0]),
      ww = len(axis);
    const scratch = { grey: new Float64Array(228), yellow: new Float64Array(228), profile: new Float64Array(38) };
    let best = null;
    for (const { q } of neighbours) {
      const [ul, ur, lr, ll] = q,
        c = centre(q),
        offset = sub(c, wc),
        u = sub(ur, ul),
        v = sub(ll, ul),
        w = len(u),
        h = len(v);
      const along = (offset[0] * axis[0] + offset[1] * axis[1]) / (ww * ww),
        below = (-offset[0] * axis[1] + offset[1] * axis[0]) / (ww * ww);
      if (
        (axis[0] * u[0] + axis[1] * u[1]) / (ww * w) < 0.5 ||
        along < 0.15 ||
        along > 2.6 ||
        below < 0.12 ||
        below > 2.25 ||
        w < 8 ||
        h < 2
      )
        continue;
      if (cache.has(q)) {
        const prior = cache.get(q);
        if (prior && (!best || best.score < prior.score)) best = prior;
        continue;
      }
      let local = null;
      for (const scale of [0.7, 0.85, 1, 1.15, 1.35, 1.6])
        for (const ox of [-0.1, 0, 0.12])
          for (const oy of [-1.25, -0.75, -0.25, 0.25])
            for (const roll of [-0.25, 0, 0.25]) {
              const a = add(add(ul, u, ox), v, oy),
                b = add(add(a, u, scale), v, roll);
              if (!golden(im, [a, b])) continue;
              for (const depth of [1.5, 2, 2.5, 3, 3.5, 4])
                for (const shear of [-0.4, 0, 0.4]) {
                  const d = add(add(a, v, depth), u, (shear * depth * h) / w),
                    pts = [a, b, add(d, sub(b, a), 1), d];
                  const cp = centre(pts);
                  if (Math.abs(cp[0] / im.cols - 0.5) > 0.34 || Math.abs(cp[1] / im.rows - 0.5) > 0.4) continue;
                  const e = orangeHeadingProbe(im.data, im.cols, im.rows, 4, pts, source, scratch, true);
                  if (e?.verified && (!local || local.score < e.score)) local = { score: e.score, quad: pts };
                }
            }
      cache.set(q, local);
      if (local && (!best || best.score < local.score)) best = local;
    }
    return best;
  }
  // Rectify the printed word and preserve its greyscale strokes for the general English recognizer.
  function rasters(im, q) {
    const chips = [],
      u = sub(q[1], q[0]),
      v = sub(q[3], q[0]),
      c = centre(q);
    // Re-estimate the baseline of a short, obliquely viewed flavour word within the uncertainty of one source pixel.
    for (const tilt of [0, -0.035, 0.035]) {
      const anchor = rect(c, add(u, [-u[1], u[0]], tilt), v),
        grey = crop(im, anchor, 223, 74, 1.25, 1.8);
      for (const height of [56, 64])
        for (const channel of [0, 1]) {
          const values = [],
            bytes = grey.data;
          for (let i = channel; i < bytes.length; i += 4) values.push(bytes[i]);
          const lo = percentile([...values], 0.1),
            hi = percentile([...values], 0.95),
            width = 251,
            buf = new Uint8Array(width * (height + 28));
          buf.fill(255);
          for (let y = 0; y < height; y++)
            for (let x = 0; x < 223; x++) {
              const px = Math.min(73, Math.round((y * 73) / (height - 1))),
                g = (values[px * 223 + x] - lo) / Math.max(1, hi - lo);
              buf[(y + 14) * width + x + 14] = Math.round(255 * (1 - Math.min(1, Math.max(0, g))));
            }
          chips.push({ width, height: height + 28, bytes: buf, channel });
        }
      grey.delete();
    }
    return chips;
  }
  function sendJob(worker, action, payload) {
    return new Promise((resolve, reject) => {
      worker.onmessage = ({ data }) => {
        if (data.status === 'resolve') resolve(data.data);
        if (data.status === 'reject') reject(Error('Rear print OCR failed'));
      };
      worker.onerror = worker.onmessageerror = () => reject(Error('Rear print OCR unavailable'));
      worker.postMessage({ workerId: 'rear-print', jobId: action, action, payload });
    });
  }

  async function wordPng(raster) {
    const canvas = new OffscreenCanvas(raster.width, raster.height);
    const context = canvas.getContext('2d'),
      image = context.createImageData(raster.width, raster.height);
    for (let i = 0; i < raster.bytes.length; i++) {
      const k = 4 * i;
      image.data[k] = image.data[k + 1] = image.data[k + 2] = raster.bytes[i];
      image.data[k + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    return new Uint8Array(await (await canvas.convertToBlob({ type: 'image/png' })).arrayBuffer());
  }

  async function readFlavourWord(candidates) {
    const worker = new Worker('ocr-worker.js');
    const asset = (name) => new URL(name, self.location.href).href;
    try {
      const langs = ['eng'];
      await sendJob(worker, 'load', {
        options: { lstmOnly: true, corePath: asset('tesseract-core-lstm.wasm.js') }
      });
      await sendJob(worker, 'loadLanguage', {
        langs,
        options: { langPath: asset('./'), gzip: true, lstmOnly: true, cacheMethod: 'none' }
      });
      await sendJob(worker, 'initialize', { langs, oem: 1, config: {} });
      await sendJob(worker, 'setParameters', { params: { tessedit_pageseg_mode: '7' } });
      const read = async (raster) => {
        const observation = await sendJob(worker, 'recognize', {
          image: await wordPng(raster),
          options: {},
          output: { text: true }
        });
        return plainOrangeRoofWord(observation.text);
      };
      for (const candidate of candidates) {
        // Require the raw red and green planes to agree under the very same rectification.
        for (let index = 0; index < candidate.crops.length; index += 2) {
          const red = candidate.crops[index],
            green = candidate.crops[index + 1];
          if ((await read(red)) && (await read(green))) return candidate;
        }
      }
      return null;
    } finally {
      worker.terminate();
    }
  }
  return async function readOrangeRear(rgba, registry) {
    const gtin = '7310860007372',
      product = registry[gtin];
    if (!product || typeof Worker !== 'function' || typeof OffscreenCanvas !== 'function') return null;
    const response = await fetch('../../data/orange-nutrition.json');
    if (!response.ok) return null;
    const gallery = await response.json();
    if (gallery.version !== 1) return null;
    const source = orangeHeaderTemplate(gallery.header);
    const candidates = scoped((own) => {
      const im = own(new cv.Mat()),
        factor = 464 / Math.max(rgba.cols, rgba.rows);
      cv.resize(
        rgba,
        im,
        new cv.Size(Math.round(rgba.cols * factor), Math.round(rgba.rows * factor)),
        0,
        0,
        factor < 1 ? cv.INTER_AREA : cv.INTER_LINEAR
      );
      const poses = proposals(im),
        detection = own(im.clone()),
        pixels = detection.data,
        brightness = [];
      for (let k = 0; k < pixels.length; k += 36)
        brightness.push(Math.max(pixels[k], pixels[k + 1], pixels[k + 2]));
      const exposure = Math.max(0.8, Math.min(1.35, 230 / Math.max(75, percentile(brightness, 0.96))));
      for (let k = 0; k < pixels.length; k++)
        if (k % 4 < 3) pixels[k] = Math.min(255, Math.round(exposure * pixels[k]));
      const neighbours = [...poses, ...proposals(detection)],
        cache = new Map(),
        items = [];
      for (const { q } of poses.slice(0, 18)) {
        const heading = side(im, q, neighbours, source, cache);
        if (!heading) continue;
        const blocks = orangeRearCopy(im, q, heading.quad);
        if (blocks) items.push({ q, heading, blocks });
      }
      return items
        .sort((a, b) => b.heading.score - a.heading.score)
        .slice(0, 3)
        .map((item) => ({ ...item, crops: rasters(im, item.q) }));
    });
    // Most images exit here. The nested English OCR worker starts only for a qualifying rear/roof/side junction.
    if (!candidates.length) return null;
    const match = await readFlavourWord(candidates);
    return match
      ? {
          product,
          gtin,
          view: 'orange-rear-print',
          headingScore: match.heading.score,
          printBaselines: [match.blocks.upper, match.blocks.lower]
        }
      : null;
  };
})();
