// Complete front-panel product names from the God Morgon portfolio. Generic fruit
// names also appear in ingredient lists and do not establish an outside item.
const titles = new Set([
  'SMOOTH ORANGE', 'SMOOTH APPELSIN', 'SMOOTH APELSIN', 'FRUIT CRUSH', 'ORANGE NECTAR',
  'APPLE ELDERFLOWER', 'APPLE MANDARIN CARROT', 'ORANGE BLOOD ORANGE', 'APPLE PEAR KIWI LIME',
  'APPLE RHUBARB', 'APPLE STRAWBERRY PASSIONFRUIT', 'ORANGE MANGO', 'ORANGE MANDARIN',
  'BLOOD ORANGE', 'BLOOD ORANGE APPLE', 'SWEET ORANGE', 'MANGO PASSION', 'MANGO PASSION FRUIT',
  'ORIGINAL LEMONADE', 'CLASSIC TROPICAL', 'TROPICAL DELIGHT', 'BERRY PROTECT', 'SUN POWER',
  'GINGER SHOT', 'GINGER BERRY SHOT', 'GINGER FIBER TROPICAL SHOT', 'EXTRA STRONG SHOT',
  'ENERGY SHOT', 'IMMUNITY SHOT', 'WAKE UP SMOOTHIE', 'BERRY BLEND', 'EXOTIC BLEND'
]);

const normalize = text => text.normalize('NFKD').replace(/\p{M}/gu, '').toUpperCase()
  .replace(/[^A-Z0-9.,]+/g, ' ').trim().replace(/\s+/g, ' ');
const cx = b => (b.x0 + b.x1) / 2;
const height = b => b.y1 - b.y0;
function bounds(words) {
  return {x0: Math.min(...words.map(w => w.x0)), x1: Math.max(...words.map(w => w.x1)),
    y0: Math.min(...words.map(w => w.y0)), y1: Math.max(...words.map(w => w.y1))};
}

// A white-background source is eligible only when it contains one isolated
// connected package. This intentionally declines shelf scenes and frame-filling crops.
export function solePackage({width, height: h, data}) {
  if (width < 16 || h < 16 || width * h > 200000 || data.length !== width * h * 4) return null;
  const mask = new Uint8Array(width * h);
  const notable = [];
  for (let i = 0; i < mask.length; i++) {
    const j = i * 4;
    mask[i] = data[j + 3] > 128 && Math.min(data[j], data[j+1], data[j+2]) < 220 ? 1 : 0;
  }
  const queue = new Int32Array(mask.length);
  for (let i = 0; i < mask.length; i++) {
    if (!mask[i]) continue;
    let count = 1, head = 0, x0 = width, x1 = 0, y0 = h, y1 = 0;
    const left = new Int32Array(h).fill(width), right = new Int32Array(h).fill(-1);
    queue[0] = i; mask[i] = 0;
    while (head < count) {
      const at = queue[head++], x = at % width, y = Math.floor(at / width);
      x0 = Math.min(x0,x); x1 = Math.max(x1,x); y0 = Math.min(y0,y); y1 = Math.max(y1,y);
      left[y] = Math.min(left[y],x); right[y] = Math.max(right[y],x);
      const neighbours = [];
      if (x) neighbours.push(at-1);
      if (x+1 < width) neighbours.push(at+1);
      if (y) neighbours.push(at-width);
      if (y+1 < h) neighbours.push(at+width);
      for (const n of neighbours) if (mask[n]) { mask[n] = 0; queue[count++] = n; }
    }
    if (count > width*h*0.01) notable.push({x0,x1,y0,y1,left,right,count});
  }
  if (notable.length !== 1) return null;
  const box = notable[0], ratio = (box.x1-box.x0)/(box.y1-box.y0);
  if (box.x0 < 1 || box.y0 < 1 || box.x1 >= width-1 || box.y1 >= h-1 ||
      box.count < width*h*.04 || ratio < .15 || ratio > .9) return null;
  return box;
}

