// Match several independently printed regions in the same planar projection.
// A shared brand logo or the word "grapefruit" alone occurs on competing cartons.
function printedRegionScore(own, paddedGray, patch) {
  const margin = 16;
  const [x,y,right,bottom] = patch.box;
  const [w,h] = patch.size;
  const roi = own(paddedGray.roi(new cv.Rect(x,y,right-x+2*margin,bottom-y+2*margin)));
  const resized = own(new cv.Mat()), pixels = own(new cv.Mat()), smooth = own(new cv.Mat());
  cv.resize(roi, resized, new cv.Size(w+8,h+8), 0, 0, cv.INTER_AREA);
  resized.convertTo(pixels, cv.CV_32F);
  cv.GaussianBlur(pixels, smooth, new cv.Size(0,0), 2);
  cv.subtract(pixels, smooth, pixels);
  const bytes = Int8Array.from(atob(patch.contrast), c => c.charCodeAt(0));
  const reference = own(cv.matFromArray(h, w, cv.CV_32F, bytes));
  const response = own(new cv.Mat());
  cv.matchTemplate(pixels, reference, response, cv.TM_CCORR_NORMED);
  return cv.minMaxLoc(response).maxVal;
}

function locatePrintedRegions(own, template, query, matcher, focus) {
  const pairs = correspondences(own, template, query, matcher, .83, 70);
  if (pairs.length < 12) return null;
  const matrix = points => own(cv.matFromArray(points.length, 1, cv.CV_32FC2, points.flat()));
  const source = matrix(pairs.map(m => template.points[m.source]));
  const target = matrix(pairs.map(m => query.points[m.target]));
  const mask = own(new cv.Mat());
  const transform = own(cv.findHomography(source, target, cv.RANSAC, 3.5, mask, 1000, .995));
  if (transform.empty()) return null;
  const inliers = cv.countNonZero(mask);
  if (inliers < 12) return null;
  const {width, height} = template;
  const corners = matrix([[0,0],[width,0],[width,height],[0,height]]);
  const projected = own(new cv.Mat());
  cv.perspectiveTransform(corners, projected, transform);
  const arr = projected.data32F;
  const quad = [0,2,4,6].map(i => [arr[i],arr[i+1]]);
  const fraction = area(quad)/(query.width * query.height);
  if (!cv.isContourConvex(projected) || !(fraction > .008 && fraction < 1.7) ||
      visibleArea(quad, query.width, query.height) < .85 * area(quad)) return null;
  const center = [0,1].map(axis => quad.reduce((sum,p) => sum+p[axis],0)/4);
  if (Math.abs(center[0]/query.width-.5) > .29 || Math.abs(center[1]/query.height-.5) > .30) return null;
  if (focus && cv.pointPolygonTest(focus,
      new cv.Point(center[0] / query.width, center[1] / query.height), true) < -.035) return null;
  const aligned = own(new cv.Mat()), gray = own(new cv.Mat()), padded = own(new cv.Mat());
  cv.warpPerspective(query.frame, aligned, transform, new cv.Size(width,height),
    cv.INTER_LINEAR | cv.WARP_INVERSE_MAP);
  cv.cvtColor(aligned, gray, cv.COLOR_RGBA2GRAY);
  cv.copyMakeBorder(gray,padded,16,16,16,16,cv.BORDER_REPLICATE);
  for (const patch of template.details) {
    const score = printedRegionScore(own,padded,patch);
    if (!(score >= patch.minimum)) return null;
  }
  return {gtin: template.gtin, view:'lettering', inliers};
}

// All registered candidates in this fallback must agree, including across scales.
async function readPrintedRegions(rgba, matcher, registry, footprint) {
  const response = await fetch('../../data/registered-detail-gallery.json');
  if (!response.ok) throw Error('Detail gallery unavailable');
  const gallery = await response.json();
  if (gallery.version !== 1) throw Error('Unknown detail gallery format');
  const found = new Map();
  for (const [size, stretch] of [[620,1],[900,1],[540,1.6],[680,1.6]]) {
    scoped(own => {
      const query = extract(own,rgba,size,stretch);
      if (query.points.length < 12) return;
      const focus = footprint && own(cv.matFromArray(4, 1, cv.CV_32FC2, footprint.flat()));
      for (const template of gallery.templates) {
        const hit = scoped(local => locatePrintedRegions(local,template,query,matcher,focus));
        if (hit && (!found.has(hit.gtin) || found.get(hit.gtin).inliers < hit.inliers)) found.set(hit.gtin,hit);
      }
    });
  }
  if (found.size > 1) return {status:'ambiguous'};
  const [hit] = found.values();
  if (!hit) return null;
  const product = registry[hit.gtin];
  return product ? {product, view:hit.view, inliers:hit.inliers} : {status:'incompatible'};
}
