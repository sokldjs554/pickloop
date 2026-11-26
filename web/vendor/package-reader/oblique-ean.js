// Recover printed EAN evidence from coherent, foreshortened bars after a normal
// optical read fails. The caller uses this as photo evidence, never as an order.
// A catalogue pattern proposes a sampling grid. All digits and the leading parity
// must then win an independent unconstrained decode on two separated scanlines.
globalThis.readObliqueEAN = (() => {
  const left = ['0001101', '0011001', '0010011', '0111101', '0100011',
    '0110001', '0101111', '0111011', '0110111', '0001011'];
  const parity = ['LLLLLL', 'LLGLGG', 'LLGGLG', 'LLGGGL', 'LGLLGG',
    'LGGLLG', 'LGGGLL', 'LGLGLG', 'LGLGGL', 'LGGLGL'];
  const invert = pattern => [...pattern].map(bit => 1 - Number(bit)).join('');
  const family = {L: left, G: left.map(s => [...invert(s)].reverse().join('')), R: left.map(invert)};
  const bipolar = s => [...s].map(c => 1 - 2 * Number(c));
  const digits = Object.fromEntries(Object.entries(family).map(([key, val]) => [key, val.map(bipolar)]));

  function validEAN(code) {
    if (!/^\d{13}$/.test(code)) return false;
    const sum = [...code].reduce((s, d, i) => s + Number(d) * (i % 2 ? 3 : 1), 0);
    return sum % 10 === 0;
  }

  function encode(code) {
    const lhs = [...parity[Number(code[0])]].map((f, i) => family[f][Number(code[i + 1])]).join('');
    const rhs = [...code.slice(7)].map(d => family.R[Number(d)]).join('');
    return bipolar('101' + lhs + '01010' + rhs + '101');
  }

  function decodeModules(modules) {
    const choices = [];
    for (let group = 0; group < 12; group++) {
      const start = 3 + 7 * group + (group >= 6 ? 5 : 0);
      const choicesHere = {};
      for (const f of group < 6 ? ['L', 'G'] : ['R']) {
        let score = -Infinity, digit = -1;
        for (let d = 0; d < 10; d++) {
          let dot = 0;
          for (let i = 0; i < 7; i++) dot += digits[f][d][i] * modules[start + i];
          if (dot > score) { score = dot; digit = d; }
        }
        choicesHere[f] = {digit, score};
      }
      choices.push(choicesHere);
    }
    let bestCode = null, bestScore = -Infinity;
    for (let lead = 0; lead < 10; lead++) {
      let code = String(lead), total = 0;
      for (let i = 0; i < choices.length; i++) {
        const digit = choices[i][i < 6 ? parity[lead][i] : 'R'];
        total += digit.score;
        code += digit.digit;
      }
      if (total > bestScore) { bestScore = total; bestCode = code; }
    }
    // Never repair a failed checksum by substituting a registered digit.
    return validEAN(bestCode) ? bestCode : null;
  }

  function stripeRegions(pixels, width, height) {
    const step = 16, cols = Math.floor(width / step), rows = Math.floor(height / step);
    const tiles = Array(cols * rows).fill(null);
    for (let ty = 0; ty < rows; ty++) {
      for (let tx = 0; tx < cols; tx++) {
        let xx = 0, xy = 0, yy = 0, strong = 0;
        for (let y = 1; y < step - 1; y += 2) {
          for (let x = 1; x < step - 1; x += 2) {
            const k = (ty * step + y) * width + tx * step + x;
            const dx = pixels[k + 1] - pixels[k - 1], dy = pixels[k + width] - pixels[k - width];
            const mag = Math.hypot(dx, dy);
            if (mag < 7) continue;
            xx += dx * dx / mag;
            xy += 2 * dx * dy / mag;
            yy += dy * dy / mag;
            strong++;
          }
        }
        const length = Math.hypot(xx - yy, xy);
        if (strong >= 16 && length > .77 * (xx + yy) && xx + yy > 500) {
          tiles[ty * cols + tx] = [(xx - yy) / length, xy / length];
        }
      }
    }

    const seen = new Uint8Array(tiles.length), regions = [];
    for (let start = 0; start < tiles.length; start++) {
      if (!tiles[start] || seen[start]) continue;
      const group = [start], axis = tiles[start];
      seen[start] = 1;
      for (let j = 0; j < group.length; j++) {
        const x = group[j] % cols, y = Math.floor(group[j] / cols);
        for (let ty = Math.max(0, y - 1); ty <= Math.min(rows - 1, y + 1); ty++) {
          for (let tx = Math.max(0, x - 1); tx <= Math.min(cols - 1, x + 1); tx++) {
            const index = ty * cols + tx, t = tiles[index];
            if (t && !seen[index] && axis[0] * t[0] + axis[1] * t[1] > .72) {
              seen[index] = 1;
              group.push(index);
            }
          }
        }
      }
      // Limit reads to substantial visible bar regions on the subject.
      if (group.length < 6 || group.length * step * step < .004 * width * height) continue;
      const points = group.map(k => [(k % cols + .5) * step, (Math.floor(k / cols) + .5) * step]);
      const cx = points.reduce((sum, p) => sum + p[0], 0) / points.length;
      const cy = points.reduce((sum, p) => sum + p[1], 0) / points.length;
      if (cx < .1 * width || cx > .9 * width || cy < .1 * height || cy > .9 * height) continue;
      let xx = 0, xy = 0, yy = 0;
      for (const [x, y] of points) { xx += (x-cx)**2; xy += (x-cx)*(y-cy); yy += (y-cy)**2; }
      const angle = .5 * Math.atan2(2 * xy, xx - yy), dx = Math.cos(angle), dy = Math.sin(angle);
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (const [x, y] of points) {
        const along = (x - cx) * dx + (y - cy) * dy;
        const across = -(x - cx) * dy + (y - cy) * dx;
        minX = Math.min(minX, along); maxX = Math.max(maxX, along);
        minY = Math.min(minY, across); maxY = Math.max(maxY, across);
      }
      const length = maxX - minX + step, breadth = maxY - minY + step;
      if (length >= 95 && breadth < length) regions.push({cx, cy, angle, length, breadth, count: group.length});
    }
    return regions.sort((a, b) => b.count - a.count).slice(0, 8);
  }

  function sample(pixels, width, height, x, y) {
    if (x < 0 || y < 0 || x >= width - 1 || y >= height - 1) return 180;
    const k = Math.floor(y) * width + Math.floor(x), u = x % 1, v = y % 1;
    return (pixels[k] * (1-u) + pixels[k+1] * u) * (1-v) +
      (pixels[k+width] * (1-u) + pixels[k+width+1] * u) * v;
  }

  function scanLine(pixels, width, height, region, delta, offset) {
    const angle = region.angle + delta, dx = Math.cos(angle), dy = Math.sin(angle);
    const count = Math.ceil(Math.min(1800, region.length * 1.8 + 50));
    const cx = region.cx - dy * offset, cy = region.cy + dx * offset;
    const raw = Float32Array.from({length: count}, (_, j) =>
      sample(pixels, width, height, cx + (j-count/2)*dx, cy + (j-count/2)*dy));
    let sum = 0;
    const prefix = Float64Array.from(raw, z => (sum += z)), radius = Math.max(5, Math.round(region.length / 30));
    const contrast = raw.map((z, i) => {
      const l = Math.max(0, i - radius), r = Math.min(i + radius, count - 1);
      return z - (prefix[r] - (l ? prefix[l - 1] : 0)) / (r - l + 1);
    });
    const runs = [];
    let start = 0;
    for (let i = 1; i < count; i++) {
      if (contrast[i] < -1 && contrast[i - 1] >= -1) start = i;
      if (contrast[i] >= -1 && contrast[i - 1] < -1) runs.push([start, i]);
    }
    return {contrast, runs};
  }

  // Under perspective the mapping along a printed line is a 1D homography.
  const grids = Array.from({length: 21}, (_, k) => {
    const bend = (k - 10) * .035;
    return Float32Array.from({length: 95}, (_, j) => {
      const t = (j + .5) / 95;
      return t / (1 + bend * (1 - t));
    });
  });

  function interpret({contrast, runs}, templates) {
    let bestCode = null, bestScore = .775;
    const modules = new Float32Array(95);
    for (let i = 0; i < runs.length; i++) {
      // An EAN normally has 30 dark bars. Merged narrow bars are common on oblique faces.
      for (let j = i + 21; j < Math.min(i + 38, runs.length); j++) {
        const start = runs[i][0], end = runs[j][1], span = end - start;
        if (span < 95 || (i && start - runs[i-1][1] < span / 95 * 1.5) ||
            (j+1 < runs.length && runs[j+1][0] - end < span / 95 * 1.5)) continue;
        for (const grid of grids) {
          let energy = 0;
          for (let k = 0; k < 95; k++) {
            const x = start + span * grid[k], ix = Math.floor(x);
            modules[k] = contrast[ix] + (contrast[ix+1] - contrast[ix]) * (x-ix);
            energy += modules[k]**2;
          }
          if (energy < 95 * 16) continue;
          for (const ref of templates) {
            let dot = 0;
            for (let k = 0; k < 95; k++) dot += modules[k] * ref.pattern[k];
            const score = dot / Math.sqrt(95 * energy);
            if (score <= bestScore) continue;
            const decoded = decodeModules(ref.reverse ? modules.slice().reverse() : modules);
            if (decoded === ref.code) { bestCode = decoded; bestScore = score; }
          }
        }
      }
    }
    return bestCode;
  }

  return function readObliqueEAN(gray, width, height, codes) {
    const templates = [];
    for (const code of new Set(codes)) {
      if (!validEAN(code)) continue;
      const pattern = encode(code);
      templates.push({code, pattern, reverse: false}, {code, pattern: pattern.slice().reverse(), reverse: true});
    }
    const matches = new Map();
    for (const region of stripeRegions(gray, width, height)) {
      for (const delta of [0, -.1, .1, -.2, .2]) {
        // Require spatially separated parallel lines through the same region to agree.
        const offsets = new Map();
        for (const f of [0, -.14, .14, -.28, .28]) {
          const offset = f * region.breadth;
          const code = interpret(scanLine(gray, width, height, region, delta, offset), templates);
          if (!code) continue;
          const record = offsets.get(code) || [];
          record.push(offset);
          offsets.set(code, record);
          if (record.length >= 2 && Math.max(...record) - Math.min(...record) >= 8) {
            matches.set(code, Math.max(matches.get(code) || 0, record.length));
          }
        }
      }
    }
    return [...matches].map(([gtin, scanLines]) => ({gtin, scanLines}));
  };
})();
