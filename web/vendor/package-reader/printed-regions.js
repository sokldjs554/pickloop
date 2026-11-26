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

function locatePrintedRegions(own, template, query, matcher, focus, rectified=false) {
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
  if (rectified) {
    // The second fit must remain on the originally localized panel.
    const corners = [[0,0],[1,0],[1,1],[0,1]];
    if (quad.some(([x,y],i) =>
      Math.max(Math.abs(x/width-corners[i][0]),Math.abs(y/height-corners[i][1])) > .23)) return null;
  }
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
  const scores = template.details.map(patch => printedRegionScore(own,padded,patch));
  let marks;
  if (scores.every((score,i) => score >= template.details[i].minimum)) {
    marks = template.details.map(({box: [x,y,right,bottom]}) => [(x+right)/2, (y+bottom)/2]);
  } else if (template.oblique && !rectified && scores[0] >= .60 && scores.every(score => score >= .30)) {
    // A logo often survives perspective compression. Use it to refine this plane,
    // then still require separate matches to both words in the rectified pixels.
    const second = locatePrintedRegions(own, template, features(own,aligned), matcher, null, true);
    if (!second) return null;
    marks = second.marks;
  } else {
    return null;
  }
  if (!template.oblique) return {gtin:template.gtin,view:'lettering',inliers};
  const projectedMarks = own(new cv.Mat());
  cv.perspectiveTransform(matrix(marks), projectedMarks, transform);
  const positions = marks.map((_,i) => [projectedMarks.data32F[2*i],projectedMarks.data32F[2*i+1]]);
  return {gtin:template.gtin,view:'lettering',inliers,marks:positions,source:template.sourceHash};
}

function samePrintedPanel(a, b) {
  if (a.gtin !== b.gtin || a.source === b.source) return false;
  const distance = (p,q) => Math.hypot(p[0]-q[0],p[1]-q[1]);
  const separation = Math.min(distance(a.marks[0],a.marks[2]), distance(b.marks[0],b.marks[2]));
  return separation > 0 && a.marks.every((mark,i) => distance(mark,b.marks[i]) <= .35*separation);
}

// The upright passes stretch along the image axes. A diagonally foreshortened face
// needs an affine stretch along a tilted axis; map its keypoints back before scoring.
function affineQuery(own, frame, degrees) {
  const angle = degrees*Math.PI/180, c = Math.cos(angle), s = Math.sin(angle);
  const xx = 1+c*c, xy = -s*c, yy = 1+s*s;
  const xs = [0,xx*frame.cols,xy*frame.rows,xx*frame.cols+xy*frame.rows];
  const ys = [0,xy*frame.cols,yy*frame.rows,xy*frame.cols+yy*frame.rows];
  const x = Math.min(...xs), y = Math.min(...ys);
  const affine = own(cv.matFromArray(2,3,cv.CV_64F,[xx,xy,-x,xy,yy,-y]));
  const raster = own(new cv.Mat());
  cv.warpAffine(frame,raster,affine,new cv.Size(Math.ceil(Math.max(...xs)-x),Math.ceil(Math.max(...ys)-y)),
    cv.INTER_LINEAR,cv.BORDER_CONSTANT);
  const warped = features(own,raster);
  const points = warped.points.map(([u,v]) => [(yy*(u+x)-xy*(v+y))/2,(-xy*(u+x)+xx*(v+y))/2]);
  return {points,descriptors:warped.descriptors,frame,width:frame.cols,height:frame.rows};
}

function obliquePrintedMatches(own, rgba, matcher, templates, footprint, found) {
  if (templates.length < 2) return;
  const frame = own(new cv.Mat());
  const scale = 900/Math.max(rgba.rows,rgba.cols);
  cv.resize(rgba,frame,new cv.Size(Math.round(rgba.cols*scale),Math.round(rgba.rows*scale)),0,0,
    scale < 1 ? cv.INTER_AREA : cv.INTER_LINEAR);
  const focus = footprint && own(cv.matFromArray(4,1,cv.CV_32FC2,footprint.flat()));
  const votes = [], products = new Set(templates.map(t=>t.gtin));
  for (const angle of [-30,30,-60,60]) {
    scoped(local => {
      const query = affineQuery(local,frame,angle);
      for (const template of templates) {
        const hit = scoped(inner => locatePrintedRegions(inner,template,query,matcher,focus));
        if (!hit) continue;
        if (votes.some(previous => samePrintedPanel(previous,hit))) found.set(hit.gtin,hit);
        votes.push(hit);
      }
    });
    if (found.size === products.size) break;
  }
}

// All registered candidates in this fallback must agree, including across scales.
async function readPrintedRegions(rgba, matcher, registry, footprint) {
  const response = await fetch('../../data/registered-detail-gallery.json');
  if (!response.ok) throw Error('Detail gallery unavailable');
  const gallery = await response.json();
  if (gallery.version !== 1) throw Error('Unknown detail gallery format');
  const found = new Map();
  const upright = gallery.templates.filter(template => !template.oblique);
  for (const [size, stretch] of [[620,1],[900,1],[540,1.6],[680,1.6]]) {
    scoped(own => {
      const query = extract(own,rgba,size,stretch);
      if (query.points.length < 12) return;
      const focus = footprint && own(cv.matFromArray(4, 1, cv.CV_32FC2, footprint.flat()));
      for (const template of upright) {
        const hit = scoped(local => locatePrintedRegions(local,template,query,matcher,focus));
        if (hit && (!found.has(hit.gtin) || found.get(hit.gtin).inliers < hit.inliers)) found.set(hit.gtin,hit);
      }
    });
  }
  if (!found.size) {
    const oblique = gallery.templates.filter(template => template.oblique);
    scoped(own => obliquePrintedMatches(own,rgba,matcher,oblique,footprint,found));
  }
  if (found.size > 1) return {status:'ambiguous'};
  const [hit] = found.values();
  if (!hit) return null;
  const product = registry[hit.gtin];
  return product ? {product, view:hit.view, inliers:hit.inliers} : {status:'incompatible'};
}
