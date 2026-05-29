// Trade Targets picker: pick a player on another roster, render the
// pre-computed acquisition packages. Mirrors the server-side _target_card macro.

(function () {
  const select = document.getElementById("target-select");
  const result = document.getElementById("target-result");
  const indexEl = document.getElementById("target-index");
  if (!select || !result || !indexEl) return;

  let index = {};
  try {
    index = JSON.parse(indexEl.textContent);
  } catch (e) {
    return;
  }

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

  function packageHtml(pkg) {
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
  }

  function cardHtml(t) {
    const p = t.player;
    const posTag = '<span class="pos-tag">' + esc(p.position) + (p.team ? " · " + esc(p.team) : "") + "</span>";
    const inj = p.injury_status ? ' <span class="injury Q">' + esc(p.injury_status) + "</span>" : "";
    const age = p.age ? " · age " + Math.round(p.age) : "";
    let body;
    if (t.packages && t.packages.length) {
      body =
        '<div class="target-packages"><div class="target-packages-label">What it takes</div>' +
        t.packages.map(packageHtml).join("") + "</div>";
    } else {
      const why = t.owner_trajectory === "win-now"
        ? "(they're competing now and won't downgrade their lineup)"
        : "clears their bar right now";
      body = '<div class="target-tough muted small">Tough to pry loose — no value-fair package ' + why + ".</div>";
    }
    return (
      '<section class="target-card"><div class="target-header">' +
      '<div class="target-player"><span class="target-name">' + esc(p.name) + "</span> " +
      posTag + inj +
      ' <span class="muted small">dyn ' + money(p.dynasty_value) + age + "</span></div>" +
      '<div class="target-meta muted small">on <strong>' + esc(t.owner_team) + "</strong> " +
      '<span class="trajectory-badge trajectory-' + t.owner_trajectory + '">' + t.owner_trajectory + "</span>" +
      ' &middot; <span class="good">+' + money(t.my_lineup_improvement) + "</span> to your lineup</div>" +
      "</div>" + body + "</section>"
    );
  }

  select.addEventListener("change", function () {
    const id = select.value;
    if (!id || !index[id]) {
      result.innerHTML = "";
      return;
    }
    result.innerHTML = cardHtml(index[id]);
    result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
})();
