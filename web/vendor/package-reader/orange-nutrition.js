// The old Swedish 1 L, Finnish 1 L and Swedish 1.75 L use the same orange illustration.
// Compare the printed single flavor, script underneath it and the adjacent nutrition heading.
// The registered heading has two long yellow lines, a short third line and white values below.
function orangeHeaderTemplate(item) {
  const unpack = text => Int8Array.from(atob(text), c => c.charCodeAt(0));
  const squaredNorm = values => values.reduce((sum, v) => sum + v*v, 0);
  const grey = unpack(item.grey), yellow = unpack(item.yellow);
  return {grey, yellow, greyNorm: squaredNorm(grey), yellowNorm: squaredNorm(yellow)};
}

function orangeHeadingPattern(score, third, right, dip, profile) {
  return score >= .55 && third > 2.5 && right < 0 && dip > 1 &&
    profile[2] + profile[3] > 0 && profile[5] + profile[6] > 0 && profile[8] + profile[9] > 0;
}

function orangeHeadingProbe(pixels, width, height, channels, quad, source, scratch, details = false) {
  const {grey, yellow, profile} = scratch;
  profile.fill(0);
  for (let row = 0; row < 19; row++) {
    const t = row / 18;
    const leftX = quad[0][0] + t*(quad[3][0]-quad[0][0]);
    const leftY = quad[0][1] + t*(quad[3][1]-quad[0][1]);
    const rightX = quad[1][0] + t*(quad[2][0]-quad[1][0]);
    const rightY = quad[1][1] + t*(quad[2][1]-quad[1][1]);
    for (let col = 0; col < 12; col++) {
      const u = (col + .5)/12;
      const x = leftX + u*(rightX-leftX), y = leftY + u*(rightY-leftY);
      if (x < 0 || y < 0 || x >= width-1 || y >= height-1) return null;
      const ix = Math.floor(x), iy = Math.floor(y), dx = x-ix, dy = y-iy;
      const top = channels*(iy*width+ix), bottom = top+channels*width;
      const sample = channel =>
        (1-dy)*((1-dx)*pixels[top+channel] + dx*pixels[top+channels+channel]) +
        dy*((1-dx)*pixels[bottom+channel] + dx*pixels[bottom+channels+channel]);
      const r = sample(0), g = sample(1), b = sample(2), index = 12*row+col;
      grey[index] = .299*r + .587*g + .114*b;
      yellow[index] = Math.min(r,g)-b;
    }
  }
  let greyDot = 0, yellowDot = 0, greyNorm = 0, yellowNorm = 0;
  for (let row = 0; row < 19; row++) {
    for (let col = 0; col < 12; col++) {
      const i = 12*row+col, above = 12*Math.max(0,row-2)+col, below = 12*Math.min(18,row+2)+col;
      const luminance = grey[i] - (grey[above]+grey[below])/2;
      const chroma = yellow[i] - (yellow[above]+yellow[below])/2;
      greyDot += luminance*source.grey[i];
      yellowDot += chroma*source.yellow[i];
      greyNorm += luminance*luminance;
      yellowNorm += chroma*chroma;
      if (col < 4) profile[row] += chroma/4;
      else if (col >= 6 && col < 11) profile[19+row] += chroma/5;
    }
  }
  const score = .4*greyDot/Math.sqrt(Math.max(1, greyNorm*source.greyNorm)) +
    .6*yellowDot/Math.sqrt(Math.max(1, yellowNorm*source.yellowNorm));
  const shortLine = (profile[8]+profile[9])/2;
  const third = shortLine - (profile[7]+profile[10])/2;
  const right = (profile[27]+profile[28])/2;
  const dip = Math.min((profile[2]+profile[3])/2-profile[4], (profile[5]+profile[6])/2-profile[4]);
  const verified = orangeHeadingPattern(score,third,right,dip,profile);
  if (details) return {score, third, right, dip, verified};
  const limit = value => Math.max(-1, Math.min(1,value/13));
  return score + .28*limit(third) + .14*limit(shortLine-right) + .13*limit(dip) + Number(verified);
}

