'use strict';

// The dataset's official class name and numerical ID stay visible alongside each Korean label.
const koreanProductNames = {
  'Golden-Delicious': '골든 딜리셔스 사과',
  'Granny-Smith': '그래니 스미스 사과',
  'Pink-Lady': '핑크 레이디 사과',
  'Red-Delicious': '레드 딜리셔스 사과',
  'Royal-Gala': '로열 갈라 사과',
  Avocado: '아보카도',
  Banana: '바나나',
  Kiwi: '키위',
  Lemon: '레몬',
  Lime: '라임',
  Mango: '망고',
  Cantaloupe: '칸탈루프 멜론',
  'Galia-Melon': '갈리아 멜론',
  'Honeydew-Melon': '허니듀 멜론',
  Watermelon: '수박',
  Nectarine: '천도복숭아',
  Orange: '오렌지',
  Papaya: '파파야',
  'Passion-Fruit': '패션프루트',
  Peach: '복숭아',
  Anjou: '앙주 배',
  Conference: '콘퍼런스 배',
  Kaiser: '카이저 배',
  Pineapple: '파인애플',
  Plum: '자두',
  Pomegranate: '석류',
  'Red-Grapefruit': '레드 자몽',
  Satsumas: '온주밀감',
  'Bravo-Apple-Juice': '브라보 사과주스',
  'Bravo-Orange-Juice': '브라보 오렌지주스',
  'God-Morgon-Apple-Juice': '고드 모르곤 사과주스',
  'God-Morgon-Orange-Juice': '고드 모르곤 오렌지주스',
  'God-Morgon-Orange-Red-Grapefruit-Juice': '고드 모르곤 오렌지·레드 자몽주스',
  'God-Morgon-Red-Grapefruit-Juice': '고드 모르곤 레드 자몽주스',
  'Tropicana-Apple-Juice': '트로피카나 사과주스',
  'Tropicana-Golden-Grapefruit': '트로피카나 골든 자몽주스',
  'Tropicana-Juice-Smooth': '트로피카나 스무스 주스',
  'Tropicana-Mandarin-Morning': '트로피카나 만다린 모닝 주스',
  'Arla-Ecological-Medium-Fat-Milk': '알라 유기농 중지방 우유',
  'Arla-Lactose-Medium-Fat-Milk': '알라 락토프리 우유',
  'Arla-Medium-Fat-Milk': '알라 중지방 우유',
  'Arla-Standard-Milk': '알라 일반 우유',
  'Garant-Ecological-Medium-Fat-Milk': '가란트 유기농 중지방 우유',
  'Garant-Ecological-Standard-Milk': '가란트 유기농 일반 우유',
  'Oatly-Natural-Oatghurt': '오틀리 플레인 귀리 요거트',
  'Oatly-Oat-Milk': '오틀리 귀리 음료',
  'Arla-Ecological-Sour-Cream': '알라 유기농 사워크림',
  'Arla-Sour-Cream': '알라 사워크림',
  'Arla-Sour-Milk': '알라 발효유',
  'Alpro-Blueberry-Soyghurt': '알프로 블루베리 두유 요거트',
  'Alpro-Vanilla-Soyghurt': '알프로 바닐라 두유 요거트',
  'Alpro-Fresh-Soy-Milk': '알프로 냉장 두유',
  'Alpro-Shelf-Soy-Milk': '알프로 상온 두유',
  'Arla-Mild-Vanilla-Yoghurt': '알라 마일드 바닐라 요거트',
  'Arla-Natural-Mild-Low-Fat-Yoghurt': '알라 마일드 저지방 플레인 요거트',
  'Arla-Natural-Yoghurt': '알라 플레인 요거트',
  'Valio-Vanilla-Yoghurt': '발리오 바닐라 요거트',
  'Yoggi-Strawberry-Yoghurt': '요기 딸기 요거트',
  'Yoggi-Vanilla-Yoghurt': '요기 바닐라 요거트',
  Asparagus: '아스파라거스',
  Aubergine: '가지',
  Cabbage: '양배추',
  Carrots: '당근',
  Cucumber: '오이',
  Garlic: '마늘',
  Ginger: '생강',
  Leek: '리크',
  'Brown-Cap-Mushroom': '갈색 양송이버섯',
  'Yellow-Onion': '노란 양파',
  'Green-Bell-Pepper': '초록 파프리카',
  'Orange-Bell-Pepper': '주황 파프리카',
  'Red-Bell-Pepper': '빨간 파프리카',
  'Yellow-Bell-Pepper': '노란 파프리카',
  'Floury-Potato': '분질 감자',
  'Solid-Potato': '단단한 감자',
  'Sweet-Potato': '고구마',
  'Red-Beet': '레드 비트',
  'Beef-Tomato': '비프 토마토',
  'Regular-Tomato': '일반 토마토',
  'Vine-Tomato': '송이 토마토',
  Zucchini: '주키니 호박'
};

