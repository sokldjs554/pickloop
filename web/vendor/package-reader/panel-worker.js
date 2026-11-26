// Disposable classic worker. OpenCV's pinned browser distribution uses importScripts.
importScripts('opencv.js', 'oblique-ean.js', 'subpixel-ean.js', 'printed-regions.js', 'split-collar.js', 'orange-side.js', 'orange-nutrition.js', 'orange-values.js', 'orange-rear.js','outside-family.js');

function loadRuntime() {
  // OpenCV 4.10 exposes a self-resolving thenable. Resolve without returning it.
  return new Promise(resolve => cv.then(() => resolve()));
}

function extract(own, rgba, size, stretch) {
  const scale = size / Math.max(rgba.rows, rgba.cols);
  const frame = own(new cv.Mat());
  cv.resize(rgba, frame, new cv.Size(Math.max(1, Math.round(rgba.cols * scale * stretch)),
    Math.max(1, Math.round(rgba.rows * scale))), 0, 0, scale < 1 ? cv.INTER_AREA : cv.INTER_LINEAR);
  return features(own, frame);
}

function features(own, frame) {
  const gray = own(new cv.Mat());
  cv.cvtColor(frame, gray, cv.COLOR_RGBA2GRAY);
  const orb = own(new cv.ORB());
  orb.setMaxFeatures(1800);
  orb.setEdgeThreshold(9);
  orb.setFastThreshold(8);
  const keys = own(new cv.KeyPointVector()), descriptors = own(new cv.Mat());
  orb.detectAndCompute(gray, own(new cv.Mat()), keys, descriptors);
  const points = Array.from({length: keys.size()}, (_, i) => {
    const {x, y} = keys.get(i).pt;
    return [x, y];
  });
  return {points, descriptors, frame, width: frame.cols, height: frame.rows};
}

function area(points) {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const [x, y] = points[i], next = points[(i + 1) % points.length];
    sum += x * next[1] - y * next[0];
  }
  return sum / 2;
}

function visibleArea(quad, width, height) {
  let vertices = quad;
  for (const [axis, limit, direction] of [[0, 0, 1], [1, 0, 1], [0, width, -1], [1, height, -1]]) {
    const next = [];
    for (let i = 0; i < vertices.length; i++) {
      const a = vertices[i], b = vertices[(i + 1) % vertices.length];
      const insideA = (a[axis] - limit) * direction >= 0;
      const insideB = (b[axis] - limit) * direction >= 0;
      if (insideA) next.push(a);
      if (insideA !== insideB) {
        const t = (limit - a[axis]) / (b[axis] - a[axis]);
        next.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]);
      }
    }
    vertices = next;
  }
  return area(vertices);
}

function hullArea(points) {
  const sorted = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  function half(sequence) {
    const hull = [];
    for (const p of sequence) {
      while (hull.length >= 2) {
        const a = hull[hull.length - 2], b = hull[hull.length - 1];
        if ((b[0] - a[0]) * (p[1] - a[1]) > (b[1] - a[1]) * (p[0] - a[0])) break;
        hull.pop();
      }
      hull.push(p);
    }
    hull.pop();
    return hull;
  }
  const lower = half(sorted);
  return Math.abs(area([...lower, ...half(sorted.reverse())]));
}

function correspondences(own, reference, query, matcher, ratio = .79, maxDistance = 64) {
  const bytes = Uint8Array.from(atob(reference.descriptors), c => c.charCodeAt(0));
  const features = own(cv.matFromArray(reference.points.length, 32, cv.CV_8U, bytes));
  const nearest = own(new cv.DMatchVectorVector());
  matcher.knnMatch(features, query.descriptors, nearest, 2);
  const unique = new Map();
  for (let i = 0; i < nearest.size(); i++) {
    const neighbors = nearest.get(i);
    if (neighbors.size() === 2) {
      const best = neighbors.get(0), second = neighbors.get(1);
      if (best.distance < ratio * second.distance && best.distance <= maxDistance &&
          (!unique.has(best.trainIdx) || best.distance < unique.get(best.trainIdx).distance)) {
        unique.set(best.trainIdx, {source: i, target: best.trainIdx, distance: best.distance});
      }
    }
    neighbors.delete();
  }
  return Array.from(unique.values()).sort((a, b) => a.distance - b.distance || a.source - b.source);
}

