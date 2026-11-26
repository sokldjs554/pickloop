// A thumb can hide the short third title line while leaving the right ends of
// two yellow lines and two white values visible. Require all four printed
// endings plus agreement between independent registered and competing photos.
function orangeValueSource(item) {
  const result = {role:item.role};
  for (const key of ['g','y','cg','cy']) {
    if (!item[key]) continue;
    result[key] = Int8Array.from(atob(item[key]), c => c.charCodeAt(0));
    result[key+'Norm'] = result[key].reduce((sum,v) => sum+v*v,0);
  }
  return result;
}

function orangeValueEndpoints(grey, yellow) {
  const ends = [];
  const strengths = [];
  // For each observed line, subtract the ink-free neighboring rows before
  // finding its last bright pixel. The upper two are titles, the lower two are values.
  for (const [field, ink, gap, left, right] of [
    [yellow,[3,4],[1,5],2,40], [yellow,[6,7],[5,9],2,40],
    [grey,[16,17],[14,18],17,46], [grey,[20,21],[18,23],17,46],
  ]) {
    const row = Array.from({length:49}, (_,x) =>
      (field[ink[0]*49+x]+field[ink[1]*49+x]-field[gap[0]*49+x]-field[gap[1]*49+x])/2);
    const smooth = row.map((v,i) => .39894*v +
      .24197*(row[Math.max(0,i-1)]+row[Math.min(48,i+1)]) +
      .05399*(row[Math.max(0,i-2)]+row[Math.min(48,i+2)]) +
      .00443*(row[Math.max(0,i-3)]+row[Math.min(48,i+3)]));
    const sorted = smooth.slice(left,right).sort((a,b) => a-b);
    const peak = sorted[Math.floor(.9*(sorted.length-1))];
    strengths.push(peak);
    let end = -1;
    for (let x = 0; x < 47; x++) {
      if (smooth[x] > Math.max(3, .33*peak)) end = x;
    }
    ends.push(end);
  }
  return {strengths, ends};
}

function verifiedOrangeValues(own, rgba, quad, sources, excludedSource) {
  const mat = points => own(cv.matFromArray(4,1,cv.CV_32FC2,points.flat()));
  const transform = own(cv.getPerspectiveTransform(mat(quad),mat([[0,0],[48,0],[48,49],[0,49]])));
  const patch = own(new cv.Mat());
  cv.warpPerspective(rgba,patch,transform,new cv.Size(49,50));
  const grey = new Float32Array(2450), yellow = new Float32Array(2450);
  for (let i = 0; i < grey.length; i++) {
    const r = patch.data[4*i], g = patch.data[4*i+1], b = patch.data[4*i+2];
    grey[i] = .299*r+.587*g+.114*b;
    yellow[i] = Math.min(r,g)-b;
  }
  const {strengths, ends} = orangeValueEndpoints(grey,yellow);
  const [title1,title2,value1,value2] = ends;
  const gap = Math.min(value1,value2)-Math.max(title1,title2);
  if (Math.min(...strengths) <= 5 || Math.min(title1,title2) < 2 ||
      Math.abs(title1-title2) > 5 || Math.abs(value1-value2) > 4 || gap < 1 || gap > 15) return false;
  function highpass(field) {
    const signal = own(cv.matFromArray(50,49,cv.CV_32F,field)), smooth = own(new cv.Mat());
    cv.GaussianBlur(signal,smooth,new cv.Size(0,0),1.8);
    cv.subtract(signal,smooth,signal);
    return signal.data32F;
  }
  const g = highpass(grey), y = highpass(yellow);
  let gNorm = 0, yNorm = 0;
  for (let row = 0; row < 50; row++) {
    for (let col = 0; col < 49; col++) {
      const i = 49*row+col;
      if (row < 2 || row >= 47 || col < 3 || (row >= 26 && col < 29)) g[i] = y[i] = 0;
      gNorm += g[i]*g[i];
      yNorm += y[i]*y[i];
    }
  }
  const positives = [], competitors = [];
  let primary = 0;
  for (const [id, source] of Object.entries(sources)) {
    if (id === excludedSource) continue;
    let gDot = 0, yDot = 0;
    for (let i = 0; i < g.length; i++) {
      gDot += g[i]*source.g[i];
      yDot += y[i]*source.y[i];
    }
    const score = .4*gDot/Math.sqrt(Math.max(1,gNorm*source.gNorm)) +
      .6*yDot/Math.sqrt(Math.max(1,yNorm*source.yNorm));
    (source.role === 'registered' ? positives : competitors).push(score);
    if (source.cg) primary = score;
  }
  positives.sort((a,b) => b-a);
  return primary >= .50 && positives[1] >= .45 && positives[1]-Math.max(...competitors) >= .15;
}

