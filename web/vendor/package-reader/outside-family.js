// A positive statement about an unregistered family. It never supplies a product or GTIN.
function outsideFamilyMarks(points, boxes) {
  return boxes.every(([x, y, right, bottom]) => {
    const xs = points.filter(([u, v]) => u >= x && u <= right && v >= y && v <= bottom).map((p) => p[0]);
    return xs.length >= 3 && Math.max(...xs) - Math.min(...xs) >= 0.3 * (right - x);
  });
}

function familyFeatures(own, frame, size) {
  const k = size / Math.max(frame.cols, frame.rows);
  const scaled = own(new cv.Mat()),
    gray = own(new cv.Mat());
  cv.resize(
    frame,
    scaled,
    new cv.Size(Math.max(1, Math.round(frame.cols * k)), Math.max(1, Math.round(frame.rows * k))),
    0,
    0,
    k < 1 ? cv.INTER_AREA : cv.INTER_LINEAR
  );
  cv.cvtColor(scaled, gray, cv.COLOR_RGBA2GRAY);
  const orb = own(new cv.ORB()),
    keys = own(new cv.KeyPointVector()),
    descriptors = own(new cv.Mat());
  orb.setMaxFeatures(2400);
  orb.setEdgeThreshold(9);
  orb.setFastThreshold(8);
  orb.detectAndCompute(gray, own(new cv.Mat()), keys, descriptors);
  const points = Array.from({length: keys.size()}, (_, i) => {
    const {x, y} = keys.get(i).pt;
    return [x, y];
  });
  return {gray, points, descriptors, width: gray.cols, height: gray.rows};
}

function outsideFamilyPairs(own, reference, query, matcher) {
  const neighbors = own(new cv.DMatchVectorVector()),
    unique = new Map();
  if (reference.points.length < 2 || query.points.length < 2) return [];
  matcher.knnMatch(reference.descriptors, query.descriptors, neighbors, 2);
  for (let i = 0; i < neighbors.size(); i++) {
    const v = neighbors.get(i);
    if (v.size() === 2) {
      const a = v.get(0),
        b = v.get(1),
        old = unique.get(a.trainIdx);
      if (a.distance < 0.79 * b.distance && a.distance <= 64 && (!old || a.distance < old.distance)) {
        unique.set(a.trainIdx, {source: i, target: a.trainIdx, distance: a.distance});
      }
    }
    v.delete();
  }
  return Array.from(unique.values());
}

function familyPose(own, reference, query, matcher) {
  const pairs = outsideFamilyPairs(own, reference, query, matcher);
  if (pairs.length < 12) return null;
  const pts = (arr) => own(cv.matFromArray(arr.length, 1, cv.CV_32FC2, arr.flat()));
  const a = pairs.map((p) => reference.points[p.source]),
    b = pairs.map((p) => query.points[p.target]);
  const mask = own(new cv.Mat());
  const hom = own(cv.findHomography(pts(a), pts(b), cv.RANSAC, 3.5, mask, 1000, 0.995));
  if (hom.empty() || cv.countNonZero(mask) < 12) return null;
  return {hom, points: a.filter((_, i) => mask.data[i])};
}

function familySubset(own, obj, keep) {
  const stride = obj.descriptors.cols;
  const bytes = new Uint8Array(keep.length * stride);
  keep.forEach((n, i) => bytes.set(obj.descriptors.data.subarray(n * stride, (n + 1) * stride), i * stride));
  return {
    points: keep.map((n) => obj.points[n]),
    descriptors: own(cv.matFromArray(keep.length, stride, cv.CV_8U, bytes))
  };
}

function outsideBandCorrelation(own, gray, patch) {
  const [x, y, r, b] = patch.box,
    [w, h] = patch.size;
  const crop = own(gray.roi(new cv.Rect(x, y, r - x, b - y)));
  const small = own(new cv.Mat()),
    contrast = own(new cv.Mat()),
    blur = own(new cv.Mat());
  cv.resize(crop, small, new cv.Size(w, h), 0, 0, cv.INTER_AREA);
  small.convertTo(contrast, cv.CV_32F);
  cv.GaussianBlur(contrast, blur, new cv.Size(0, 0), 2);
  cv.subtract(contrast, blur, contrast);
  const expected = Int8Array.from(atob(patch.contrast), (c) => c.charCodeAt(0));
  let dot = 0,
    actualNorm = 0,
    expectedNorm = 0;
  for (let i = 0; i < expected.length; i++) {
    const actual = contrast.data32F[i],
      ref = expected[i];
    dot += actual * ref;
    actualNorm += actual * actual;
    expectedNorm += ref * ref;
  }
  return dot / Math.max(1, Math.sqrt(actualNorm * expectedNorm));
}