function frontSimilarity(own, contour, frame, artwork) {
  const rectangle = own(cv.matFromArray(4, 1, cv.CV_32FC2, [0,0, 47,0, 47,127, 0,127]));
  const transform = own(cv.getPerspectiveTransform(contour, rectangle));
  const aligned = own(new cv.Mat()), colors = own(new cv.Mat());
  cv.warpPerspective(frame, aligned, transform, new cv.Size(48, 128));
  cv.resize(aligned, colors, new cv.Size(12, 32), 0, 0, cv.INTER_AREA);
  function vector(pixels, channels) {
    const gray = [], chroma = [];
    for (let y = 16; y < 31; y++) {
      for (let x = 1; x < 11; x++) {
        const i = channels * (y * 12 + x);
        const r = pixels[i], g = pixels[i+1], b = pixels[i+2];
        const luminance = .299*r + .587*g + .114*b;
        gray.push(luminance);
        chroma.push(r - luminance, g - luminance, b - luminance);
      }
    }
    const average = gray.reduce((sum, value) => sum + value, 0) / gray.length;
    return gray.map(v => v - average).concat(chroma);
  }
  const reference = vector(Uint8Array.from(atob(artwork), c => c.charCodeAt(0)), 3);
  const observed = vector(colors.data, 4);
  const dot = (a, b) => a.reduce((sum, v, i) => sum + v * b[i], 0);
  return dot(reference, observed) / Math.max(1, Math.sqrt(dot(reference, reference) * dot(observed, observed)));
}

// This enrolled front shares fruit and brand artwork with other markets.
const FRONT_IDENTITY_BANDS = {'ARLA-55f09abff8b47d20': [.365, .400]};

function frontIdentityEvidence(reference, inliers) {
  const band = FRONT_IDENTITY_BANDS[reference.id];
  if (!band) return true;
  const [top, bottom] = band;
  const letters = inliers.filter(([x, y]) => x > .05 * reference.width && x < .95 * reference.width
    && y > top * reference.height && y < bottom * reference.height).map(([x]) => x);
  return letters.length >= 4 && Math.max(...letters) - Math.min(...letters) >= .25 * reference.width;
}

function assess(own, reference, query, matcher) {
  const pairs = correspondences(own, reference, query, matcher);
  if (pairs.length < 12) return null;
  const original = pairs.map(pair => reference.points[pair.source]);
  const seen = pairs.map(pair => query.points[pair.target]);
  const src = own(cv.matFromArray(pairs.length, 1, cv.CV_32FC2, original.flat()));
  const dst = own(cv.matFromArray(pairs.length, 1, cv.CV_32FC2, seen.flat()));
  const mask = own(new cv.Mat());
  const matrix = own(cv.findHomography(src, dst, cv.RANSAC, 3, mask, 700, .995));
  if (matrix.empty()) return null;
  const h = matrix.data64F;
  const corners = [[0,0], [reference.width,0], [reference.width,reference.height], [0,reference.height]].map(([x,y]) => {
    const w = h[6]*x + h[7]*y + h[8];
    return [(h[0]*x+h[1]*y+h[2])/w, (h[3]*x+h[4]*y+h[5])/w];
  });
  const projected = area(corners);
  const frameArea = query.width * query.height;
  if (!Number.isFinite(projected) || projected < .012 * frameArea || projected > 2.2 * frameArea) return null;
  const contour = own(cv.matFromArray(4, 1, cv.CV_32FC2, corners.flat()));
  if (!cv.isContourConvex(contour) || visibleArea(corners, query.width, query.height) < .67 * projected) return null;
  const keep = original.filter((_, i) => mask.data[i]);
  if (keep.length < 12 || keep.length < pairs.length * .32) return null;
  const cover = Math.min(hullArea(keep) / (reference.width * reference.height),
    hullArea(seen.filter((_, i) => mask.data[i])) / projected);
  if (cover < .07) return null;
  const votes = reference.zones.map(([x0, y0, x1, y1]) =>
    keep.filter(([x, y]) => x >= x0 && x <= x1 && y >= y0 && y <= y1).length);
  let score = keep.length * Math.sqrt(cover), appearance = null;
  if (reference.view === 'front') {
    appearance = frontSimilarity(own, contour, query.frame, reference.appearance);
    score = Math.sqrt(score) * Math.max(0, appearance) ** 5;
  }
  // A shelf can contain a perfectly matching carton behind the subject. Measure the
  // distance in original frame proportions, also when matching a widened query.
  const normalized = corners.map(([x, y]) => [x / query.width, y / query.height]);
  const face = own(cv.matFromArray(4, 1, cv.CV_32FC2, normalized.flat()));
  const centerDistance = cv.pointPolygonTest(face, new cv.Point(.5, .5), true);
  return {reference, corners, gtin: reference.gtin, view: reference.view, inliers: keep.length,
    votes, cover, score, appearance, centerDistance, footprint: normalized, areaFraction: projected / frameArea,
    hasIdentityText: frontIdentityEvidence(reference, keep)};
}

