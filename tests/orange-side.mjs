import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const load = name => readFile(new URL('../' + name, import.meta.url), 'utf8');
const source = await load('web/vendor/package-reader/orange-side.js');
const context = vm.createContext({
  area: points => points.reduce((sum,[x,y],i) => {
    const [u,v] = points[(i+1)%points.length];
    return sum + x*v - y*u;
  }, 0)/2,
});
vm.runInContext(source, context);
const proof = observations => context.orangeAdjoiningProof(observations);
const gtin = '7310860007372';
const face = (source,view,left,right) => ({source,view,gtin,inliers:40,
  quad:[[left,.1],[right,.1],[right,.9],[left,.9]]});
const front = face('A','front',.22,.48);
const side = face('B','ingredients',.48,.75);
const second = {...side,source:'C'};
assert.equal(proof([front,side,second]).gtin,gtin);
assert.equal(proof([front]),null);
assert.equal(proof([side,second]),null);
assert.equal(proof([front,side,{...side}]),null);
assert.equal(proof([front,side,{...second,gtin:'7310865074768'}]),null);
assert.equal(proof([front,side,face('C','ingredients',.63,.9)]),null);
assert.equal(proof([face('A','front',.02,.20),side,second]),null);

const raw = await load('web/data/orange-side.json');
const gallery = JSON.parse(raw);
const rows = JSON.parse(await load('docs/experiments/orange-side/enrollment.json'));
const references = new Map(rows.map(row => [row.sha256 + row.view,row]));
assert.equal(gallery.version,1);
assert.equal(gallery.templates.length,9);
for (const item of gallery.templates) {
  const row = references.get(item.source+item.view);
  assert.ok(row);
  assert.equal(row.gtin,item.gtin);
  assert.ok(row.source.includes('/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/train/'));
  assert.ok(item.points.length >= 100);
  assert.equal(Buffer.from(item.descriptors,'base64').byteLength,32*item.points.length);
  assert.ok(item.points.every(([x,y]) => x >= 0 && x <= 1000 && y >= 0 &&
    y <= (item.view === 'front' ? 420 : 630)));
}
console.log('Orange side evidence and gallery passed',createHash('sha256').update(raw).digest('hex'));
