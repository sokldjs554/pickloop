import assert from 'node:assert/strict';
import test from 'node:test';
import '../web/vendor/package-reader/subpixel-ean.js';

// Independently specified physical bit patterns. Sampling below deliberately
// projects 95 modules onto 43 native pixels, then blurs and integrates each pixel.
const apple = '7310865074225',
  large = '7310865081650';
const patterns = {
  [apple]:
    '10101111010110011000110100010010101111011100101010111001010001001011100110110011011001001110101',
  [large]:
    '10101111010110011000110100010010101111011100101010111001010010001100110101000010011101110010101',
  unknown:
    '10101111010110011000110100010010101111011100101010111001010001001011100110110010000101101100101',
};
const width = 260,
  height = 230;
function image(code, { other, erased, contrast = 200 } = {}) {
  const raster = new Uint8Array(width * height).fill(135);
  const taps = [];
  // Convolve a 9x uniform photosite integral with Gaussian optics, away from frame edges.
  for (let i = -16; i <= 24; i++) {
    let weight = 0;
    for (let j = 0; j < 9; j++) weight += Math.exp(-0.5 * ((i - j) / 4.05) ** 2);
    taps.push({ offset: i / 9, weight });
  }
  const weightSum = taps.reduce((v, t) => v + t.weight, 0);
  for (let y = 80; y < 155; y++)
    for (let x = 90; x < 165; x++) {
      let brightness = 0;
      for (const a of taps)
        for (const b of taps) {
          const dx = x + a.offset - 126,
            dy = y + b.offset - 115,
            s = dx * 0.13 + dy * 0.9915,
            q = -dx * 0.9915 + dy * 0.13,
            z = q - 0.32 * s;
          const t = s / (43 + 0.045 * q) + 0.5,
            u = t / (1 + 0.045 * (1 - t)),
            i = Math.floor((1 - u) * 95);
          let value = 135;
          if (Math.abs(z) < 14 && u > -0.09 && u < 1.09) {
            const pat = patterns[z > 0 && other ? other : code];
            let ink = i >= 0 && i < 95 && pat[i] === '1' ? -1 : 1;
            if (erased === 'guards' && [0, 2, 46, 48, 92, 94].includes(i)) ink = 1;
            if (erased === 'digits' && i >= 27 && i < 39) ink = 0;
            value = 126 + contrast * 0.5 * ink;
          }
          brightness += a.weight * b.weight * value;
        }
      raster[y * width + x] = Math.floor(brightness / (weightSum * weightSum));
    }
  return raster;
}
const scan = (photo, codes = [apple, large]) =>
  globalThis.readSubpixelEAN(photo, width, height, codes).map((r) => r.gtin);
test('independently decodes two valid but different print patterns of the same brand', () => {
  assert.deepEqual(scan(image(apple)), [apple]);
  assert.deepEqual(scan(image(large)), [large]);
  assert.deepEqual(scan(image(large), [apple]), []);
});
test('withholds results with contradictory bands, missing guards, missing digits or low contrast', () => {
  for (const options of [{ other: large }, { erased: 'guards' }, { erased: 'digits' }, { contrast: 16 }])
    assert.deepEqual(scan(image(apple, options)), []);
  assert.deepEqual(scan(image('unknown')), []);
});
