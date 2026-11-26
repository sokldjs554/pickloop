// A mixed citrus collar has a dark seam between two differently coloured wedges.
// The cap above and the dark carton below are part of the registered pattern.
const COLLAR_SAMPLE_POINTS = {
  cap: [[-.38, -.35], [0, -.35], [.38, -.35]],
  seam: [[0, .29], [0, .50], [0, .73]],
  yellow: [[-.47, .24], [-.77, .24], [-.47, .43], [-.77, .43]],
  pink: [[.47, .24], [.77, .24], [.47, .43], [.77, .43]],
  carton: [[-.4, 1.38], [.4, 1.38]],
};
const COLLAR_GRID = Array.from({length: 143}, (_, i) => [
  -1.2 + 2.4 * (i % 13) / 12, -.55 + 1.87 * Math.floor(i / 13) / 10,
]);

function collarLuminance(red, green, blue) {
  return (red + 2 * green + blue) / 4;
}

function normalizedCollarGrid(values) {
  let mean = 0, sumSquares = 0;
  for (const value of values) mean += value / values.length;
  for (const value of values) sumSquares += (value - mean) ** 2;
  const scale = 1 / Math.max(.01, Math.sqrt(sumSquares));
  return values.map(value => (value - mean) * scale);
}

// A rotating, sloping carton projects the seam and its tangent to different axes.
// Integer offsets support a fast rough search. Bilinear taps preserve subpixel evidence.
function collarSampler(width, length, angle, across = 1, skew = 0, subpixel = null) {
  const radians = angle * Math.PI / 180;
  const dx = length * Math.sin(radians), dy = length * Math.cos(radians);
  function offset([u, v]) {
    const a = (dy * across + dx * skew) * u + dx * v;
    const b = (-dx * across + dy * skew) * u + dy * v;
    if (!subpixel) return Math.round(a) + width * Math.round(b);
    const x = a + subpixel[0], y = b + subpixel[1];
    const ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy;
    return [ix + width * iy, (1-fx)*(1-fy), fx*(1-fy), (1-fx)*fy, fx*fy];
  }
  const groups = Object.fromEntries(Object.entries(COLLAR_SAMPLE_POINTS)
    .map(([name, points]) => [name, points.map(offset)]));
  return {groups, grid: COLLAR_GRID.map(offset), interpolated: !!subpixel};
}

function scoreCollar(rgb, width, height, x, y, sampling, references) {
  const center = x + width*y, {groups, grid, interpolated} = sampling;
  function pixel(tap, channel) {
    if (!interpolated) return rgb[3*(center + tap) + channel];
    const [offset, w00, w10, w01, w11] = tap, start = 3*(center + offset) + channel;
    return w00*rgb[start] + w10*rgb[start+3] +
      w01*rgb[start+3*width] + w11*rgb[start+3*width+3];
  }
  if (pixel(groups.cap[1], 1) < pixel(groups.seam[1], 1) + 35 ||
      pixel(groups.yellow[0], 1) < pixel(groups.seam[1], 1) + 32 ||
      pixel(groups.pink[0], 0) < pixel(groups.seam[1], 0) + 23) return null;

  function meanColor(group) {
    return [0, 1, 2].map(channel =>
      group.reduce((sum, tap) => sum + pixel(tap, channel), 0) / group.length);
  }
  const cap = meanColor(groups.cap), seam = meanColor(groups.seam);
  const yellow = meanColor(groups.yellow), pink = meanColor(groups.pink), carton = meanColor(groups.carton);
  const chroma = ([red,,blue]) => (red-blue)/Math.max(1, red);
  const hue = ([red,green,blue]) => (green-blue)/Math.max(1, red-blue);
  if (collarLuminance(...seam) > .70 * Math.min(...[cap, yellow, pink].map(c => collarLuminance(...c))) ||
      collarLuminance(...carton) > .67 * Math.min(collarLuminance(...cap), collarLuminance(...pink)) ||
      chroma(cap) > .45 || chroma(yellow) < .47 || chroma(pink) < .30 ||
      hue(yellow) < .62 || hue(pink) > .58 || hue(yellow)-hue(pink) < .155) return null;

  const observed = normalizedCollarGrid(grid.map(tap => collarLuminance(pixel(tap,0), pixel(tap,1), pixel(tap,2))));
  const scores = references.map(ref => ref.reduce((sum, value, i) => sum + value * observed[i], 0));
  scores.sort((a,b) => b-a);
  return {first: scores[0], second: scores[1]};
}