const catalogueElement = suffix => document.getElementById('catalogue-' + suffix);
const number = new Intl.NumberFormat('ko-KR');
const quantity = n => number.format(n);

function productRow(item) {
  const row = document.createElement('tr');
  const heading = document.createElement('th');
  heading.scope = 'row';
  const title = document.createElement('span');
  title.textContent = koreanProductNames[item.name] || item.name;
  const official = document.createElement('small');
  official.textContent = `#${item.id} · ${item.name}`;
  heading.append(title, official);
  row.append(heading);
  for (const key of ['test_total', 'correct', 'wrong', 'held']) {
    const cell = document.createElement('td');
    cell.textContent = quantity(item[key]);
    row.append(cell);
  }
  return row;
}

function normaliseSearch(text) {
  return text.normalize().toLowerCase().replace(/[\s-]/gu, '');
}

function includesTerms(text, terms) {
  const searchable = normaliseSearch(text);
  return terms.every(term => searchable.includes(term));
}

function bindPagedTable({prefix, filterId, entries, matches, makeRow, unit}) {
  const element = suffix => document.getElementById(prefix + '-' + suffix);
  const search = element('search');
  const filter = element(filterId);
  const previous = element('prev');
  const next = element('next');
  const pageSize = 8;
  let page = 0;

  function render() {
    const terms = search.value.normalize().trim().toLowerCase().split(/[\s-]+/u).filter(Boolean);
    const filtered = entries.filter(item => matches(item, filter.value, terms));
    const start = page * pageSize;
    const end = Math.min(start + pageSize, filtered.length);
    element('rows').replaceChildren(...filtered.slice(start, end).map(makeRow));
    element('position').textContent = filtered.length
      ? `검색 결과 ${quantity(filtered.length)}${unit} 중 ${quantity(start + 1)}–${quantity(end)}번째`
      : '검색 결과가 없습니다.';
    previous.disabled = page === 0;
    next.disabled = end >= filtered.length;
  }

  function resetPage() { page = 0; render(); }
  search.addEventListener('input', resetPage);
  filter.addEventListener('change', resetPage);
  previous.addEventListener('click', () => { page -= 1; render(); });
  next.addEventListener('click', () => { page += 1; render(); });
  render();
}

