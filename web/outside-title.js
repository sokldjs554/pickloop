// Locate an isolated dark front panel and retain red/orange ink in the title area.
// Photos with two panels, a wall of products, or a small/off-center pack abstain.
export async function titleCrop(image) {
  const bitmap = await createImageBitmap(image);
  const scale = Math.min(1, 1440 / bitmap.height);
  const width = Math.round(bitmap.width * scale), height = Math.round(bitmap.height * scale);
  if (width < 80 || width > .85 * height || width < .22 * height) {
    bitmap.close();
    return null;
  }
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  try { ctx.drawImage(bitmap, 0, 0, width, height); } finally { bitmap.close(); }
  const top = Math.round(.34 * height), rows = Math.round(.50 * height) - top;
  const strip = ctx.getImageData(0, top, width, rows);
  const pixels = strip.data;
  const columns = [];
  for (let x = 0; x < width; x++) {
    let dark = 0;
    for (let y = 0; y < rows; y++) {
      const i = 4 * (y * width + x);
      if (Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) < 125) dark++;
    }
    if (dark > .55 * rows) columns.push(x);
  }
  if (!columns.length) return null;
  const left = columns[0], right = columns.at(-1), span = right - left + 1;
  if (span < .23 * height || span > .43 * height || Math.abs((left + right) / 2 - width / 2) > .09 * width ||
      columns.some((x, i) => i && x - columns[i - 1] > .055 * span)) return null;
  const inset = Math.round(.055 * span);
  const crop = ctx.getImageData(left + inset, top, span - 2 * inset, rows);
  let ink = 0;
  for (let i = 0; i < crop.data.length; i += 4) {
    const red = crop.data[i] - Math.max(crop.data[i + 1], crop.data[i + 2]);
    if (red > 40) ink++;
    const gray = 255 - Math.min(255, Math.max(0, (red - 10) * 4));
    crop.data[i] = crop.data[i + 1] = crop.data[i + 2] = gray;
  }
  const fraction = ink / (crop.width * rows);
  if (fraction < .025 || fraction > .33) return null;
  canvas.width = crop.width;
  canvas.height = rows;
  ctx.putImageData(crop, 0, 0);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  return blob && {image: new Uint8Array(await blob.arrayBuffer()), width: crop.width};
}

// The two flavor words must be prominent, stacked and centered on the same face.
// The heading immediately above them distinguishes a product title from ingredients.
export function outsideTitle(tsv, width) {
  const words = [];
  for (const row of (tsv || '').split('\n')) {
    const fields = row.trimEnd().split('\t');
    if (fields[0] !== '5') continue;
    const [x, y, w, h] = fields.slice(6, 10).map(Number);
    const word = fields[11]?.toUpperCase().replace(/^[^A-Z]+|[^A-Z]+$/g, '');
    if (word && w > 0 && h > 0) words.push({word, x, y, w, h, cx: x + w / 2, confidence: Number(fields[10])});
  }
  const titles = [
    ['CITRUS', 'BLOOD', 'ORANGE', '블러드오렌지'],
    ['BLEND', 'ORANGE', 'MANGO', '오렌지·망고'],
  ];
  const found = [];
  for (const [heading, first, last, family] of titles) {
    // The curved second heading word can be incomplete. Its prefix only
    // corroborates the intact SELECTED word and the two exact flavor words.
    const hits = [
      words.filter(w => w.word === 'SELECTED' || w.word === 'ELECTED'),
      words.filter(w => w.word === heading || (heading === 'CITRUS' && /^CIT[A-Z]{2,3}$/.test(w.word))),
      words.filter(w => w.word === first),
      words.filter(w => w.word === last),
    ];
    if (hits.some(group => group.length !== 1)) continue;
    const [selected, a, b, c] = hits.map(group => group[0]);
    if (selected.word !== 'SELECTED' && a.word !== heading) continue;
    if (selected.x >= a.x || a.x < selected.x + .8 * selected.w || a.x - selected.x - selected.w > .16 * width ||
        Math.abs(selected.y - a.y) > .6 * Math.max(selected.h, a.h)) continue;
    if ([b, c].some(w => w.confidence < 75 || w.h < .032 * width || w.w < .13 * width || Math.abs(w.cx / width - .5) > .21)) continue;
    if (Math.abs(b.cx - c.cx) > .10 * width || c.y <= b.y + .45 * b.h || c.y > b.y + 2.8 * b.h ||
        a.y >= b.y || b.y - a.y > 4 * Math.max(a.h, b.h) || Math.abs(a.cx - b.cx) > .31 * width) continue;
    found.push(family);
  }
  return found.length === 1 ? found[0] : null;
}