function orangeValuePoseScore(rgba, quad, source, scratch) {
  const width = rgba.cols, height = rgba.rows, pixels = rgba.data;
  const [a,b,c,d] = quad;
  const dx1 = b[0]-c[0], dx2 = d[0]-c[0], dx3 = a[0]-b[0]+c[0]-d[0];
  const dy1 = b[1]-c[1], dy2 = d[1]-c[1], dy3 = a[1]-b[1]+c[1]-d[1];
  const det = dx1*dy2-dx2*dy1;
  if (Math.abs(det) < .5) return -1;
  // Unit-square to quadrilateral homography. A bilinear warp shifts the upper
  // values enough to confuse a narrow, foreshortened side panel with its rival.
  const g = (dx3*dy2-dx2*dy3)/det, h = (dx1*dy3-dx3*dy1)/det;
  const {grey, yellow, rows} = scratch;
  for (let row = 0; row < 50; row++) {
    const v = row/49, dx = b[0]-a[0]+g*b[0], dy = b[1]-a[1]+g*b[1];
    const left = a[0]+v*(d[0]-a[0]+h*d[0]), top = a[1]+v*(d[1]-a[1]+h*d[1]);
    for (let col = 0; col < 16; col++) {
      const u = (1+3*col)/48, denominator = 1+g*u+h*v;
      const x = (dx*u+left)/denominator, y = (dy*u+top)/denominator;
      if (x < 0 || y < 0 || x >= width-1 || y >= height-1) return -1;
      const ix = Math.floor(x), iy = Math.floor(y), fx = x-ix, fy = y-iy;
      const i = 4*(iy*width+ix), j = i+4*width;
      const channel = k => (1-fy)*((1-fx)*pixels[i+k]+fx*pixels[i+4+k]) +
        fy*((1-fx)*pixels[j+k]+fx*pixels[j+4+k]);
      const r = channel(0), green = channel(1), blue = channel(2);
      grey[16*row+col] = .299*r+.587*green+.114*blue;
      yellow[16*row+col] = Math.min(r,green)-blue;
    }
  }
  let gNorm = 0, yNorm = 0, gDot = 0, yDot = 0;
  let index = 0;
  for (const row of rows) {
    for (let col = 0; col < 16; col++, index++) {
      if (row < 2 || row > 46 || col === 0 || (row >= 26 && 1+3*col < 29)) continue;
      const i = 16*row+col, before = 16*Math.max(0,row-2)+col, after = 16*Math.min(49,row+2)+col;
      const luma = grey[i]-(grey[before]+grey[after])/2;
      const chroma = yellow[i]-(yellow[before]+yellow[after])/2;
      gNorm += luma*luma;
      yNorm += chroma*chroma;
      gDot += luma*source.cg[index];
      yDot += chroma*source.cy[index];
    }
  }
  return .4*gDot/Math.sqrt(Math.max(1,gNorm*source.cgNorm)) +
    .6*yDot/Math.sqrt(Math.max(1,yNorm*source.cyNorm));
}

