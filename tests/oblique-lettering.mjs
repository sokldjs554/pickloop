import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {test} from 'node:test';

const source = readFileSync(new URL('../web/vendor/package-reader/printed-regions.js',import.meta.url),'utf8');
const samePanel = runInNewContext(source + '\nsamePrintedPanel');
const mixed = {gtin:'registered',source:'first',marks:[[100,40],[104,61],[108,73]]};
const same = {gtin:'registered',source:'second',marks:[[101,42],[105,62],[109,73]]};

test('lettering votes must agree on SKU, separate enrolled source and physical panel', () => {
  assert.ok(samePanel(mixed,same));
  assert.equal(samePanel(mixed,{...same,source:'first'}),false);
  assert.equal(samePanel(mixed,{...same,gtin:'different'}),false);
  const neighbor = same.marks.map(([x,y])=>[x+30,y]);
  assert.equal(samePanel(mixed,{...same,marks:neighbor}),false);
  assert.equal(samePanel(mixed,{...same,marks:[same.marks[0],same.marks[1],neighbor[2]]}),false);
});

test('two distinct verified training photos each require the brand and both fruit markings', () => {
  const read = path => JSON.parse(readFileSync(new URL(path,import.meta.url)));
  const refs=read('../docs/experiments/side-panel-lettering/oblique-enrollment.json');
  const archive=readFileSync(new URL('../docs/experiments/registered-recall/archive-labels.csv',import.meta.url),'utf8');
  const gallery=read('../web/data/registered-detail-gallery.json').templates.filter(t=>t.oblique);
  assert.equal(new Set(refs.map(r=>r.sha256)).size,2);
  assert.equal(gallery.length,refs.length);
  for (const ref of refs) {
    assert.match(ref.source,/\/dataset\/train\//);
    assert.equal(archive.includes(ref.sha256),false);
    const active=gallery.find(template=>template.sourceHash===ref.sha256);
    assert.equal(active.gtin,ref.gtin);
    assert.deepEqual(active.details.map(p=>p.minimum),[.43,.50,.50]);
    assert.ok(ref.zones[1][3] <= ref.zones[2][1]+8);
  }
});