function orangeHeadingSearch(frame, front, source) {
  const width = frame.cols, height = frame.rows, data = frame.data;
  const quad = front.quad.map(([x,y]) => [x*width,y*height]);
  const [ax,ay] = quad[0], vx = quad[3][0]-ax, vy = quad[3][1]-ay, seam = Math.hypot(vx,vy);
  // The heading starts on the other side of the shared carton seam. Width, top
  // inclination, seam offsets, height and perspective vary independently by pose.
  const bounds = [[.12,.67],[-.48,.35],[-.045,.085],[-.045,.045],[.05,.16],[-.045,.045]];
  function points([span, slope, along, across, depth, shear]) {
    const x = ax+along*vx+across*seam, y = ay+along*vy;
    return [[x-span*seam,y+slope*seam], [x,y], [x+depth*vx,y+depth*vy],
      [x+(shear-span)*seam+depth*vx,y+slope*seam+depth*vy]];
  }
  const scratch = {grey:new Float64Array(228), yellow:new Float64Array(228), profile:new Float64Array(38)};
  const measure = params => orangeHeadingProbe(data,width,height,4,points(params),source,scratch) ?? -1;
  // Bounded differential evolution searches this six-dimensional face pose.
  // The fixed seed makes identical images reproducible in a disposable worker.
  let seed = 41721;
  function random() {
    seed ^= seed << 13;
    seed ^= seed >>> 17;
    seed ^= seed << 5;
    return (seed >>> 0)/4294967296;
  }
  let best = null;
  for (let trial = 0; trial < 2; trial++) {
    const pool = Array.from({length:70}, () => bounds.map(([lo,hi]) => lo+(hi-lo)*random()));
    const scores = pool.map(measure);
    let leader = scores.indexOf(Math.max(...scores));
    for (let generation = 0; generation < 85; generation++) {
      for (let i = 0; i < pool.length; i++) {
        const first = pool[Math.floor(random()*pool.length)];
        const second = pool[Math.floor(random()*pool.length)];
        const step = .5+.5*random(), required = Math.floor(random()*bounds.length);
        const candidate = pool[i].map((old, axis) => {
          if (random() > .80 && axis !== required) return old;
          const value = pool[leader][axis] + step*(first[axis]-second[axis]);
          const [lo,hi] = bounds[axis];
          return value < lo || value > hi ? lo+random()*(hi-lo) : value;
        });
        const score = measure(candidate);
        if (score > scores[i]) {
          scores[i] = score;
          pool[i] = candidate;
          if (score > scores[leader]) leader = i;
        }
      }
    }
    if (!best || scores[leader] > best.rank) {
      const region = points(pool[leader]);
      const proof = orangeHeadingProbe(data,width,height,4,region,source,scratch,true);
      if (proof) best = {...proof, rank:scores[leader], quad:region};
    }
  }
  if (!best?.verified) return false;
  const x = best.quad.reduce((sum,p) => sum+p[0]/width,0)/4;
  const y = best.quad.reduce((sum,p) => sum+p[1]/height,0)/4;
  return Math.abs(x-.5) < .34 && Math.abs(y-.5) < .40;
}

function verifiedOrangeTitle(own, rgba, front, patches) {
  const corners = front.quad.flatMap(([x,y]) => [x*rgba.cols,y*rgba.rows]);
  const mat = flat => own(cv.matFromArray(4,1,cv.CV_32FC2,flat));
  const transform = own(cv.getPerspectiveTransform(mat(corners),mat([0,0, 96,0, 96,240, 0,240])));
  const aligned = own(new cv.Mat()), grey = own(new cv.Mat());
  cv.warpPerspective(rgba,aligned,transform,new cv.Size(96,240));
  cv.cvtColor(aligned,grey,cv.COLOR_RGBA2GRAY);
  for (const patch of patches) {
    const [x,y,right,bottom] = patch.box;
    const crop = own(grey.roi(new cv.Rect(x,y,right-x,bottom-y)));
    const reduced = own(new cv.Mat()), pixels = own(new cv.Mat()), smooth = own(new cv.Mat());
    cv.resize(crop,reduced,new cv.Size(28,9),0,0,cv.INTER_AREA);
    reduced.convertTo(pixels,cv.CV_32F);
    cv.GaussianBlur(pixels,smooth,new cv.Size(0,0),1.5);
    cv.subtract(pixels,smooth,pixels);
    const reference = Int8Array.from(atob(patch.pattern), c => c.charCodeAt(0));
    const actual = pixels.data32F;
    let dot = 0, norm = 0, referenceNorm = 0;
    for (let i = 0; i < reference.length; i++) {
      dot += actual[i]*reference[i];
      norm += actual[i]**2;
      referenceNorm += reference[i]**2;
    }
    if (dot/Math.sqrt(Math.max(1,norm*referenceNorm)) < .75) return false;
  }
  return true;
}

async function readOrangeNutrition(rgba, matcher, registry, footprint) {
  const [sides, parts] = await Promise.all(['orange-side','orange-nutrition'].map(async name => {
    const response = await fetch('../../data/'+name+'.json');
    if (!response.ok) throw Error('Orange evidence unavailable');
    return response.json();
  }));
  if (sides.version !== 1 || parts.version !== 1) throw Error('Unknown orange gallery');
  const templates = sides.templates.filter(template => template.view === 'front');
  const best = scoped(own => {
    const poses = [];
    const focus = footprint && own(cv.matFromArray(4,1,cv.CV_32FC2,footprint.flat()));
    for (const size of [620,720]) {
      const original = extract(own,rgba,size,1);
      for (const angle of [null,-30,30,-60,60]) {
        scoped(inner => {
          const query = angle === null ? original : affineQuery(inner,original.frame,angle);
          if (query.points.length < 18) return;
          for (const template of templates) {
            const pose = scoped(local => orangeFace(local,template,query,matcher,.28));
            if (!pose || pose.inliers < 24 || !parts.fronts[pose.source]) continue;
            const center = pose.quad.reduce((p,[x,y]) => [p[0]+x/4,p[1]+y/4],[0,0]);
            if (focus && cv.pointPolygonTest(focus,new cv.Point(...center),true) < -.035) continue;
            if (scoped(local => verifiedOrangeTitle(local,rgba,pose,parts.fronts[pose.source]))) poses.push(pose);
          }
        });
      }
    }
    return poses.sort((a,b) => b.inliers-a.inliers)[0];
  });
  if (!best || !registry[best.gtin] || !orangeHeadingSearch(rgba,best,orangeHeaderTemplate(parts.header))) return null;
  return {product:registry[best.gtin], gtin:best.gtin, view:'orange-nutrition-heading', inliers:best.inliers};
}