function locateOrangeValues(rgba, front, sources) {
  const quad = front.quad.map(([x,y]) => [x*rgba.cols,y*rgba.rows]);
  const [ax,ay] = quad[0], vx = quad[3][0]-ax, vy = quad[3][1]-ay, seam = Math.hypot(vx,vy);
  const bounds = [[.032,.40],[-.30,.22],[-.035,.06],[-.035,.035],[.09,.40],[-.05,.05]];
  const rows = Array.from({length:50},(_,i) => i).filter(i => i < 25 || (i >= 27 && i <= 47 && i%2 === 1));
  const scratch = {grey:new Float64Array(800),yellow:new Float64Array(800),rows};
  const primary = Object.values(sources).find(item => item.cg);
  function projected([span,slope,along,across,depth,shear]) {
    const x = ax+along*vx+across*seam, y = ay+along*vy;
    return [[x-span*seam,y+slope*seam], [x,y], [x+depth*vx,y+depth*vy],
      [x+(shear-span)*seam+depth*vx,y+slope*seam+depth*vy]];
  }
  const measure = values => orangeValuePoseScore(rgba,projected(values),primary,scratch);
  let seed = 14187;
  function random() {
    seed ^= seed << 13;
    seed ^= seed >>> 17;
    seed ^= seed << 5;
    return (seed >>> 0)/4294967296;
  }
  // Refine source-agnostic side-pose hypotheses only after the front flavor
  // and script have been verified. Evaluate all four line endings at full resolution.
  for (let trial = 0; trial < 3; trial++) {
    const pool = Array.from({length:70}, () => bounds.map(([lo,hi]) => lo+random()*(hi-lo)));
    const scores = pool.map(measure);
    let best = 0;
    for (let i = 1; i < pool.length; i++) if (scores[i] > scores[best]) best = i;
    for (let step = 0; step < 85; step++) {
      for (let i = 0; i < pool.length; i++) {
        const a = pool[Math.floor(random()*pool.length)], b = pool[Math.floor(random()*pool.length)];
        const required = Math.floor(random()*bounds.length), factor = .45+.55*random();
        const candidate = pool[i].map((old,k) => {
          if (random() > .8 && k !== required) return old;
          const value = pool[best][k]+factor*(a[k]-b[k]), [lo,hi] = bounds[k];
          return value < lo || value > hi ? lo+random()*(hi-lo) : value;
        });
        const score = measure(candidate);
        if (score > scores[i]) {
          scores[i] = score;
          pool[i] = candidate;
          if (score > scores[best]) best = i;
        }
      }
    }
    const finalists = pool.map((candidate,i) => ({candidate,score:scores[i]})).sort((a,b) => b.score-a.score);
    if (finalists.slice(0,4).some(({candidate}) => {
      const region = projected(candidate);
      const x = region.reduce((sum, point) => sum+point[0]/rgba.cols,0)/4;
      const y = region.reduce((sum, point) => sum+point[1]/rgba.rows,0)/4;
      return Math.abs(x-.5) < .34 && Math.abs(y-.5) < .40 &&
        scoped(own => verifiedOrangeValues(own,rgba,region,sources));
    })) return true;
  }
  return false;
}

async function readOrangeValues(rgba, front) {
  const response = await fetch('../../data/orange-values.json');
  if (!response.ok) throw Error('Nutrition column evidence unavailable');
  const gallery = await response.json();
  if (gallery.version !== 1) throw Error('Unknown nutrition column gallery');
  const sources = Object.fromEntries(Object.entries(gallery.templates).map(([id,item]) => [id,orangeValueSource(item)]));
  return locateOrangeValues(rgba,front,sources);
}

// Old orange cartons share their upper front print. When the proposed rival has
// zero lower-face inliers, an independent, adjacent values panel can disambiguate it.
function sharedOrangeRivalFace(seen, templates) {
  const rival = seen[0];
  if (rival?.view !== 'front' || rival.votes[1] !== 0) return null;
  const records = Object.values(templates);
  if (!records.some(row => row.role === 'competing' && row.gtin === rival.gtin)) return null;
  const registered = new Set(records.filter(row => row.role === 'registered').map(row => row.gtin));
  const alternative = seen.find(hit => registered.has(hit.gtin) && hit.view === 'front' && hit.votes[0] >= 4);
  if (!alternative) return null;
  const diagonal = Math.hypot(rival.footprint[2][0]-rival.footprint[0][0],
    rival.footprint[2][1]-rival.footprint[0][1]);
  const sameFace = rival.footprint.every(([x,y],i) =>
    Math.hypot(x-alternative.footprint[i][0],y-alternative.footprint[i][1]) < .20*diagonal);
  return sameFace ? rival.footprint : null;
}

async function resolveSharedOrangeFront(rgba, matcher, registry, seen, decision) {
  if (decision?.status !== 'incompatible' || seen[0]?.view !== 'front' || seen[0].votes[1] !== 0 ||
      !seen.some(hit => hit.view === 'front' && registry[hit.gtin] && hit.votes[0] >= 4)) return decision;
  const response = await fetch('../../data/orange-values.json');
  if (!response.ok) return decision;
  const gallery = await response.json();
  if (gallery.version !== 1) return decision;
  const footprint = sharedOrangeRivalFace(seen,gallery.templates);
  if (!footprint) return decision;
  const proof = await readSideEvidence(rgba,matcher,registry,footprint);
  return proof?.view === 'orange-nutrition-values' ? proof : decision;
}
