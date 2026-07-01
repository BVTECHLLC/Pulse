/* v0.75 White-label branding — applies the configured brand to any page.
   Public endpoint, safe display values only. Fails silently on error. */
(function () {
  function esc(s) {
    return (s == null ? '' : String(s)).replace(/[&<>"]/g, function (m) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[m];
    });
  }
  function apply(b) {
    if (!b) return;
    var root = document.documentElement;
    if (b.accent) {
      root.style.setProperty('--accent', b.accent);
      root.style.setProperty('--brand', b.accent);
    }
    var name = b.app_name || ((b.company || '') + ' ' + (b.product || '')).trim();
    if (name) {
      // Keep any page-specific suffix (e.g. "— Client Portal").
      document.title = document.title.replace(/BVTech OpsPilot|OpsPilot/g, name) || name;
    }
    document.querySelectorAll('.wm').forEach(function (el) {
      el.innerHTML = '<b>' + esc(b.company || '') + '</b> ' + esc(b.product || '');
    });
    if (b.logo_url) {
      document.querySelectorAll('.lockup img, .topbar img').forEach(function (img) { img.src = b.logo_url; });
    }
  }
  try {
    fetch('/api/branding').then(function (r) { return r.ok ? r.json() : null; }).then(apply).catch(function () {});
  } catch (e) {}
})();
