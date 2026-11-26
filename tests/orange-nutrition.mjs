import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import vm from 'node:vm';

const read = name => readFile(new URL('../'+name,import.meta.url),'utf8');
const context = vm.createContext({atob});
vm.runInContext(await read('web/vendor/package-reader/orange-nutrition.js'), context);
const parts = JSON.parse(await read('web/data/orange-nutrition.json'));
const enrollment = JSON.parse(await read('docs/experiments/orange-side/nutrition-enrollment.json'));
assert.equal(parts.version,1);
assert.equal(enrollment.header.sha256.length,64);
assert.ok(enrollment.header.source.includes('/dataset/train/Packages/Juice/God-Morgon-Orange-Juice/'));
for (const front of enrollment.fronts) {
  assert.ok(front.source.includes('/dataset/train/'));
  const patches = parts.fronts[front.sha256];
  assert.equal(patches.length,2);
  for (const item of patches) assert.equal(Buffer.from(item.pattern,'base64').length,28*9);
}
const reference = context.orangeHeaderTemplate(parts.header);
assert.equal(reference.grey.length,228);
assert.equal(reference.yellow.length,228);
const scratch = {grey:new Float64Array(228),yellow:new Float64Array(228),profile:new Float64Array(38)};
const blank = new Uint8Array(96*96*3).fill(127);
const quad = [[2,2],[90,2],[90,90],[2,90]];
assert.equal(context.orangeHeadingProbe(blank,96,96,3,quad,reference,scratch,true).verified,false);
const leftProfile = Float64Array.from({length:38},(_,i) => [2,3,5,6,8,9].includes(i) ? 10 : -4);
assert.equal(context.orangeHeadingPattern(.8,6,-4,5,leftProfile),true);
assert.equal(context.orangeHeadingPattern(.8,-1,-4,5,leftProfile),false);
assert.equal(context.orangeHeadingPattern(.8,6,4,5,leftProfile),false);
assert.equal(context.orangeHeadingPattern(.8,6,-4,-1,leftProfile),false);
assert.equal(context.orangeHeadingPattern(.4,6,-4,5,leftProfile),false);

// Optional real-photo challenge. Only the original public URLs, hashes and the
// bounds of the printed nutrition label are versioned. The runner never writes images.
const controls = JSON.parse(await read('docs/experiments/orange-side/nutrition-controls.json'));
assert.equal(controls.length,3);
if (process.argv[2]) {
  const directory = process.argv[2];
  for (const row of controls) {
    const local = path.join(directory,row.key+'.preview.jpg');
    const file = await readFile(local);
    assert.equal(createHash('sha256').update(file).digest('hex'),row.sha256);
    const decoded = spawnSync('python',['-c',
      'import sys;from PIL import Image;sys.stdout.buffer.write(Image.open(sys.argv[1]).convert("RGB").tobytes())',
      local], {maxBuffer:8e6});
    assert.equal(decoded.status,0,decoded.stderr.toString());
    const [width,height] = row.size;
    assert.equal(decoded.stdout.length,3*width*height);
    const [x,y,right,bottom] = row.box, w = right-x, h = bottom-y;
    let tested = 0, accepted = 0;
    // Offset, zoom and skew the observation window to give a differently wrapped
    // label a chance to fit the positive pattern. Each source remains one photo.
    for (const span of [.72,.86,1]) for (const shift of [-.025,0,.025])
    for (const offset of [-.14,-.07,0,.07,.14]) for (const scale of [.75,.88,1,1.12,1.25,1.5,1.75])
    for (const tilt of [-.08,0,.08]) {
      const left = Math.max(0,x+w*shift), end = Math.min(width-2,left+w*span);
      const top = y+offset*h, low = top+h*scale;
      const patch = [[left,top],[end,top+h*tilt],[end,low+h*tilt],[left,low]];
      const result = context.orangeHeadingProbe(decoded.stdout,width,height,3,patch,reference,scratch,true);
      if (result) {
        tested++;
        if (result.verified) accepted++;
      }
    }
    assert.ok(tested >= 800);
    assert.equal(accepted,0,row.key);
    console.log(row.key, '0 accepted in',tested,'alignments');
  }
}
console.log('Orange nutrition evidence checks passed');
