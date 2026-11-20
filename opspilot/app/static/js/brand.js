/* v2.2 White-label branding — applies the configured brand to any page.
   Public endpoint, safe display values only. Fails silently on error.

   Beyond the name/logo/accent, this fills data-brand hooks so a page's footer
   and inline copy become fully the operator's (or a reseller's): put
   data-brand="company|year|address|support-email|support-phone|website|note|
   powered" on any element and it's populated here; empty values hide the
   element (and its [data-brand-wrap] ancestor) so nothing dangles. */
(function () {
  function esc(s) {
    return (s == null ? '' : String(s)).replace(/[&<>"]/g, function (m) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[m];
    });
  }
  function hideWrap(el) {
    var w = el.closest ? el.closest('[data-brand-wrap]') : null;
    (w || el).style.display = 'none';
  }
  function fill(sel, text, href) {
    document.querySelectorAll(sel).forEach(function (el) {
      if (text == null || text === '') { hideWrap(el); return; }
      if (href != null) { el.setAttribute('href', href); }
      el.textContent = text;
    });
  }
  function apply(b) {
    if (!b) return;
    var root = document.documentElement;
    if (b.accent) {
      root.style.setProperty('--accent', b.accent);
      root.style.setProperty('--brand', b.accent);
    }
    if (b.accent2) {
      root.style.setProperty('--accent2', b.accent2);
      root.style.setProperty('--brand2', b.accent2);
    }
    var name = b.app_name || ((b.company || '') + ' ' + (b.product || '')).trim();
    if (name) {
      document.title = document.title.replace(/BVTech OpsPilot|OpsPilot/g, name) || name;
    }
    document.querySelectorAll('.wm').forEach(function (el) {
      el.innerHTML = '<b>' + esc(b.company || '') + '</b> ' + esc(b.product || '');
    });
    if (b.logo_url) {
      document.querySelectorAll('.lockup img, .topbar img').forEach(function (img) { img.src = b.logo_url; });
    }
    // Inline + footer hooks.
    fill('[data-brand="company"]', b.company || '');
    fill('[data-brand="year"]', String(new Date().getFullYear()));
    fill('[data-brand="address"]', b.company_address || '');
    fill('[data-brand="support-email"]', b.support_email || '',
         b.support_email ? ('mailto:' + b.support_email) : null);
    fill('[data-brand="support-phone"]', b.support_phone || '',
         b.support_phone ? ('tel:' + String(b.support_phone).replace(/[^0-9+]/g, '')) : null);
    fill('[data-brand="website"]', (b.website_url || '').replace(/^https?:\/\//, ''),
         b.website_url || null);
    fill('[data-brand="note"]', b.footer_note || '');
    // "Powered by" credit — shown only when the toggle is on.
    document.querySelectorAll('[data-brand="powered"]').forEach(function (el) {
      if (b.powered_by) { el.textContent = 'Powered by ' + (b.company || ''); el.style.display = ''; }
      else { hideWrap(el); }
    });
    // Operator flourishes (e.g. a scripture/tagline) — hidden in full
    // white-label mode so a reseller's portal stays clean.
    document.querySelectorAll('[data-brand-flourish]').forEach(function (el) {
      if (!b.powered_by) { el.style.display = 'none'; }
    });
  }
  try {
    fetch('/api/branding').then(function (r) { return r.ok ? r.json() : null; }).then(apply).catch(function () {});
  } catch (e) {}
})();