// Rectification can expose fine lettering on foreshortened panels. Require an
// independent ORB detection in the rectified pixels and a second homography
// that projects the reference corners back near the same four locations.
function refine(own, candidate, frame, matcher) {
  const {reference, corners} = candidate;
  const {width, height} = reference;
  const rectangle = [[0, 0], [width, 0], [width, height], [0, height]];
  const from = own(cv.matFromArray(4, 1, cv.CV_32FC2, corners.flat()));
  const to = own(cv.matFromArray(4, 1, cv.CV_32FC2, rectangle.flat()));
  const transform = own(cv.getPerspectiveTransform(from, to));
  const aligned = own(new cv.Mat());
  cv.warpPerspective(frame, aligned, transform, new cv.Size(width, height));
  const query = features(own, aligned);
  if (query.points.length < 12) return null;
  const result = assess(own, reference, query, matcher);
  if (!result || result.corners.some(([x, y], i) =>
    Math.hypot(x - rectangle[i][0], y - rectangle[i][1]) > .12 * Math.max(width, height))) return null;
  return {...result, centerDistance: candidate.centerDistance, footprint: candidate.footprint,
    areaFraction: candidate.areaFraction};
}

function scoped(run) {
  const allocations = [];
  try {
    return run(value => { allocations.push(value); return value; });
  } finally {
    for (const value of allocations.reverse()) value.delete();
  }
}

// These variants use the same orange title and squeezed-fruit styling.
// A near-tie on the same physical face needs evidence separate from the artwork.
const SHARED_ORANGE_FRONT_GTINS = new Set(['7310860007372', '6415130050490', '7310865074768']);
const FRONT_APPEARANCE_UNCERTAINTY = .01;

function hasSharedMarketRival(best, seen) {
  if (best.view !== 'front' || !best.footprint || !SHARED_ORANGE_FRONT_GTINS.has(best.gtin)) return false;
  const [first, , opposite] = best.footprint;
  const diagonal = Math.hypot(first[0] - opposite[0], first[1] - opposite[1]);
  return seen.some(hit => hit.gtin !== best.gtin && SHARED_ORANGE_FRONT_GTINS.has(hit.gtin)
    && hit.view === 'front' && hit.footprint && hit.inliers >= 17 && hit.votes[0] >= 4 && hit.score >= 2.8
    && hit.appearance >= Math.max(.88, best.appearance - FRONT_APPEARANCE_UNCERTAINTY)
    && best.footprint.every(([x, y], i) => Math.hypot(x - hit.footprint[i][0], y - hit.footprint[i][1])
      < .20 * diagonal));
}

