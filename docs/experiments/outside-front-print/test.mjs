import { strict as assert } from 'node:assert';
import test from 'node:test';
import { outsideFrontPrint } from './outside-print.mjs';

function word(text, x, y, width, height = 12, confidence = 95, block = 1) {
  return [5, 1, block, 1, y, x + 1, x, y, width, height, confidence, text].join('\t');
}
const logo = [word('GOD', 55, 30, 28), word('MOR', 55, 44, 29), word('GON', 55, 58, 28)];
const title = [word('MANGO', 32, 85, 49), word('PASSION', 84, 85, 48)];
const pixels = (shape = [[12, 10, 137, 179]]) => {
  const w = 160, h = 200, data = new Uint8ClampedArray(w * h * 4).fill(255);
  for (const [left, top, right, bottom] of shape) for (let y = top; y <= bottom; y++) {
    for (let x = left; x <= right; x++) data.fill(40, (y * w + x) * 4, (y * w + x) * 4 + 3);
  }
  return {width: w, height: h, data};
};
const run = (lines, image = pixels()) => outsideFrontPrint(lines.join('\n'), image)?.text ?? null;
test('a full manufacturer title on one isolated front supports an outside result', () => {
  assert.equal(run([...logo, ...title]), 'MANGO PASSION');
});
test('an ingredient panel, serving size or second product cannot supply front evidence', () => {
  assert.equal(run([...logo, ...title, word('INGREDIENTS:',10,145,70)]), null);
  assert.equal(run([...logo, ...title, word('TROPICANA',85,15,52)]), null);
  assert.equal(run([...logo, ...title, word('GOD',20,120,22)]), null);
  assert.equal(run([...logo, ...title], pixels([[12,10,145,71],[13,78,144,179]])), null);
  assert.equal(run([...logo, word('per',24,89,20),word('850',55,89,24),word('ml',81,89,18)]), null);
});
test('product quantities require explicit net contents and must exclude every registered volume', () => {
  const quantity = n => [word('NET',28,97,25),word('VOL',55,97,23),word(n,80,97,25),word('ml',108,97,17)];
  assert.equal(run([...logo, ...quantity('850')]), 'NET VOL 850 ML');
  assert.equal(run([...logo, ...quantity('250')]), null);
  assert.equal(run([...logo, ...quantity('1000')]), null);
  assert.equal(run([...logo, ...quantity('175000')]), null);
});
test('front words must remain fully readable, spatially aligned and inside one package silhouette', () => {
  assert.equal(run([...logo, word('MANG?',35,85,46),word('PASSION',84,85,58)]), null);
  assert.equal(run([...logo, ...title.map(x => x.replace('\t95\t','\t35\t'))]), null);
  assert.equal(run([...logo,word('ORANGE',34,85,43),word('RED',80,85,24),word('GRAPEFRUIT',107,85,45)]), null);
  assert.equal(run([...logo, ...title], pixels([[0,0,159,199]])), null);
  assert.equal(run([...logo, ...title, word('2x',35,150,24),word('1L',63,150,20)]), null);
});
