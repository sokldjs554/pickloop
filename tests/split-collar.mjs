import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {runInNewContext} from 'node:vm';

const path = name => new URL('../'+name, import.meta.url);
const read = name => JSON.parse(readFileSync(path(name),'utf8'));
const source = readFileSync(path('web/vendor/package-reader/split-collar.js'),'utf8');
const master = read('web/data/registered-collar.json');
const {matchSplitCollar,collarOnCarton} = runInNewContext(source + '\n({matchSplitCollar,collarOnCarton})');

test('split collar registration uses four distinct training photos and existing logo sources', () => {
  const manifest = read('docs/experiments/split-fruit-collar/enrollment.json');
  const logos = read('web/data/registered-detail-gallery.json').templates;
  assert.equal(master.gtin, manifest.gtin);
  assert.equal(new Set(master.references.map(r=>r.sha256)).size,4);
  assert.deepEqual(master.references.map(r=>r.sha256),manifest.references.map(r=>r.sha256));
  for (const reference of master.references) assert.equal(reference.grid.length,143);
  for (const row of manifest.references) assert.match(row.source,/\/dataset\/train\/Packages\/Juice\//);
  for (const hash of master.logoSources) assert.ok(logos.some(t=>t.sourceHash===hash && t.gtin===master.gtin));
});

test('the registered logo cannot authorize a closure from a neighboring pack', () => {
  const face = [[120,80],[195,74],[197,283],[122,286]];
  assert.equal(collarOnCarton(face,[151,61]),true);
  assert.equal(collarOnCarton(face,[246,61]),false);
  assert.equal(collarOnCarton(face,[154,185]),false);
  assert.equal(collarOnCarton(face,[-40,40]),false);
});

test('dark seam, cap-shaped luminance and white lettering without two fruit colours stay held', () => {
  const w=95,h=95, pixels=new Uint8Array(3*w*h);
  for (let y=0;y<h;y++) for (let x=0;x<w;x++) {
    const inside=((x-47)/24)**2+((y-31)/14)**2 < 1;
    const slit=Math.abs(x-47)<2 && y>39;
    const intensity=inside?225:(y>=32 && y<54 && !slit && x>18 && x<76)?149:32;
    // The horizontal light/dark structure and a neighboring high-contrast inscription remain.
    const letter=y>65 && y<78 && x%7<3;
    pixels.fill(letter?225:intensity,(y*w+x)*3,(y*w+x)*3+3);
  }
  assert.equal(matchSplitCollar(pixels,w,h,master.references),null);
  assert.equal(matchSplitCollar(pixels,w,h,[master.references[0],master.references[0]]),null);
});
