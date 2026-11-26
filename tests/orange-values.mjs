import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const read = name => readFile(new URL('../'+name,import.meta.url),'utf8');
const gallery = JSON.parse(await read('web/data/orange-values.json'));
const enrollment = JSON.parse(await read('docs/experiments/orange-side/values-enrollment.json'));
const ctx = vm.createContext({atob});
vm.runInContext(await read('web/vendor/package-reader/orange-values.js'),ctx);
assert.equal(gallery.version,1);
assert.equal(enrollment.length,6);
assert.equal(new Set(enrollment.map(row=>row.sha256)).size,6);
assert.deepEqual(enrollment.filter(row=>row.role==='registered').map(row=>row.gtin),
  Array(3).fill('7310860007372'));
assert.equal(new Set(enrollment.filter(row=>row.role==='competing').map(row=>row.gtin)).size,2);
for (const row of enrollment) {
  const source = ctx.orangeValueSource(gallery.templates[row.id]);
  assert.equal(source.role,row.role);
  assert.equal(source.g.length,2450);
  assert.equal(source.y.length,2450);
  assert.equal(source.g[0],0);
  assert.equal(source.y[49*31+12],0);
  if (source.cg) assert.equal(source.cg.length,16*36);
  if (row.role === 'registered') assert.ok(row.image_url.includes('/dataset/train/'));
  else assert.ok(row.image_url.endsWith('/'+row.id.split('-')[1]+'.400.jpg'));
}
const grey = new Float32Array(2450), yellow = new Float32Array(2450);
const blank = ctx.orangeValueEndpoints(grey,yellow);
assert.deepEqual([...blank.ends],[-1,-1,-1,-1]);
for (const [field,rows,left,right] of [[yellow,[3,4],2,30],[yellow,[6,7],2,32],
                                      [grey,[16,17],21,41],[grey,[20,21],35,41]]) {
  for (const row of rows) for (let col=left;col<=right;col++) field[row*49+col]=60;
}
const printed = ctx.orangeValueEndpoints(grey,yellow);
assert.deepEqual([...printed.ends],[30,32,41,41]);
assert.ok(Math.min(...printed.strengths)>5);

const face = [[.35,.1],[.72,.16],[.65,.90],[.28,.88]];
const alternate = {gtin:'7310860007372',view:'front',votes:[87,0],footprint:face};
const rival = {gtin:'7310865074768',view:'front',votes:[94,0],footprint:face};
const acceptsPair = (a,b) => Boolean(ctx.sharedOrangeRivalFace([a,b],gallery.templates));
assert.ok(acceptsPair(rival,alternate));
assert.equal(acceptsPair({...rival,votes:[94,1]},alternate),false);
assert.equal(acceptsPair({...rival,view:'ingredients'},alternate),false);
assert.equal(acceptsPair({...rival,gtin:'7310860007396'},alternate),false);
assert.equal(acceptsPair(rival,{...alternate,votes:[0,40]}),false);
assert.equal(acceptsPair(rival,{...alternate,footprint:face.map(([x,y])=>[x-.4,y])}),false);
console.log('Orange nutrition endpoints and six source records passed');