function matchSplitCollar(rgb, width, height, enrollments) {
  if (!width || !height || rgb.length !== 3*width*height || enrollments.length < 2 ||
      new Set(enrollments.map(item => item.sha256)).size !== enrollments.length) return null;
  const references = enrollments.map(item => normalizedCollarGrid(item.grid));
  let best = null;
  const candidates = new Map();
  for (const length of [6,8,10,12,15,18,22,27]) {
    const border = Math.ceil(length*2);
    for (let angle = -80; angle <= 80; angle += 10) {
      const sampler = collarSampler(width, length, angle);
      for (let y = border; y < height-border; y += 2) {
        for (let x = border; x < width-border; x += 2) {
          const scores = scoreCollar(rgb, width, height, x, y, sampler, references);
          if (!scores) continue;
          const pose = {...scores, x, y, length, angle, across: 1, skew: 0};
          if (!best || pose.second > best.second) best = pose;
          const key = Math.floor(x/8) + ':' + Math.floor(y/8);
          if (pose.second > .72 && (!candidates.has(key) || pose.second > candidates.get(key).second)) {
            candidates.set(key, pose);
          }
        }
      }
    }
  }

  const peaks = [...candidates.values()].sort((a,b) => b.second-a.second).slice(0,8);
  function inside(x, y, length, across, skew) {
    // All grid and colour taps lie inside this conservative rotated bounding circle.
    const border = Math.ceil(length*Math.hypot(1.2*across, 1.38 + 1.2*Math.abs(skew)))+1;
    return x >= border && y >= border && x < width-border && y < height-border;
  }
  for (const peak of peaks) {
    for (const scale of [.8,1,1.2]) for (const shift of [-10,0,10]) {
      const length = peak.length*scale, angle = peak.angle+shift;
      for (const across of [.66,.85,1,1.24,1.50]) for (const skew of [-.60,-.30,0,.30,.60]) {
        const sampler = collarSampler(width, length, angle, across, skew);
        for (const ox of [-1,0,1]) for (const oy of [-1,0,1]) {
          const x = peak.x+ox, y = peak.y+oy;
          if (!inside(x,y,length,across,skew)) continue;
          const scores = scoreCollar(rgb,width,height,x,y,sampler,references);
          if (scores && scores.second > best.second) best = {...scores,x,y,length,angle,across,skew};
        }
      }
    }
  }

  // Registration also samples at fractional pixel positions. Refine the best geometric
  // proposal with the same interpolation and maximize the weaker of two source matches.
  if (!best || best.second <= .78) return best;
  const steps = {x:1, y:1, length:1.2, angle:5, across:.10, skew:.12};
  function evaluate(pose) {
    const {x,y,length,angle,across,skew} = pose;
    if (across < .40 || across > 1.9 || Math.abs(skew) > 1.1 || !inside(x,y,length,across,skew)) return null;
    const ix = Math.floor(x), iy = Math.floor(y);
    const sampler = collarSampler(width,length,angle,across,skew,[x-ix,y-iy]);
    const scores = scoreCollar(rgb,width,height,ix,iy,sampler,references);
    return scores && {...pose,...scores};
  }
  function refine(seed) {
    let refined = evaluate(seed);
    for (const fraction of [1,.5,.25]) for (let round = 0; round < 3; round++) {
      for (const [key, step] of Object.entries(steps)) {
        const base = refined || seed;
        let next = refined;
        for (const sign of [-1,1]) {
          const proposal = evaluate({...base, [key]: base[key]+sign*step*fraction});
          if (proposal && (!next || proposal.second > next.second)) next = proposal;
        }
        refined = next;
      }
    }
    return refined && refined.second > seed.second ? refined : seed;
  }
  const primary = refine(best);
  if (primary.second >= .88 || primary.second < .84) return primary;

  // A tilted seam can move sideways as its projected width or angle changes.
  // Rescore a small joint neighbourhood on the same pixels, using both source matches.
  let strongest = primary;
  for (const dx of [-2, -1, 0, 1, 2]) for (const dy of [-1, -.5, 0, .5, 1]) {
    for (const dWidth of [-.25, 0, .25]) for (const dSkew of [-.3, 0, .3]) {
      for (const dLength of [-2.4, 0, 2.4]) for (const dAngle of [-5, 0, 5]) {
        const candidate = evaluate({
          x: primary.x + dx, y: primary.y + dy,
          across: primary.across + dWidth, skew: primary.skew + dSkew,
          length: primary.length + dLength, angle: primary.angle + dAngle,
        });
        if (candidate && candidate.second > strongest.second) strongest = candidate;
      }
    }
  }
  return strongest === primary ? primary : refine(strongest);
}

