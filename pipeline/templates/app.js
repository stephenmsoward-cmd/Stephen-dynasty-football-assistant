// Toggle between Dynasty and Win-Now modes by swapping a class on <body>.
// Mode persists in the URL (?mode=winnow) so links are shareable.

(function () {
  const VALID_MODES = ['dynasty', 'winnow'];
  const buttons = document.querySelectorAll('.mode-toggle [data-mode]');

  function setMode(mode) {
    if (!VALID_MODES.includes(mode)) return;
    document.body.classList.remove('mode-dynasty', 'mode-winnow');
    document.body.classList.add('mode-' + mode);
    buttons.forEach(function (b) {
      b.classList.toggle('active', b.dataset.mode === mode);
      b.setAttribute('aria-selected', b.dataset.mode === mode ? 'true' : 'false');
    });
    const url = new URL(location.href);
    url.searchParams.set('mode', mode);
    history.replaceState(null, '', url);
  }

  buttons.forEach(function (b) {
    b.addEventListener('click', function () { setMode(b.dataset.mode); });
  });

  const initial = new URLSearchParams(location.search).get('mode');
  if (initial && VALID_MODES.includes(initial)) {
    setMode(initial);
  }
})();