function panelDecision(seen, registry, recovery = false) {
  seen.sort((a, b) => b.score - a.score);
  const best = seen[0], other = best && seen.find(r => r.gtin !== best.gtin);
  const product = best && registry[best.gtin];
  if (!best) return null;
  const enrolled = name => Boolean(name && !name.endsWith('250ml'));
  const rival = other?.score || 0;
  const supported = best.view === 'front'
    ? best.hasIdentityText !== false && best.inliers >= 17 && best.votes[0] >= 4 &&
      best.appearance >= .88 && best.score >= Math.max(2.8, 1.38 * rival)
    : Math.min(...best.votes) >= 3 && best.cover >= .16 && best.score >= Math.max(14, 1.45 * rival);
  if (supported && enrolled(product)) {
    const peripheral = best.centerDistance < -.25 || (best.centerDistance < -.12 && best.areaFraction < .10);
    if (peripheral || (recovery && (best.centerDistance < -.12 || best.areaFraction < .04 ||
      (best.view === 'front' && best.votes[1] < 2)))) return {status: 'off_center'};
  }
  if (supported && enrolled(product) && hasSharedMarketRival(best, seen)) {
    return {status: 'market_unverified', footprint: best.footprint, marketCandidate: product};
  }
  if (supported) return enrolled(product)
    ? {product, view: best.view, inliers: best.inliers}
    : {status: 'incompatible'};
  if (best.view === 'front' && best.score >= 2.8 && seen.some(hit =>
    !enrolled(registry[hit.gtin]) && hit.score >= .65 * best.score)) {
    return {status: 'ambiguous', footprint: best.footprint};
  }
  return null;
}

// Use a blurred side barcode only to distinguish visually competing foreground packs.
// In face coordinates allow the near quarter-width of an adjacent side, not the next carton.
function barcodeOnPack(own, footprint, center) {
  const points = coords => own(cv.matFromArray(coords.length, 1, cv.CV_32FC2, coords.flat()));
  const face = points(footprint);
  const unit = points([[0,0],[1,0],[1,1],[0,1]]);
  const transform = own(cv.getPerspectiveTransform(face, unit));
  const output = own(new cv.Mat());
  cv.perspectiveTransform(points([center]), output, transform);
  const [u, v] = output.data32F;
  return u >= -.25 && u <= 1.25 && v >= 0 && v <= 1;
}

async function readSideEvidence(rgba, matcher, registry, footprint) {
  const printed = await readPrintedRegions(rgba, matcher, registry, footprint);
  if (printed && printed.view !== 'split-fruit-collar') return printed;
  const orange = await readOrangeSide(rgba, matcher, registry, footprint) ||
    await readOrangeNutrition(rgba, matcher, registry, footprint);
  if (printed && orange && printed.product !== orange.product) return {status: 'ambiguous'};
  return printed || orange;
}

async function resolveAmbiguousPanel(rgba, matcher, registry, gallery, seen, decision) {
  const printed = await readSideEvidence(rgba, matcher, registry, decision.footprint);
  if (printed) return printed.product ? printed : decision;
  const faces = seen.filter(hit => hit.view === 'front' && registry[hit.gtin] &&
    !registry[hit.gtin].endsWith('250ml') && hit.score >= .65 * seen[0].score &&
    hit.centerDistance >= -.12 && hit.areaFraction >= .04);
  if (!faces.length) return decision;
  return scoped(own => {
    const gray = own(new cv.Mat());
    cv.cvtColor(rgba, gray, cv.COLOR_RGBA2GRAY);
    const codes = [...new Set(gallery.templates.map(t => t.gtin).filter(code => /^\d{13}$/.test(code)))];
    const scans = readSubpixelEAN(gray.data, gray.cols, gray.rows, codes);
    if (new Set(scans.map(s => s.gtin)).size !== 1) return decision;
    const hit = scans.find(scan => faces.some(face => face.gtin === scan.gtin &&
      barcodeOnPack(own, face.footprint, scan.center)));
    return hit ? {product: registry[hit.gtin], view: 'side-ean-bands', gtin: hit.gtin,
      scanBands: 2} : decision;
  });
}