function readLayout(tsv, image) {
  const lines = new Map(); let pageW=image.width, pageH=image.height;
  for (const row of tsv.split(/\r?\n/)) {
    const c=row.split('\t'); if (c.length < 12) continue;
    if (c[0] === '1') {pageW=Number(c[8]);pageH=Number(c[9]);}
    if (c[0] !== '5' || !c[11].trim()) continue;
    const x=Number(c[6]), y=Number(c[7]), w=Number(c[8]), h=Number(c[9]);
    if (![x,y,w,h].every(Number.isFinite) || w <= 0 || h <= 0) continue;
    const key=c.slice(1,5).join('/');
    const word={x0:x,x1:x+w,y0:y,y1:y+h,raw:c[11],text:normalize(c[11]),conf:Number(c[10])};
    if (!lines.has(key)) lines.set(key,[]);
    lines.get(key).push(word);
  }
  const rows = [...lines.values()].map(words => {
    words.sort((a,b)=>a.x0-b.x0);
    return {...bounds(words),words,raw:words.map(w=>w.raw).join(' '),
      text:words.map(w=>w.text).filter(Boolean).join(' ')};
  }).sort((a,b)=>a.y0-b.y0 || a.x0-b.x0);
  return {rows,pageW,pageH};
}

function stacked(a,b) {
  return b.y0 >= a.y0 && b.y0-a.y1 < height(a)*1.5 &&
    Math.abs(cx(a)-cx(b)) <= Math.max(height(a),height(b));
}
function logoBox(rows) {
  const starts=rows.filter(r=>r.text==='GOD' || r.text==='GOD MORGON' || r.text==='GODMORGON');
  if (starts.length!==1) return null;
  const a=starts[0];
  if (a.text!=='GOD') return a;
  const m=rows.find(r=>r.text==='MORGON' && stacked(a,r));
  if (m) return bounds([a,m]);
  const b=rows.find(r=>r.text==='MOR' && stacked(a,r));
  if (!b) return null;
  const c=rows.find(r=>/^G(?:O|0|[\p{S}])N$/iu.test(r.raw) && stacked(b,r));
  return c ? bounds([a,b,c]) : null;
}

function outsideTitle(text) {
  const label=text.replace(/[.,]/g,' ').replace(/\s+/g,' ').trim();
  if (titles.has(label)) return label;
  const q=text.match(/^(?:NET (?:VOL(?:UME)?|CONTENTS)|NETTO(?:VOLUME|TILAVUUS)?)\s+(\d+(?:[.,]\d+)?)\s*(ML|CL|L)$/);
  if (!q) return null;
  const ml=Number(q[1].replace(',','.')) * {ML:1,CL:10,L:1000}[q[2]];
  return ml>=50 && ml<=3000 && ml!==250 && ml!==1000 ? text : null;
}

export function outsideFrontPrint(tsv,image) {
  if (typeof tsv!=='string' || !image) return null;
  const {rows,pageW,pageH}=readLayout(tsv,image), words=rows.map(r=>r.text).join(' ');
  if (!pageW || !pageH ||
      /INGREDI|INGREDIEN|AINEKS|AINEOS|NUTRIT|NARINGS|RAVINTO|ALLERGEN|RECIPE|RESEPT|PER\s+100|TROPICANA|BRAVO|INNOCENT|RYNKEBY|BRAMHULTS|\b\d+\s*X\b|\bPACK OF\b/.test(words)) return null;
  const logo=logoBox(rows);
  if (!logo) return null;
  const pkg=solePackage(image);
  if (!pkg) return null;
  const inside=b=>{
    const y=Math.min(image.height-1,Math.floor((b.y0+b.y1)/2*image.height/pageH));
    return b.x0*image.width/pageW >= pkg.left[y]-1 && b.x1*image.width/pageW <= pkg.right[y]+2;
  };
  if (!inside(logo)) return null;
  const below=rows.filter(r=>r.y0 >= logo.y1-height(logo)*.1 && r.y0-logo.y1<=3*height(logo) &&
    Math.abs(cx(r)-cx(logo))<=height(logo) && inside(r));
  for (const first of below) {
    const groups=[[first], ...below.filter(next=>next!==first && stacked(first,next)).map(next=>[first,next])];
    for (const g of groups) {
      if (g.some(line=>line.words.some(w=>w.text && !(w.conf>=60)))) continue;
      const text=outsideTitle(g.map(line=>line.text).join(' '));
      if (text) return {text,source:'isolated_front_print'};
    }
  }
  return null;
}