function outsideFamilyEvidence(own, template, query, matcher) {
  const bytes = Uint8Array.from(atob(template.descriptors), (c) => c.charCodeAt(0));
  const ref = {
    points: template.points,
    descriptors: own(cv.matFromArray(template.points.length, 32, cv.CV_8U, bytes))
  };
  const fitted = familyPose(own, ref, query, matcher);
  if (!fitted) return null;
  const sizeReading = template.family === 'Smooth Orange 1.75L';
  const panels = sizeReading ? template.patches.slice(0, 2) : template.patches;
  if (
    !outsideFamilyMarks(
      fitted.points,
      panels.map((p) => p.box)
    )
  )
    return null;
  const h = fitted.hom.data64F;
  const map = ([x, y]) => {
    const z = h[6] * x + h[7] * y + h[8];
    return [(h[0] * x + h[1] * y + h[2]) / z, (h[3] * x + h[4] * y + h[5]) / z];
  };
  const rect = ([x, y, r, b]) =>
    [
      [x, y],
      [r, y],
      [r, b],
      [x, b]
    ].map(map);
  const quad = rect([0, 0, template.width, template.height]);
  const contour = own(cv.matFromArray(4, 1, cv.CV_32FC2, quad.flat()));
  const qw = query.width,
    qh = query.height,
    fraction = area(quad) / (qw * qh);
  if (
    !cv.isContourConvex(contour) ||
    !(fraction > 0.18 && fraction < 2.15) ||
    visibleArea(quad, qw, qh) < 0.66 * area(quad)
  )
    return false;
  const xs = quad.map((p) => p[0]),
    ys = quad.map((p) => p[1]);
  const average = (a) => a.reduce((sum, v) => sum + v, 0) / a.length;
  if (
    Math.abs(average(xs) / qw - 0.5) > 0.17 ||
    Math.abs(average(ys) / qh - 0.5) > 0.24 ||
    Math.max(...xs) - Math.min(...xs) < 0.55 * Math.min(qw, qh)
  )
    return false;
  if (template.patches.some((p) => rect(p.box).some(([x, y]) => !(x >= 0 && x <= qw && y >= 0 && y <= qh))))
    return false;
  const gray = own(new cv.Mat());
  cv.warpPerspective(
    query.gray,
    gray,
    fitted.hom,
    new cv.Size(template.width, template.height),
    cv.INTER_LINEAR | cv.WARP_INVERSE_MAP
  );
  if (panels.some((p) => outsideBandCorrelation(own, gray, p) < 0.6)) return null;
  if (sizeReading) {
    const capacity = template.patches[2];
    const original =
      outsideFamilyMarks(fitted.points, [capacity.box]) && outsideBandCorrelation(own, gray, capacity) >= 0.6;
    if (!original && !familyCapacityGlyphs(own, gray, capacity)) return null;
  }
  const outside = [];
  query.points.forEach(([x, y], i) => {
    if (cv.pointPolygonTest(contour, new cv.Point(x, y), false) < 0) outside.push(i);
  });
  const [x, y, r, b] = template.patches[0].box,
    logo = [];
  ref.points.forEach(([u, v], i) => {
    if (u >= x && u <= r && v >= y && v <= b) logo.push(i);
  });
  if (
    outside.length >= 12 &&
    logo.length >= 12 &&
    familyPose(own, familySubset(own, ref, logo), familySubset(own, query, outside), matcher)
  )
    return false;
  return quad.map(([x, y]) => [x / qw, y / qh]);
}

async function readOutsideFamily(rgba, matcher, ambiguousFace = null) {
  if (rgba.cols > 1.35 * rgba.rows) return null;
  const response = await fetch('../../data/outside-family.json');
  if (!response.ok) throw Error('Outside-family gallery unavailable');
  const {templates} = await response.json(),
    names = new Set();
  for (const size of [640, 1000]) {
    scoped((own) => {
      const query = familyFeatures(own, rgba, size);
      for (const template of templates) {
        if (ambiguousFace && template.family !== 'Smooth Orange 1.75L') continue;
        const face = scoped((o) => outsideFamilyEvidence(o, template, query, matcher));
        if (face && (!ambiguousFace || sameOutsideFace(face, ambiguousFace))) names.add(template.family);
      }
    });
  }
  return names.size === 1 ? {status: 'outside_family', family: Array.from(names)[0]} : null;
}