async function readPanel(image) {
  const [galleryResponse, registryResponse] = await Promise.all([
    fetch('../../data/registered-pack-gallery.json'), fetch('registry.json'), loadRuntime(),
  ]);
  if (!galleryResponse.ok || !registryResponse.ok) throw Error('Gallery unavailable');
  const [gallery, registry] = await Promise.all([galleryResponse.json(), registryResponse.json()]);
  if (gallery.version !== 1) throw Error('Unknown gallery format');
  const bitmap = await createImageBitmap(image);
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  const allocations = [];
  const own = value => { allocations.push(value); return value; };
  try {
    const rgba = own(cv.matFromImageData(ctx.getImageData(0, 0, canvas.width, canvas.height)));
    canvas.width = canvas.height = 1;
    cv.setRNGSeed(441);
    const matcher = own(new cv.BFMatcher(cv.NORM_HAMMING, false));
    const seen = [];
    for (const [size, stretch] of [[720, 1], [490, 1.7], [490, 1]]) {
      const query = extract(own, rgba, size, stretch);
      if (query.points.length < 12) continue;
      const candidates = gallery.templates.map(template => scoped(local => assess(local, template, query, matcher)))
        .filter(Boolean);
      seen.push(...candidates);
      if (size === 720) {
        const first = panelDecision(seen, registry);
        if (first?.status === 'off_center') return await readSideEvidence(rgba, matcher, registry);
        if (['ambiguous', 'market_unverified'].includes(first?.status)) {
          return await annotateOutsideCapacity(rgba, matcher, await resolveAmbiguousPanel(rgba, matcher, registry, gallery, seen, first));
        }
        if (first?.status === 'incompatible') return await resolveSharedOrangeFront(rgba, matcher, registry, seen, first);
        if (first) return first;
      }
      for (const candidate of candidates) {
        if (candidate.centerDistance < -.12 || candidate.areaFraction < .04) continue;
        const hit = scoped(local => refine(local, candidate, query.frame, matcher));
        if (hit) seen.push(hit);
      }
    }
    const decision = panelDecision(seen, registry, true);
    if (['ambiguous', 'market_unverified'].includes(decision?.status)) {
      return await annotateOutsideCapacity(rgba, matcher, await resolveAmbiguousPanel(rgba, matcher, registry, gallery, seen, decision));
    }
    if (decision?.status === 'incompatible') return await resolveSharedOrangeFront(rgba, matcher, registry, seen, decision);
    if (decision && decision.status !== 'off_center') return decision;
    // An identified background pack cannot identify the foreground object. A separate
    // lettering match must place the full set of distinguishing regions near the center.
    const printed = await readSideEvidence(rgba, matcher, registry);
    if (decision?.status === 'off_center' || printed?.status) return printed;
    const gray = own(new cv.Mat());
    cv.cvtColor(rgba, gray, cv.COLOR_RGBA2GRAY);
    const scans = readObliqueEAN(gray.data, gray.cols, gray.rows, Object.keys(registry));
    if (!scans.length) return printed || await readOrangeRear(rgba, registry) || await readOutsideFamily(rgba, matcher);
    const {gtin, scanLines} = scans[0];
    if (scans.length > 1 || (printed && printed.product !== registry[gtin])) {
      return {status: 'ambiguous'};
    }
    if (registry[gtin].endsWith('250ml')) return {status: 'incompatible'};
    return {product: registry[gtin], view: 'oblique-ean', gtin, scanLines};
  } finally {
    for (const mat of allocations.reverse()) mat.delete();
  }
}
self.onmessage = async ({data}) => {
  try {
    self.postMessage({status: 'resolve', data: await readPanel(data.payload.image)});
  } catch {
    self.postMessage({status: 'reject'});
  }
};