function matchesProduct(item, group, terms) {
  if (group && item.group !== group) return false;
  if (terms.length === 1 && /^#?\d+$/.test(terms[0])) return String(item.id) === terms[0].replace('#', '');
  return includesTerms(`${item.name} ${koreanProductNames[item.name] || ''}`, terms);
}

const statusLabels = {correct: '정답', wrong: '오답', held: '보류'};
const photoSources = {test: '공식 시험', val: '공식 검증', 'iconic-images-and-descriptions': '카탈로그'};

function photoProductCell(name) {
  const cell = document.createElement('td');
  if (name === 'UNKNOWN') {
    cell.textContent = '판정 보류';
    return cell;
  }
  const korean = document.createElement('span');
  korean.textContent = koreanProductNames[name] || name;
  const official = document.createElement('small');
  official.textContent = name;
  cell.append(korean, official);
  return cell;
}

function photoRow(photo, source) {
  const row = document.createElement('tr');
  const file = document.createElement('th');
  file.scope = 'row';
  const parts = photo.path.split('/');
  const link = document.createElement('a');
  link.href = source + parts.map(encodeURIComponent).join('/');
  link.textContent = parts.at(-1);
  link.title = photo.path;
  const reference = document.createElement('small');
  reference.textContent = `${photoSources[parts[0]]} · ${photo.id.slice(0, 12)}`;
  reference.title = photo.id;
  file.append(link, reference);
  const status = document.createElement('td');
  status.className = photo.status;
  status.textContent = statusLabels[photo.status];
  row.append(file, photoProductCell(photo.truth), photoProductCell(photo.prediction), status);
  return row;
}

function matchesPhoto(photo, filter, terms) {
  if (filter === 'review' && photo.status === 'correct') return false;
  if (Object.hasOwn(statusLabels, filter) && photo.status !== filter) return false;
  return includesTerms([photo.id, photo.path, photo.truth, photo.prediction,
    koreanProductNames[photo.truth], koreanProductNames[photo.prediction]].join(' '), terms);
}

function bindPreviousPhotos(prior) {
  const details = document.getElementById('previous-photos');
  const content = document.getElementById('photo-lookup');
  const status = document.getElementById('photo-load-status');
  let loading = false;
  content.hidden = true;
  async function load() {
    if (!details.open || loading || !content.hidden) return;
    loading = true;
    status.textContent = '사진별 판정 기록을 불러오는 중입니다.';
    try {
      const response = await fetch('data/grocery-previous-photos.json');
      if (!response.ok) throw new Error('lookup unavailable');
      const {photos, source_base: source} = await response.json();
      if (!/^https:\/\/raw\.githubusercontent\.com\/marcusklasson\/GroceryStoreDataset\/[a-f0-9]{40}\/dataset\/$/.test(source)
          || photos.length !== prior.total
          || Object.keys(statusLabels).some(key => photos.filter(row => row.status === key).length !== prior[key])) {
        throw new Error('lookup does not match the source and measured totals');
      }
      bindPagedTable({prefix: 'photo', filterId: 'filter', entries: photos, matches: matchesPhoto,
        makeRow: row => photoRow(row, source), unit: '장'});
      content.hidden = false;
      status.textContent = '';
    } catch {
      status.textContent = '사진별 기록을 불러오지 못했습니다. 위의 CSV를 확인하거나 목록을 닫았다가 다시 열어 주세요.';
    } finally {
      loading = false;
    }
  }
  if (location.hash === '#previous-photos') details.open = true;
  details.addEventListener('toggle', load);
  load();
}

function showCatalogue({counts, previous_unknown: prior, classes}) {
  const recognised = classes.filter(item => item.correct > 0).length;
  catalogueElement('coverage').textContent =
    `등록 상품 ${quantity(counts.registered)}종 중 공식 시험에서 한 장 이상 정확히 식별한 상품은 ${quantity(recognised)}종입니다.`;
  for (const key of ['test_total', 'correct', 'wrong', 'held']) {
    catalogueElement(key.replace('_', '-')).textContent = quantity(counts[key]);
  }
  catalogueElement('previous').textContent =
    `재평가 ${quantity(prior.total)}장 중 정답 ${quantity(prior.correct)}장, 오답 ${quantity(prior.wrong)}장, 보류 ${quantity(prior.held)}장`;
  catalogueElement('outside').textContent = counts.outside_total
    ? `외부 사진 ${quantity(counts.outside_total)}장 중 오수락 ${quantity(counts.outside_false_accepts)}장`
    : '평가된 외부 사진이 없습니다.';
  bindPagedTable({prefix: 'catalogue', filterId: 'group', entries: classes, matches: matchesProduct,
    makeRow: productRow, unit: '종'});
  bindPreviousPhotos(prior);
}

async function loadCatalogue() {
  const status = catalogueElement('status');
  const results = catalogueElement('results');
  results.hidden = true;
  status.textContent = '상품별 판정 기록을 불러오는 중입니다.';
  try {
    const response = await fetch('data/grocery-catalogue.json');
    if (!response.ok) throw new Error('catalogue unavailable');
    showCatalogue(await response.json());
    results.hidden = false;
    status.textContent = '';
    if (location.hash === '#previous-photos') {
      document.getElementById('previous-photos').scrollIntoView?.();
    }
  } catch {
    status.textContent = '상품별 판정 기록을 불러오지 못했습니다. 위의 사진별 판정 CSV를 확인해 주세요.';
  }
}

loadCatalogue();
