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
    // Rebuild the TOC so mode-hidden sections drop out.
    if (window.__rebuildToc) window.__rebuildToc();
  }

  buttons.forEach(function (b) {
    b.addEventListener('click', function () { setMode(b.dataset.mode); });
  });

  const initial = new URLSearchParams(location.search).get('mode');
  if (initial && VALID_MODES.includes(initial)) {
    setMode(initial);
  }
})();

// Auto-build a floating table of contents from h2 elements on long pages.
// Only renders if (a) the viewport is wide enough and (b) there are 3+ sections.
// Re-renders when the mode toggle is flipped (called from above).

(function () {
  const container = document.querySelector('.container');
  if (!container) return;

  let existingToc = null;
  let observer = null;

  function isMuted(el) {
    // Walk up and see if any ancestor is hidden via mode-only class given
    // the current body mode.
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
    if (existingToc) {
      existingToc.remove();
      existingToc = null;
    }
    if (observer) {
      observer.disconnect();
      observer = null;
    }

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

    const toc = document.createElement('nav');
    toc.className = 'toc';
    toc.setAttribute('aria-label', 'On this page');
    const heading = document.createElement('div');
    heading.className = 'toc-heading';
    heading.textContent = 'On this page';
    toc.appendChild(heading);
    const list = document.createElement('ul');
    unique.forEach(function (u) {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = '#' + u.heading.id;
      a.textContent = u.label;
      li.appendChild(a);
      list.appendChild(li);
    });
    toc.appendChild(list);
    document.body.appendChild(toc);
    existingToc = toc;

    const linksById = {};
    list.querySelectorAll('a').forEach(function (a) {
      linksById[a.getAttribute('href').slice(1)] = a;
    });

    observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        const id = entry.target.id;
        const link = linksById[id];
        if (!link) return;
        if (entry.isIntersecting) {
          Object.values(linksById).forEach(function (l) { l.classList.remove('active'); });
          link.classList.add('active');
        }
      });
    }, { rootMargin: '-25% 0px -65% 0px' });

    unique.forEach(function (u) { observer.observe(u.heading); });
  }

  window.__rebuildToc = build;
  build();
})();
