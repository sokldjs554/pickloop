// Additional evidence for an old carton whose front artwork is shared by several GTINs.
// The orange word alone cannot resolve the SKU. Two independent reference photographs
// must locate the same ingredients panel next to the registered front on the photographed carton.
function orangeFace(own, template, query, matcher, centerLimit = .17) {
  const matches = correspondences(own, template, query, matcher);
  if (matches.length < 12) return null;
  const src = matches.map(match => template.points[match.source]);
  const dst = matches.map(match => query.points[match.target]);
  const mat = points => own(cv.matFromArray(points.length, 1, cv.CV_32FC2, points.flat()));
  const mask = own(new cv.Mat());
  const map = own(cv.findHomography(mat(src), mat(dst), cv.RANSAC, 3, mask, 1000, .995));
  if (map.empty()) return null;
  const keep = src.filter((_, i) => mask.data[i]);
  if (keep.length < 12 || keep.length < .32 * matches.length) return null;
  const front = template.view === 'front';
  const bands = front ? [[28,220], [230,415]] : [[15,220], [230,570]];
  if (bands.some(([lo, hi]) => keep.filter(([, y]) => y >= lo && y <= hi).length < 3)) return null;
  if (hullArea(keep) < (front ? .04 : .07) * 1000000) return null;
  const projected = own(new cv.Mat());
  cv.perspectiveTransform(mat([[0,0], [1000,0], [1000,1000], [0,1000]]), projected, map);
  const xy = projected.data32F;
  const quad = Array.from({length:4}, (_, i) => [xy[2*i]/query.width, xy[2*i+1]/query.height]);
  const size = area(quad);
  if (!cv.isContourConvex(projected) || !(size >= .024 && size <= 1.3) ||
      visibleArea(quad, 1, 1) < .55 * size) return null;
  if (cv.pointPolygonTest(mat(quad), new cv.Point(.5, .5), true) < -centerLimit) return null;
  return {source:template.source, view:template.view, gtin:template.gtin, quad, inliers:keep.length};
}

function orangeAdjoiningProof(faces) {
  const distance = (a,b) => Math.hypot(a[0]-b[0],a[1]-b[1]);
  const samePanel = (a,b) => a.source !== b.source && a.gtin === b.gtin &&
    a.quad.every((p,i) => distance(p,b.quad[i]) < .14*Math.sqrt(Math.min(area(a.quad),area(b.quad))));
  const ingredients = faces.filter(face => face.view === 'ingredients');
  for (const side of ingredients) {
    if (!ingredients.some(other => samePanel(side,other))) continue;
    const front = faces.find(face => {
      if (face.view !== 'front' || face.gtin !== side.gtin) return false;
      const seam = distance(side.quad[0],side.quad[3]);
      return distance(face.quad[1],side.quad[0]) < .16*seam &&
        distance(face.quad[2],side.quad[3]) < .16*seam;
    });
    if (front) return {gtin:side.gtin, view:'orange-adjoining-panels', inliers:side.inliers};
  }
  return null;
}

async function readOrangeSide(rgba, matcher, registry, footprint) {
  const response = await fetch('../../data/orange-side.json');
  if (!response.ok) throw Error('Orange side gallery unavailable');
  const gallery = await response.json();
  if (gallery.version !== 1) throw Error('Unknown orange side gallery format');
  const faces = [];
  for (const size of [720, 930]) {
    const result = scoped(own => {
      const query = extract(own,rgba,size,1);
      if (query.points.length < 12) return null;
      for (const template of gallery.templates.filter(item => !item.rectified)) {
        const face = scoped(local => orangeFace(local,template,query,matcher));
        if (!face) continue;
        if (footprint) {
          const expected = own(cv.matFromArray(4,1,cv.CV_32FC2,footprint.flat()));
          if (face.view === 'front' && !face.quad.some(([x,y]) =>
              cv.pointPolygonTest(expected,new cv.Point(x,y),true) >= -.04)) continue;
        }
        faces.push(face);
        if (face.view !== 'ingredients') continue;
        const from = own(cv.matFromArray(4,1,cv.CV_32FC2,
          face.quad.flatMap(([u,v]) => [u*query.width,v*query.height])));
        const to = own(cv.matFromArray(4,1,cv.CV_32FC2,[0,0, 170,0, 170,500, 0,500]));
        const aligned = own(new cv.Mat());
        cv.warpPerspective(query.frame,aligned,own(cv.getPerspectiveTransform(from,to)),new cv.Size(170,500));
        const second = features(own,aligned);
        if (second.points.length < 12) continue;
        for (const source of gallery.templates.filter(item => item.rectified && item.source !== face.source)) {
          const proof = scoped(inner => orangeFace(inner,source,second,matcher));
          const unit = [[0,0],[1,0],[1,1],[0,1]];
          if (proof && proof.quad.every(([u,v],i) => Math.hypot(u-unit[i][0],v-unit[i][1]) < .18)) {
            faces.push({...proof,quad:face.quad});
          }
        }
      }
      return orangeAdjoiningProof(faces);
    });
    if (result && registry[result.gtin]) return {...result, product:registry[result.gtin]};
  }
  return null;
}
