'use strict';

const workScene = document.getElementById('work-scene');
const film = workScene.querySelector('video');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
let visitorInteracted = false;
let automaticPlayStarted = false;

function playFilm() {
  // Autoplay can be blocked by browser settings. Native controls stay available.
  film.play().catch(() => {});
}

// Some static hosts answer byte-range requests with the complete small MP4.
// A local Blob lets native players seek even when their range request failed.
const videoSource = film.querySelector('source');
const fallback = workScene.querySelector('.film-fallback');
let retriedVideo = false;

function showAnimation() {
  film.hidden = true;
  fallback.hidden = false;
  const image = fallback.querySelector('img');
  if (!reduceMotion.matches) image.src = image.dataset.animation;
}

async function recoverVideo() {
  if (retriedVideo) return;
  retriedVideo = true;
  try {
    const response = await fetch(videoSource.src);
    if (!response.ok) throw new Error('MP4 unavailable');
    const blobUrl = URL.createObjectURL(await response.blob());
    film.addEventListener('error', showAnimation, {once: true});
    film.addEventListener('loadedmetadata', () => {
      if (visitorInteracted || (automaticPlayStarted && !reduceMotion.matches)) playFilm();
    }, {once: true});
    film.src = blobUrl;
    window.addEventListener('pagehide', event => {
      if (!event.persisted) URL.revokeObjectURL(blobUrl);
    }, {once: true});
  } catch {
    showAnimation();
  }
}

videoSource.addEventListener('error', recoverVideo);
film.addEventListener('error', recoverVideo);
if (film.error) recoverVideo();
film.addEventListener('stalled', () => {
  if (film.readyState === 0) recoverVideo();
});

film.addEventListener('pointerdown', () => { visitorInteracted = true; });
film.addEventListener('keydown', () => { visitorInteracted = true; });
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(([entry]) => {
    if (!entry.isIntersecting) {
      if (!film.paused) film.pause();
      return;
    }
    if (entry.intersectionRatio >= .5 && !reduceMotion.matches && !visitorInteracted && !automaticPlayStarted) {
      automaticPlayStarted = true;
      playFilm();
    }
  }, {threshold: [0, .5]});
  observer.observe(film);
}

let pendingSeek;
function seekToMoment() {
  if (pendingSeek === undefined || film.readyState < 1) return;
  film.currentTime = pendingSeek;
  pendingSeek = undefined;
  playFilm();
}

film.addEventListener('loadedmetadata', seekToMoment);
for (const link of workScene.querySelectorAll('[data-elapsed]')) {
  link.addEventListener('click', event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || film.error || film.hidden) return;
    event.preventDefault();
    visitorInteracted = true;
    pendingSeek = Number(link.dataset.elapsed);
    if (film.readyState < 1) film.load();
    else seekToMoment();
    film.focus({preventScroll: true});
  });
}
