// Interpret undersampled bars using native pixels at different transverse sampling phases.
// This can supply photo identity only; order confirmation is a separate optical path.
globalThis.readSubpixelEAN = (() => {
  // Structure tensors locate small areas of repeated parallel dark/light transitions.
  // Connected components with compatible axes propose lines on the printed face.
  function barcodeRegions(gray, width, height) {
    const step = 2,
      columns = width >> 1,
      rows = height >> 1,
      tileCount = columns * rows;
    const tiles = Array(tileCount).fill(null);
    for (let row = 2; row < rows - 2; row++)
      for (let col = 2; col < columns - 2; col++) {
        let xx = 0,
          xy = 0,
          energy = 0,
          gx = 0,
          gy = 0;
        for (let dy = -2; dy <= 2; dy++)
          for (let dx = -2; dx <= 2; dx++) {
            let j = (row * step + dy) * width + col * step + dx;
            const u =
              gray[j + 1 - width] +
              2 * gray[j + 1] +
              gray[j + 1 + width] -
              gray[j - 1 - width] -
              2 * gray[j - 1] -
              gray[j - 1 + width];
            const v =
              gray[j + width - 1] +
              2 * gray[j + width] +
              gray[j + width + 1] -
              gray[j - width - 1] -
              2 * gray[j - width] -
              gray[j - width + 1];
            const m = Math.hypot(u, v);
            if (!m) continue;
            xx += (u * u - v * v) / m;
            xy += (2 * u * v) / m;
            energy += m;
            gx += u;
            gy += v;
          }
        const norm = Math.hypot(xx, xy);
        if (norm > 0.75 * energy && energy - Math.hypot(gx, gy) > 25 * 55)
          tiles[row * columns + col] = [xx / norm, xy / norm];
      }
    const seen = new Uint8Array(tileCount),
      result = [];
    for (let start = 0; start < tileCount; start++) {
      const root = tiles[start];
      if (seen[start] || !root) continue;
      const group = [start];
      seen[start] = 1;
      for (let j = 0; j < group.length; j++) {
        const k = group[j],
          x = k % columns,
          y = Math.floor(k / columns);
        for (let r = Math.max(0, y - 1); r <= Math.min(rows - 1, y + 1); r++)
          for (let c = Math.max(0, x - 1); c <= Math.min(columns - 1, x + 1); c++) {
            const i = r * columns + c,
              t = tiles[i];
            if (!seen[i] && t && root[0] * t[0] + root[1] * t[1] > 0.72) {
              seen[i] = 1;
              group.push(i);
            }
          }
      }
      if (group.length < 18) continue;
      let xx = 0,
        xy = 0,
        X = 0,
        Y = 0;
      for (const i of group) {
        xx += tiles[i][0];
        xy += tiles[i][1];
        X += i % columns;
        Y += Math.floor(i / columns);
      }
      const centerX = (X * step) / group.length,
        centerY = (Y * step) / group.length,
        angle = Math.atan2(xy, xx) / 2,
        ex = Math.cos(angle),
        ey = Math.sin(angle);
      const coords = group.map((i) => {
        const x = (i % columns) * step - centerX,
          y = Math.floor(i / columns) * step - centerY;
        return [x * ex + y * ey, -x * ey + y * ex];
      });
      let sq = 0,
        ss = 0,
        axisMin = Infinity,
        axisMax = -Infinity;
      for (const [s, q] of coords) {
        sq += s * q;
        ss += s * s;
        axisMin = Math.min(axisMin, s);
        axisMax = Math.max(axisMax, s);
      }
      const slope = sq / Math.max(ss, 1),
        residuals = coords.map(([s, q]) => q - s * slope).sort((a, b) => a - b);
      const acrossMin = residuals[Math.floor(0.07 * group.length)],
        acrossMax = residuals[Math.floor(0.93 * group.length)];
      if (axisMax - axisMin < 22 || axisMax - axisMin > 118 || acrossMax - acrossMin < 5) continue;
      result.push({
        centerX,
        centerY,
        ex,
        ey,
        axisMin,
        axisMax,
        slope,
        acrossMin,
        acrossMax,
        count: group.length,
      });
    }
    return result.sort((a, b) => b.count - a.count).slice(0, 24);
  }
  const EAN_LEFT = [
    '0001101',
    '0011001',
    '0010011',
    '0111101',
    '0100011',
    '0110001',
    '0101111',
    '0111011',
    '0110111',
    '0001011',
  ];
  const EAN_PARITY = [
    'LLLLLL',
    'LLGLGG',
    'LLGGLG',
    'LLGGGL',
    'LGLLGG',
    'LGGLLG',
    'LGGGLL',
    'LGLGLG',
    'LGLGGL',
    'LGGLGL',
  ];
  const invert = (s) => [...s].map((x) => String(1 - Number(x))).join('');
  const signs = (s) => [...s].map((x) => 1 - 2 * Number(x));
  const families = {
    L: EAN_LEFT.map(signs),
    R: EAN_LEFT.map((s) => signs(invert(s))),
    G: EAN_LEFT.map((s) => signs([...invert(s)].reverse().join(''))),
  };
  function encoded(code) {
    return [
      -1,
      1,
      -1,
      ...[...code.slice(1, 7)].flatMap((d, i) => families[EAN_PARITY[code[0]][i]][+d]),
      1,
      -1,
      1,
      -1,
      1,
      ...[...code.slice(7)].flatMap((d) => families.R[+d]),
      -1,
      1,
      -1,
    ];
  }
  function validEAN(code) {
    return (
      /^\d{13}$/.test(code) &&
      [...code].reduce((s, d, i) => s + Number(d) * (i % 2 ? 3 : 1), 0) % 10 === 0
    );
  }
  // Lookup table for the projected integral of a Gaussian point-spread function.
  const cdfTable = new Float64Array(1402);
  let mass = 0;
  for (let k = 0; k < cdfTable.length; k++) {
    const z = (k - 700) / 100;
    mass += Math.exp(-0.5 * z * z);
    cdfTable[k] = mass;
  }
  for (let k = 0; k < cdfTable.length; k++) cdfTable[k] /= mass;
  function normalCDF(z) {
    const x = z * 100 + 699.5;
    if (x <= 0) return 0;
    if (x >= 1400) return 1;
    const i = Math.floor(x);
    return cdfTable[i] + (x - i) * (cdfTable[i + 1] - cdfTable[i]);
  }
  // Basis of a blurred rectangular printed module after removing slow illumination variation.
  function weight(x, sigma, background) {
    return (
      normalCDF(x / sigma) -
      normalCDF((x - 1) / sigma) -
      normalCDF(x / background) +
      normalCDF((x - 1) / background)
    );
  }
  const LUT_SCALE = 8,
    PAD = 10;
  function wave(bits, sigma) {
    const output = new Float32Array((95 + 2 * PAD) * LUT_SCALE + 1),
      background = Math.hypot(sigma, 5.3);
    for (let k = 0; k < output.length; k++) {
      const x = k / LUT_SCALE - PAD;
      let value = 0;
      for (
        let j = Math.max(0, Math.floor(x - 4 * background));
        j < Math.min(95, Math.ceil(x + 4 * background));
        j++
      ) {
        if (bits[j] < 0) value -= 2 * weight(x - j, sigma, background);
      }
      output[k] = value;
    }
    return output;
  }
  function templates(codes) {
    const result = [];
    for (const code of new Set(codes)) {
      if (!validEAN(code)) continue;
      for (const reverse of [false, true]) {
        const bits = encoded(code);
        if (reverse) bits.reverse();
        const profiles = new Map();
        function profile(sigma) {
          const quantized = Math.round(sigma * 12);
          if (!profiles.has(quantized)) profiles.set(quantized, wave(bits, quantized / 12));
          return profiles.get(quantized);
        }
        const fine = profile(1.15),
          coarse = Float64Array.from({ length: 95 }, (_, j) => fine[(j + PAD + 0.5) * LUT_SCALE]);
        const norm = Math.sqrt(coarse.reduce((s, v) => s + v * v, 0));
        for (let j = 0; j < 95; j++) coarse[j] /= norm;
        result.push({ code, reverse, coarse, profile });
      }
    }
    return result;
  }
  function localSignal(gray, width, height, region) {
    const length = region.axisMax - region.axisMin,
      low = region.axisMin - 0.5 * length,
      high = region.axisMax + 0.65 * length;
    const corners = [low, high].flatMap((s) =>
      [region.acrossMin - 1, region.acrossMax + 1].map((z) => {
        const q = z + s * region.slope;
        return [
          region.centerX + s * region.ex - q * region.ey,
          region.centerY + s * region.ey + q * region.ex,
        ];
      }),
    );
    const minX = Math.max(8, Math.floor(Math.min(...corners.map((p) => p[0]))));
    const maxX = Math.min(width - 9, Math.ceil(Math.max(...corners.map((p) => p[0]))));
    const minY = Math.max(8, Math.floor(Math.min(...corners.map((p) => p[1]))));
    const maxY = Math.min(height - 9, Math.ceil(Math.max(...corners.map((p) => p[1]))));
    if (maxX <= minX || maxY <= minY) return [];
    // Work locally; separable Gaussian subtraction on the original pixels preserves subpixel phases.
    const kernel = Array.from({ length: 17 }, (_, i) => Math.exp(-0.5 * ((i - 8) / 2.5) ** 2));
    const norm = kernel.reduce((a, b) => a + b);
    const stride = maxX - minX + 1;
    const horizontalBlur = new Float32Array((maxY - minY + 17) * stride);
    for (let y = minY - 8; y <= maxY + 8; y++)
      for (let x = minX; x <= maxX; x++) {
        let v = 0;
        for (let i = -8; i <= 8; i++) v += kernel[i + 8] * gray[y * width + x + i];
        horizontalBlur[(y - minY + 8) * stride + x - minX] = v / norm;
      }
    const points = [];
    for (let y = minY; y <= maxY; y++)
      for (let x = minX; x <= maxX; x++) {
        const dx = x - region.centerX,
          dy = y - region.centerY,
          s = dx * region.ex + dy * region.ey,
          q = -dx * region.ey + dy * region.ex,
          z = q - s * region.slope;
        if (s < low || s > high || z < region.acrossMin - 1 || z > region.acrossMax + 1) continue;
        let mean = 0;
        for (let i = -8; i <= 8; i++)
          mean += kernel[i + 8] * horizontalBlur[(y + i - minY + 8) * stride + x - minX];
        points.push({ s, q, z, v: gray[y * width + x] - mean / norm });
      }
    return points;
  }
  // Registry codes only propose a projection and PSF. They supply no digits to readBand.
  function propose(region, points, references) {
    if (points.length < 160) return null;
    const length = region.axisMax - region.axisMin,
      minS = region.axisMin - 0.5 * length;
    const bins = new Float32Array(Math.ceil(2.2 * length * 2) + 4),
      counts = new Uint16Array(bins.length);
    for (const p of points) {
      const idx = Math.round((p.s - minS) * 2);
      bins[idx] += p.v;
      counts[idx]++;
    }
    for (let i = 0, prev = -1; i < bins.length; i++) {
      if (!counts[i]) continue;
      bins[i] /= counts[i];
      if (prev < 0) {
        bins.fill(bins[i], 0, i);
      } else
        for (let j = prev + 1; j < i; j++)
          bins[j] = bins[prev] + ((j - prev) * (bins[i] - bins[prev])) / (i - prev);
      prev = i;
    }
    const sample = new Float32Array(95);
    let best = null;
    for (const bend of [-0.12, 0, 0.12]) {
      const fractions = Array.from({ length: 95 }, (_, i) => {
        const t = (i + 0.5) / 95;
        return t / (1 + bend * (1 - t));
      });
      for (
        let start = region.axisMin - 0.36 * length;
        start < region.axisMin + 0.31 * length;
        start += Math.max(0.6, length / 47)
      ) {
        for (let span = 0.76 * length; span < 1.63 * length; span += Math.max(0.75, length / 38)) {
          let energy = 0;
          for (let i = 0; i < 95; i++) {
            const x = (start + span * fractions[i] - minS) * 2;
            const index = Math.min(Math.max(Math.floor(x), 0), bins.length - 2);
            sample[i] =
              bins[index] + Math.min(1, Math.max(0, x - index)) * (bins[index + 1] - bins[index]);
            energy += sample[i] ** 2;
          }
          if (energy < 95 * 64) continue;
          const norm = Math.sqrt(energy);
          for (const ref of references) {
            let dot = 0;
            for (let j = 0; j < 95; j++) dot += sample[j] * ref.coarse[j];
            const score = dot / norm;
            if (score >= 0.72 && (!best || score > best.score))
              best = { ref, score, params: [start, span, bend, 0, 0, 1.15] };
          }
        }
      }
    }
    return best;
  }
  // Along a stripe, s runs across the barcode, q runs along the bars; z removes
  // the face's shear from q so that separated transverse bands stay disjoint.
  function phase(p, params) {
    const t = (p.s - params[0] - params[3] * p.q) / (params[1] + params[4] * p.q);
    return t / (1 + params[2] * (1 - t));
  }
  function score(points, ref, params) {
    const [start, span, bend, skew, tilt, sigma] = params;
    if (
      span < 20 ||
      span > 190 ||
      Math.abs(bend) > 0.4 ||
      Math.abs(skew) > 0.4 ||
      Math.abs(tilt) > 0.5 ||
      sigma < 0.55 ||
      sigma > 2.5
    )
      return 0;
    const template = ref.profile(sigma);
    let energy = 0,
      contrast = 0,
      dot = 0;
    for (const p of points) {
      const u = phase(p, params);
      if (u < -0.05 || u > 1.05) continue;
      const i = (u * 95 + PAD) * LUT_SCALE,
        k = Math.floor(i),
        f = template[k] + (i - k) * (template[k + 1] - template[k]);
      dot += f * p.v;
      energy += f * f;
      contrast += p.v * p.v;
    }
    return dot / Math.sqrt(Math.max(1, energy * contrast));
  }
  // Optimize the six projective/blur parameters on the original grayscale samples.
  function refine(points, proposal) {
    const origin = proposal.params,
      ref = proposal.ref,
      steps = [0.5, 0.8, 0.04, 0.06, 0.08, 0.22];
    const vertex = (params) => ({ params, score: score(points, ref, params) });
    const simplex = [vertex(origin)];
    for (let i = 0; i < 6; i++) {
      const p = origin.slice();
      p[i] += steps[i];
      simplex.push(vertex(p));
    }
    for (let iter = 0; iter < 210; iter++) {
      simplex.sort((a, b) => b.score - a.score);
      const worst = simplex[6],
        best = simplex[0];
      if (iter > 50 && best.score - worst.score < 0.000005) break;
      const mid = origin.map((_, i) => simplex.slice(0, 6).reduce((s, p) => s + p.params[i], 0) / 6);
      const reflect = (k) => vertex(mid.map((v, i) => v + k * (v - worst.params[i])));
      const probe = reflect(1);
      if (probe.score > best.score) {
        const far = reflect(2);
        simplex[6] = far.score > probe.score ? far : probe;
      } else if (probe.score > simplex[5].score) simplex[6] = probe;
      else {
        const shrink = reflect(probe.score > worst.score ? 0.5 : -0.5);
        if (shrink.score > Math.max(probe.score, worst.score)) simplex[6] = shrink;
        else
          for (let j = 1; j <= 6; j++)
            simplex[j] = vertex(simplex[j].params.map((v, i) => (v + best.params[i]) / 2));
      }
    }
    return simplex.sort((a, b) => b.score - a.score)[0];
  }
  // Independent likelihood fit. Each band is decoded against all ten leading
  // parity layouts and all ten possible digits in each of the remaining positions.
  function readBand(points, ref, params) {
    if (points.length < 80) return null;
    const vals = points.map((p) => p.v).sort((a, b) => a - b);
    const gain = vals[Math.floor(0.9 * vals.length)] - vals[Math.floor(0.1 * vals.length)];
    if (gain < 25) return null;
    // W projects each ideal module into the observed photosites. Accumulate W'W
    // and W'y once so coordinate likelihoods do not reread every pixel.
    const gram = Array.from({ length: 95 }, () => new Float64Array(95));
    const observed = new Float64Array(95),
      sigma = params[5],
      background = Math.hypot(sigma, 5.3);
    let observedEnergy = 0;
    const guardRegions = [0, 0, 0];
    let count = 0;
    for (const p of points) {
      const u = phase(p, params);
      if (u < -0.05 || u > 1.05) continue;
      const x = (ref.reverse ? 1 - u : u) * 95;
      if (x >= 0 && x < 3) guardRegions[0]++;
      if (x >= 45 && x < 50) guardRegions[1]++;
      if (x >= 92 && x < 95) guardRegions[2]++;
      const firstModule = Math.max(0, Math.floor(x - 4 * background)),
        pastModule = Math.min(95, Math.ceil(x + 4 * background) + 1);
      const kernel = Float64Array.from({ length: pastModule - firstModule }, (_, i) =>
        weight(x - firstModule - i, sigma, background),
      );
      observedEnergy += p.v * p.v;
      count++;
      for (let i = firstModule; i < pastModule; i++) {
        const v = kernel[i - firstModule];
        observed[i] += v * p.v;
        for (let j = firstModule; j < pastModule; j++) gram[i][j] += v * kernel[j - firstModule];
      }
    }
    if (Math.min(...guardRegions) < 3 || observedEnergy / count < 64) return null;
    const rowSums = gram.map((row) => row.reduce((sum, v) => sum + v, 0));
    const offsets = Array.from({ length: 12 }, (_, j) => 3 + 7 * j + (j >= 6 ? 5 : 0));
    const energy = offsets.map((start, j) =>
      Object.fromEntries(
        (j < 6 ? ['L', 'G'] : ['R']).map((f) => [
          f,
          families[f].map((bits) => {
            let total = 0;
            for (let i = 0; i < 7; i++)
              for (let k = 0; k < 7; k++) total += bits[i] * bits[k] * gram[start + i][start + k];
            return total;
          }),
        ]),
      ),
    );
    const outputs = [];
    for (let lead = 0; lead < 10; lead++) {
      const bits = new Float64Array(95),
        decodedDigits = Array(12).fill(-1);
      bits.set([-1, 1, -1], 0);
      bits.set([1, -1, 1, -1, 1], 45);
      bits.set([-1, 1, -1], 92);
      let estimatedGain = gain;
      // Alternate unconstrained digit choices and least-squares contrast. The
      // starting contrast estimate comes from the band, not from a catalogue SKU.
      for (let gainPass = 0; gainPass < 2; gainPass++) {
        const target = observed.map((v, i) => v / estimatedGain + rowSums[i]);
        for (let sweep = 0; sweep < 8; sweep++) {
          let changed = false;
          for (let j = 0; j < 12; j++) {
            const start = offsets[j],
              f = j < 6 ? EAN_PARITY[lead][j] : 'R';
            bits.fill(0, start, start + 7);
            const residual = [];
            for (let k = start; k < start + 7; k++) {
              let v = target[k];
              for (let i = 0; i < 95; i++) v -= gram[k][i] * bits[i];
              residual.push(v);
            }
            let best = -Infinity,
              digit = -1;
            for (let d = 0; d < 10; d++) {
              let dot = 0;
              for (let i = 0; i < 7; i++) dot += residual[i] * families[f][d][i];
              const fit = 2 * dot - energy[j][f][d];
              if (fit > best) {
                best = fit;
                digit = d;
              }
            }
            if (decodedDigits[j] !== digit) changed = true;
            decodedDigits[j] = digit;
            bits.set(families[f][digit], start);
          }
          if (!changed) break;
        }
        let dot = 0,
          sum = 0;
        for (let i = 0; i < 95; i++) {
          const a = bits[i] - 1;
          dot += a * observed[i];
          if (a) for (let j = 0; j < 95; j++) sum += a * (bits[j] - 1) * gram[i][j];
        }
        estimatedGain = Math.max(20, dot / Math.max(1e-6, sum));
        if (gainPass === 1)
          outputs.push({
            gtin: String(lead) + decodedDigits.join(''),
            score: dot / Math.sqrt(Math.max(1, observedEnergy * sum)),
          });
      }
    }
    outputs.sort((a, b) => b.score - a.score);
    const best = outputs[0];
    if (!validEAN(best.gtin) || best.score < 0.84 || best.score - outputs[1].score < 0.009) return null;
    const fitted = encoded(best.gtin);
    const predicted = gram.map((row) => row.reduce((sum, a, j) => sum + a * (fitted[j] - 1), 0));
    const dot = fitted.reduce((sum, bit, i) => sum + (bit - 1) * observed[i], 0);
    const power = fitted.reduce((sum, bit, i) => sum + (bit - 1) * predicted[i], 0);
    const fittedGain = dot / Math.max(power, 1e-6);
    if (fittedGain < 20) return null;
    const residual = observed.map((v, i) => v / fittedGain - predicted[i]);
    // The chosen digits must individually outperform every alternative digit (even
    // an invalid-checksum alternative). Wiping out a guard must also worsen the fit.
    function advantage(start, alternative) {
      const delta = alternative.map((bit, i) => bit - fitted[start + i]);
      let linear = 0,
        quadratic = 0;
      for (let i = 0; i < delta.length; i++) {
        linear += delta[i] * residual[start + i];
        for (let j = 0; j < delta.length; j++)
          quadratic += delta[i] * delta[j] * gram[start + i][start + j];
      }
      return quadratic > 1e-6 ? (quadratic - 2 * linear) / quadratic : 0;
    }
    const guardMargin = Math.min(
      ...[
        [0, 3],
        [45, 5],
        [92, 3],
      ].flatMap(([s, length]) => [-1, 1].map((v) => advantage(s, Array(length).fill(v)))),
    );
    const digitMargin = Math.min(
      ...offsets.flatMap((s, j) => {
        const group = families[j < 6 ? EAN_PARITY[+best.gtin[0]][j] : 'R'];
        return group.map((alt, k) => (k === Number(best.gtin[j + 1]) ? Infinity : advantage(s, alt)));
      }),
    );
    return guardMargin > 0.12 && digitMargin > 0.065 ? best : null;
  }
  function barcodeConsensus(gray, width, height, codes) {
    // Intended for native-resolution, undersampled codes on compact archive photos.
    if (width * height > 700 * 700 || Math.min(width, height) < 48) return [];
    const candidates = templates(codes),
      result = [];
    for (const region of barcodeRegions(gray, width, height)) {
      const points = localSignal(gray, width, height, region),
        proposal = propose(region, points, candidates);
      if (!proposal) continue;
      const fit = refine(points, proposal);
      if (fit.score < 0.84) continue;
      const spread = points.map((p) => p.z).sort((a, b) => a - b);
      const qLow = spread[Math.floor(0.42 * spread.length)],
        qHigh = spread[Math.floor(0.58 * spread.length)];
      if (qHigh - qLow < 2) continue;
      const left = readBand(
        points.filter((p) => p.z < qLow),
        proposal.ref,
        fit.params,
      );
      if (left?.gtin !== proposal.ref.code) continue;
      const right = readBand(
        points.filter((p) => p.z > qHigh),
        proposal.ref,
        fit.params,
      );
      if (right?.gtin !== left.gtin) continue;
      const centerS = fit.params[0] + 0.5 * fit.params[1],
        centerQ = centerS * region.slope;
      result.push({
        gtin: left.gtin,
        scanLines: 2,
        center: [
          (region.centerX + region.ex * centerS - region.ey * centerQ) / width,
          (region.centerY + region.ey * centerS + region.ex * centerQ) / height,
        ],
        bandScores: [left.score, right.score],
      });
    }
    return result;
  }
  return barcodeConsensus;
})();
