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
    if (window.__rebuildSubnav) window.__rebuildSubnav();
  }

  buttons.forEach(function (b) {
    b.addEventListener('click', function () { setMode(b.dataset.mode); });
  });

  const initial = new URLSearchParams(location.search).get('mode');
  if (initial && VALID_MODES.includes(initial)) {
    setMode(initial);
  }
})();

// In-sidebar section list: under the active nav item, list this page's h2
// sections as anchor links with scrollspy. Replaces the old floating TOC —
// no overlap with content, and it lives where the user already looks for nav.

(function () {
  const container = document.querySelector('.content .container') || document.querySelector('.container');
  const activeLink = document.querySelector('.sidebar .nav-link.active');
  if (!container || !activeLink) return;

  let subnav = null;
  let observer = null;

  function isMuted(el) {
    const bodyHasDynasty = document.body.classList.contains('mode-dynasty');
    const bodyHasWinnow = document.body.classList.contains('mode-winnow');
    let p = el;
    while (p && p !== document.body) {
      if (p.classList) {
        if (p.classList.contains('winnow-only') && bodyHasDynasty) return true;
        if (p.classList.contains('dynasty-only') && bodyHasWinnow) return true;
      }
      p = p.parentElement;
    }
    return false;
  }

  function build() {
    if (subnav) { subnav.remove(); subnav = null; }
    if (observer) { observer.disconnect(); observer = null; }

    const headings = container.querySelectorAll('h2');
    if (headings.length < 3) return;

    const seen = new Set();
    const unique = [];
    headings.forEach(function (h, i) {
      if (isMuted(h)) return;
      const raw = h.textContent.replace(/\s+/g, ' ').trim();
      const label = raw.replace(/\s*\(\d+\)\s*$/, '').trim();
      if (!label || seen.has(label)) return;
      seen.add(label);
      if (!h.id) {
        h.id = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') + '-' + i;
      }
      unique.push({ heading: h, label: label });
    });

    if (unique.length < 3) return;

    subnav = document.createElement('div');
    subnav.className = 'subnav';
    const linksById = {};
    unique.forEach(function (u) {
      const a = document.createElement('a');
      a.href = '#' + u.heading.id;
      a.textContent = u.label;
      a.className = 'subnav-link';
      subnav.appendChild(a);
      linksById[u.heading.id] = a;
    });
    activeLink.insertAdjacentElement('afterend', subnav);

    observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        const link = linksById[entry.target.id];
        if (!link) return;
        if (entry.isIntersecting) {
          Object.values(linksById).forEach(function (l) { l.classList.remove('active'); });
          link.classList.add('active');
        }
      });
    }, { rootMargin: '-15% 0px -70% 0px' });

    unique.forEach(function (u) { observer.observe(u.heading); });
  }

  window.__rebuildSubnav = build;
  build();
})();
