// Trade Targets picker: pick a player on another roster, render the
// pre-computed acquisition packages. Mirrors the server-side _target_card /
// _packages macros, including the per-target timeline override toggle.

(function () {
  const select = document.getElementById("target-select");
  const result = document.getElementById("target-result");
  const indexEl = document.getElementById("target-index");
  if (!indexEl) return;

  let index = {};
  try {
    index = JSON.parse(indexEl.textContent);
  } catch (e) {
    return;
  }

  const TIMELINES = ["win-now", "balanced", "rebuild"];

  function money(v) {
    if (v === null || v === undefined) return "—";
    return v.toLocaleString("en-US");
  }
  function signed(v) {
    if (v === null || v === undefined) return "";
    return (v > 0 ? "+" : "") + v.toLocaleString("en-US");
  }
  function cls(v) {
    return v > 0 ? "good" : (v < 0 ? "bad" : "muted");
  }
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function sendChip(p) {
    const tag = p.is_pick
      ? '<span class="pos-tag pick-tag">PICK</span>'
      : '<span class="pos-tag">' + esc(p.position) + (p.team ? " · " + esc(p.team) : "") + "</span>";
    return (
      '<span class="target-send-player' + (p.is_pick ? " is-pick" : "") + '">' +
      esc(p.name) + " " + tag +
      ' <span class="muted small">' + money(p.dynasty_value) + "</span></span>"
    );
  }

  // Mirrors the _packages(packages, timeline) Jinja macro.
  function packagesHtml(packages, timeline) {
    if (!packages || !packages.length) {
      let why;
      if (timeline === "win-now") why = "as a win-now team (they won't downgrade their lineup)";
      else if (timeline === "rebuild") why = "even as a rebuilder";
      else why = "as a balanced team";
      return '<div class="target-tough muted small">No value-fair package clears their bar ' + why + ".</div>";
    }
    const items = packages.map(function (pkg) {
      const sends = pkg.send.map(sendChip).join(" ");
      return (
        '<div class="target-package">' +
        '<div class="target-package-send"><span class="muted small">You send</span> ' + sends + "</div>" +
        '<div class="target-package-meta">' +
        '<span>Your net lineup: <span class="' + cls(pkg.my_lineup_change) + '">' + signed(pkg.my_lineup_change) + "</span></span>" +
        '<span>Their lineup: <span class="' + cls(pkg.their_lineup_change) + '">' + signed(pkg.their_lineup_change) + "</span></span>" +
        '<span>Value gap: <span class="' + (pkg.my_value_delta >= 0 ? "good" : "bad") + '">' + signed(pkg.my_value_delta) + "</span></span>" +
        "</div>" +
        '<div class="target-package-pitch">' + esc(pkg.pitch) + "</div>" +
        "</div>"
      );
    }).join("");
    return (
      '<div class="target-packages"><div class="target-packages-label">What it takes</div>' +
      items + "</div>"
    );
  }

  // Mirrors the .timeline-toggle markup in _target_card. The inferred dot
  // stays pinned to the inferred timeline regardless of which is active.
  function toggleHtml(inferred) {
    const btns = TIMELINES.map(function (tl) {
      const isInferred = tl === inferred;
      return (
        '<button type="button" data-timeline="' + tl + '" class="' + (isInferred ? "active" : "") + '">' +
        tl + (isInferred ? ' <span class="inferred-dot" title="Inferred from their rankings">•</span>' : "") +
        "</button>"
      );
    }).join("");
    return (
      '<div class="timeline-toggle" role="tablist" aria-label="Assume their timeline">' +
      '<span class="timeline-toggle-label">Treat them as:</span>' + btns + "</div>"
    );
  }

  // Mirrors the _target_card(t) Jinja macro.
  function cardHtml(t) {
    const p = t.player;
    const inferred = t.inferred_trajectory;
    const posTag = '<span class="pos-tag">' + esc(p.position) + (p.team ? " · " + esc(p.team) : "") + "</span>";
    const inj = p.injury_status ? ' <span class="injury Q">' + esc(p.injury_status) + "</span>" : "";
    const age = p.age ? " · age " + Math.round(p.age) : "";
    return (
      '<section class="target-card" data-target-id="' + esc(p.sleeper_id) + '">' +
      '<div class="target-header">' +
      '<div class="target-player"><span class="target-name">' + esc(p.name) + "</span> " +
      posTag + inj +
      ' <span class="muted small">dyn ' + money(p.dynasty_value) + age + "</span></div>" +
      '<div class="target-meta muted small">on <strong>' + esc(t.owner_team) + "</strong>" +
      ' &middot; <span class="good">+' + money(t.my_lineup_improvement) + "</span> to your lineup</div>" +
      "</div>" +
      toggleHtml(inferred) +
      '<div class="target-packages-host">' +
      packagesHtml(t.packages_by_timeline[inferred], inferred) +
      "</div>" +
      "</section>"
    );
  }

  // Picker: render the chosen player's card.
  if (select && result) {
    select.addEventListener("change", function () {
      const id = select.value;
      if (!id || !index[id]) {
        result.innerHTML = "";
        return;
      }
      result.innerHTML = cardHtml(index[id]);
      result.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  // Delegated timeline toggle — works for both the picker result and the
  // server-rendered featured cards. Re-renders only that card's packages.
  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest(".timeline-toggle button");
    if (!btn) return;
    const card = btn.closest(".target-card");
    if (!card) return;
    const id = card.getAttribute("data-target-id");
    const entry = index[id];
    if (!entry) return;
    const tl = btn.getAttribute("data-timeline");

    card.querySelectorAll(".timeline-toggle button").forEach(function (b) {
      b.classList.toggle("active", b === btn);
    });

    const host = card.querySelector(".target-packages-host");
    if (host) host.innerHTML = packagesHtml(entry.packages_by_timeline[tl], tl);
  });
})();
