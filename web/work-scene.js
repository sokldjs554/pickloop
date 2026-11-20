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
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || film.error) return;
    event.preventDefault();
    visitorInteracted = true;
    pendingSeek = Number(link.dataset.elapsed);
    if (film.readyState < 1) film.load();
    else seekToMoment();
    film.focus({preventScroll: true});
  });
}
