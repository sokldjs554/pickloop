import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const web = process.env.PICKLOOP_WEB || new URL('../../../web/', import.meta.url).pathname;
const context = vm.createContext({});
const worker = await readFile(path.join(web, 'vendor/package-reader/panel-worker.js'), 'utf8');
const helper = await readFile(path.join(web, 'vendor/package-reader/outside-family.js'), 'utf8');
vm.runInContext(worker.slice(worker.indexOf('function area('), worker.indexOf('function visibleArea(')) + helper, context);
const {photoDecision} = await import(pathToFileURL(path.join(web, 'package-reader.js')));
const {sameOutsideFace, outsideCapacityBands, outsideFamilyMarks} = context;
const area = (x, y, r, b) => [[x,y],[r,y],[r,b],[x,b]];

test('same projected foreground can carry an additional capacity observation', () => {
  const focus = area(.28,.05,.83,.98);
  assert.equal(sameOutsideFace(area(.25,.04,.80,.96),focus), true);
  assert.equal(sameOutsideFace(area(.06,.07,.36,.97),focus), false);
  assert.equal(sameOutsideFace(area(.42,.43,.53,.56), focus), false);
  assert.equal(sameOutsideFace(area(.28,.05,.83,.98).reverse(),focus), false);
  assert.equal(sameOutsideFace(null,focus), false);
});

test('one legible field cannot replace missing brand or flavour correspondences', () => {
  const boxes = [[0,0,50,10],[0,20,50,30],[0,40,50,50]];
  const marks = [[2,3],[16,5],[41,3],[2,24],[31,23],[49,23],[1,42],[30,46],[48,43]];
  assert.equal(outsideFamilyMarks(marks, boxes), true);
  assert.equal(outsideFamilyMarks(marks.slice(0,-1),boxes), false);
  assert.equal(outsideFamilyMarks(marks.slice(0,6).concat([[2,42],[3,46],[4,43]]),boxes),false);
});

test('an absent decimal or any other missing capacity glyph prevents a positive size reading', () => {
  const width = 48, height = 20;
  const pattern = Int8Array.from({length:width*height}, (_,i)=>((i*17 + Math.floor(i/width)*11)%119)-58);
  assert.equal(outsideCapacityBands(pattern,pattern,width,height,width,0,0), true);
  for(const [start, end] of [[.075,.257],[.257,.343],[.343,.516],[.516,.755],[.765,.988]]){
    const missing = Float32Array.from(pattern);
    for(let y=0; y<height; y++) {
      missing.fill(0, y*width+Math.round(start*width), y*width+Math.round(end*width));
    }
    assert.equal(outsideCapacityBands(pattern,missing,width,height,width,0,0),false);
  }
});

test('the exact item and order stay held when a conflicting face has a verified outside size', () => {
  const size = {status:'ambiguous',outsideCapacity:'1.75 L'};
  assert.deepEqual(photoDecision({kind:'empty'},size,''),{kind:'hold',reason:'ambiguous_capacity'});
  assert.deepEqual(photoDecision({kind:'empty'},{status:'ambiguous'},''),{kind:'hold',reason:'ambiguous'});
  assert.deepEqual(photoDecision({kind:'unregistered'},size,''),{kind:'hold',reason:'unregistered_code'});
  assert.deepEqual(photoDecision({kind:'multiple'},size,''),{kind:'hold',reason:'barcode'});
  assert.deepEqual(photoDecision({kind:'registered',product:'God-Morgon-Apple-Juice'},size,''),
    {kind:'hold',reason:'ambiguous'});
});

test('a family never supplies a GTIN or replaces the optical or a prior reader conflict', () => {
  const optical = {kind:'registered',product:'God-Morgon-Apple-Juice'};
  const outside = {status:'outside_family', family:'Ginger Shot'};
  assert.deepEqual(photoDecision({kind:'empty'},outside,''), {kind:'hold',reason:'outside_family',family:'Ginger Shot'});
  assert.deepEqual(photoDecision(optical,outside,''), {kind:'barcode',product:optical.product});
  assert.deepEqual(photoDecision(optical,{product:'God-Morgon-Orange-Juice'},''), {kind:'hold',reason:'mismatch'});
  assert.deepEqual(photoDecision({kind:'empty'},{status:'incompatible'},''), {kind:'hold',reason:'incompatible'});
});