// Only the carton whose top meets the detected closure may supply branding evidence.
// All coordinates are in the same resized camera frame.
function collarOnCarton(quad, cap) {
  const midpoint = (a,b) => [(a[0]+b[0])/2, (a[1]+b[1])/2];
  const top = midpoint(quad[0],quad[1]), bottom = midpoint(quad[2],quad[3]);
  const dx = bottom[0]-top[0], dy = bottom[1]-top[1], length = Math.hypot(dx,dy);
  const x = cap[0]-top[0], y = cap[1]-top[1], along = (x*dx+y*dy)/(length*length);
  return length > 0 && Math.hypot(x,y) <= .36*length && along >= -.34 && along <= .12;
}

function findCollarBrand(own, template, query, matcher, cap) {
  const pairs = correspondences(own, template, query, matcher, .83, 70);
  if (pairs.length < 16) return null;
  const matrix = points => own(cv.matFromArray(points.length, 1, cv.CV_32FC2, points.flat()));
  const mask = own(new cv.Mat());
  const transform = own(cv.findHomography(matrix(pairs.map(p => template.points[p.source])),
    matrix(pairs.map(p => query.points[p.target])), cv.RANSAC, 3.5, mask, 1000, .995));
  if (transform.empty()) return null;
  const inliers = cv.countNonZero(mask);
  if (inliers < 16) return null;
  const w = template.width, h = template.height, projected = own(new cv.Mat());
  cv.perspectiveTransform(matrix([[0,0],[w,0],[w,h],[0,h]]), projected, transform);
  const quad = Array.from({length:4}, (_,i) => [projected.data32F[2*i],projected.data32F[2*i+1]]);
  const surface = area(quad), fraction = surface/(query.width*query.height);
  if (!cv.isContourConvex(projected) || fraction <= .008 || fraction >= 1.7 ||
      visibleArea(quad,query.width,query.height) < .85*surface || !collarOnCarton(quad,cap)) return null;
  const center = [0,1].map(axis => quad.reduce((sum,p) => sum+p[axis],0)/4);
  if (Math.abs(center[0]/query.width-.5) > .29 || Math.abs(center[1]/query.height-.5) > .30) return null;
  const aligned = own(new cv.Mat()), gray = own(new cv.Mat()), padded = own(new cv.Mat());
  cv.warpPerspective(query.frame, aligned, transform, new cv.Size(w,h), cv.INTER_LINEAR | cv.WARP_INVERSE_MAP);
  cv.cvtColor(aligned,gray,cv.COLOR_RGBA2GRAY);
  cv.copyMakeBorder(gray,padded,16,16,16,16,cv.BORDER_REPLICATE);
  const logoScore = printedRegionScore(own,padded,template.details[0]);
  return logoScore >= .70 ? {logoScore,inliers} : null;
}

async function readSplitCollar(rgba, matcher, registry, gallery) {
  const response = await fetch('../../data/registered-collar.json');
  if (!response.ok) return null;
  const enrollment = await response.json();
  if (enrollment.version !== 1 || !registry[enrollment.gtin]) return null;
  return scoped(own => {
    const scale = 348/Math.max(rgba.cols,rgba.rows);
    const width = Math.max(1,Math.round(rgba.cols*scale)), height = Math.max(1,Math.round(rgba.rows*scale));
    const small = own(new cv.Mat()), rgb = own(new cv.Mat()), blurred = own(new cv.Mat());
    cv.resize(rgba,small,new cv.Size(width,height),0,0,scale < 1 ? cv.INTER_AREA : cv.INTER_LINEAR);
    cv.cvtColor(small,rgb,cv.COLOR_RGBA2RGB);
    cv.blur(rgb,blurred,new cv.Size(3,3));
    const collar = matchSplitCollar(blurred.data,width,height,enrollment.references);
    if (!collar || collar.second < .88) return null;

    const zoom = 900/Math.max(rgba.cols,rgba.rows), frame = own(new cv.Mat());
    cv.resize(rgba,frame,new cv.Size(Math.round(rgba.cols*zoom),Math.round(rgba.rows*zoom)),
      0,0,zoom < 1 ? cv.INTER_AREA : cv.INTER_LINEAR);
    const cap = [collar.x*frame.cols/width,collar.y*frame.rows/height];
    const templates = gallery.templates.filter(t => t.gtin === enrollment.gtin && enrollment.logoSources.includes(t.sourceHash));
    for (const tilt of [2,3]) for (const angle of [-45,-30,-15,0,15,30,45]) {
      const logo = scoped(local => {
        const query = affineQuery(local,frame,angle,tilt);
        for (const template of templates) {
          const hit = scoped(inner => findCollarBrand(inner,template,query,matcher,cap));
          if (hit) return hit;
        }
      });
      if (logo) return {product:registry[enrollment.gtin],view:'split-fruit-collar',...logo,
        collarScores:[collar.first,collar.second]};
    }
    return null;
  });
}
