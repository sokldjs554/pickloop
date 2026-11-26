import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const file = new URL('../web/vendor/package-reader/orange-rear.js', import.meta.url);
const implementation = await readFile(file, 'utf8');
const plainWord = vm.runInNewContext(implementation + '\nplainOrangeRoofWord');
test('the roof reader accepts only the complete single flavour word', () => {
  for (const text of ['orange', ' Orange ', '“ORANGE”']) assert.equal(plainWord(text), true);
  for (const text of [
    'ange',
    'arange',
    'orange red grapefruit',
    'rouge',
    '×orange',
    'öorange',
    'orange1',
    'grapefruit',
    'orange 1,75L'
  ]) {
    assert.equal(plainWord(text), false, text);
  }
});

test('a missing gallery entry or unavailable gallery skips the supplemental OCR worker', async () => {
  const root = vm.createContext({
    Worker: class {
      constructor() {
        assert.fail('unavailable gallery or unregistered GTIN opened OCR');
      }
    },
    OffscreenCanvas: class {},
    fetch: async () => ({ ok: false })
  });
  const detect = vm.runInContext(implementation + '\nreadOrangeRear', root);
  assert.equal(await detect({}, {}), null);
  assert.equal(await detect({}, { 7310860007372: 'God-Morgon-Orange-Juice' }), null);
});

test('the rear face needs print at two depths and an adjoining edge', () => {
  const inspect = vm.runInNewContext(implementation + '\norangeRearCopy');
  const width = 180,
    height = 220;
  const word = [
    [48, 14],
    [78, 14],
    [78, 20],
    [48, 20]
  ];
  const heading = [
    [105, 36],
    [145, 38],
    [143, 52],
    [103, 50]
  ];
  function frame(upper, lower, separate) {
    const data = new Uint8Array(width * height * 4).fill(24);
    for (let y = 36; y < height; y++)
      for (let x = 15; x < 103; x++) {
        // Thin printed baselines with spaces between letters on dark carton material.
        const print = (y < 88 ? upper : lower) && y % 5 === 0 && x % 11 < 8;
        const k = 4 * (y * width + x);
        if (print) data.fill(176, k, k + 3);
      }
    if (separate)
      for (let y = 34; y < 111; y++)
        for (let x = 101; x < 110; x++) {
          const k = 4 * (y * width + x);
          data.fill(218, k, k + 3);
        }
    return { cols: width, rows: height, data };
  }
  assert.ok(inspect(frame(true, true, false), word, heading));
  assert.equal(inspect(frame(false, false, false), word, heading), false);
  assert.equal(inspect(frame(true, true, true), word, heading), false);
});