function familyCapacityGlyphs(own, gray, patch) {
  // A pose fitted mostly to the upper label can drift at the lower seam. Locate
  // the complete lower field in one narrow window, then require the five
  // printed glyphs '1', '.', '7', '5', 'L' in the same rigid displacement.
  const [x, y, right, bottom] = patch.box,
    [w, h] = patch.size;
  const margin = Math.round((bottom - y) * 0.65);
  const left = Math.max(0, x - margin),
    top = Math.max(0, y - margin);
  const endX = Math.min(gray.cols, right + margin),
    endY = Math.min(gray.rows, bottom + margin);
  const region = own(gray.roi(new cv.Rect(left, top, endX - left, endY - top)));
  const nw = Math.round(((endX - left) * w) / (right - x)),
    nh = Math.round(((endY - top) * h) / (bottom - y));
  if (nw < w || nh < h) return false;
  const resized = own(new cv.Mat()),
    actual = own(new cv.Mat()),
    smooth = own(new cv.Mat());
  cv.resize(region, resized, new cv.Size(nw, nh), 0, 0, cv.INTER_AREA);
  resized.convertTo(actual, cv.CV_32F);
  cv.GaussianBlur(actual, smooth, new cv.Size(0, 0), 2);
  cv.subtract(actual, smooth, actual);
  const reference = Int8Array.from(atob(patch.contrast), (c) => c.charCodeAt(0));
  const tpl = own(cv.matFromArray(h, w, cv.CV_32F, reference)),
    result = own(new cv.Mat());
  cv.matchTemplate(actual, tpl, result, cv.TM_CCORR_NORMED);
  const peak = cv.minMaxLoc(result);
  if (peak.maxVal < 0.6) return false;
  return outsideCapacityBands(reference, actual.data32F, w, h, nw, peak.maxLoc.x, peak.maxLoc.y);
}

function outsideCapacityBands(reference, actual, w, h, stride, dx, dy) {
  // Fractions follow the five glyphs in the enrolled Arla capacity field.
  const bands = [
    [0.075, 0.257],
    [0.257, 0.343],
    [0.343, 0.516],
    [0.516, 0.755],
    [0.765, 0.988]
  ];
  return bands.every(([a, b], i) => {
    const left = Math.round(a * w),
      right = Math.round(b * w);
    // The decimal point is on the baseline; empty space above it carries no evidence.
    const top = Math.round((i === 1 ? 0.55 : 0.17) * h),
      bottom = Math.round(0.9 * h);
    let dot = 0,
      normA = 0,
      normB = 0;
    for (let y = top; y < bottom; y++)
      for (let x = left; x < right; x++) {
        const u = reference[y * w + x],
          v = actual[(dy + y) * stride + dx + x];
        dot += u * v;
        normA += u * u;
        normB += v * v;
      }
    return dot / Math.max(1, Math.sqrt(normA * normB)) >= 0.6;
  });
}

function sameOutsideFace(a, b) {
  if (!a || !b || a.length !== 4 || b.length !== 4) return false;
  const center = (p) => [p.reduce((s, q) => s + q[0], 0) / 4, p.reduce((s, q) => s + q[1], 0) / 4];
  const side = (p, q, t) => (q[0] - p[0]) * (t[1] - p[1]) - (q[1] - p[1]) * (t[0] - p[0]);
  const convex = (p) => p.every((v, i) => side(v, p[(i + 1) % 4], p[(i + 2) % 4]) > 0);
  const inside = (p, t) => p.every((v, i) => side(v, p[(i + 1) % 4], t) >= 0);
  const aa = area(a),
    ab = area(b);
  if (!convex(a) || !convex(b) || aa <= 0 || ab <= 0 || Math.max(aa, ab) > 3 * Math.min(aa, ab)) return false;
  if (!inside(a, center(b)) || !inside(b, center(a))) return false;
  // Sutherland-Hodgman clipping avoids an unavailable OpenCV.js binding.
  let cut = a;
  for (let i = 0; i < 4; i++) {
    const [sx, sy] = b[i],
      [ex, ey] = b[(i + 1) % 4],
      next = [];
    const side = ([x, y]) => (ex - sx) * (y - sy) - (ey - sy) * (x - sx);
    for (let j = 0; j < cut.length; j++) {
      const p = cut[j],
        q = cut[(j + 1) % cut.length],
        dp = side(p),
        dq = side(q);
      if (dp >= 0) next.push(p);
      if (dp >= 0 !== dq >= 0) {
        const t = dp / (dp - dq);
        next.push([p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])]);
      }
    }
    cut = next;
  }
  return cut.length >= 3 && area(cut) >= 0.75 * Math.min(aa, ab);
}

async function annotateOutsideCapacity(rgba, matcher, result) {
  if (result?.status !== 'ambiguous' || !result.footprint) return result;
  const outside = await readOutsideFamily(rgba, matcher, result.footprint);
  return outside?.family === 'Smooth Orange 1.75L' ? {...result, outsideCapacity: '1.75 L'} : result;
}
