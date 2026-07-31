/* ============================================================================
   AgentGuard — motion & interaction (the site's only client runtime)

   Shipped as an external module (/motion.js) so a strict CSP works with
   `script-src 'self'` — no inline scripts, no 'unsafe-inline'. Plain modern JS,
   no build step, no dependencies, no WebGL. Everything degrades to the final,
   complete state with no JS and under prefers-reduced-motion.
   (Authoring reference for types lives in the PR description; keep this file
   the single runtime source of truth.)
   ========================================================================== */

const root = document.documentElement;
root.classList.add('js');

const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---- Theme toggle (persisted) ------------------------------------------ */
function initTheme() {
  const stored = localStorage.getItem('ag-theme');
  if (stored === 'light' || stored === 'dark') root.dataset.theme = stored;
  document.querySelectorAll('[data-theme-toggle]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const next = root.dataset.theme === 'light' ? 'dark' : 'light';
      root.dataset.theme = next;
      localStorage.setItem('ag-theme', next);
      btn.setAttribute('aria-pressed', String(next === 'light'));
    });
  });
}

/* ---- Copy-to-clipboard (with a tick confirmation) ---------------------- */
function initCopy() {
  document.querySelectorAll('[data-copy]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const text = btn.getAttribute('data-copy') ?? '';
      try {
        await navigator.clipboard.writeText(text);
        btn.classList.add('is-copied');
        const label = btn.querySelector('[data-copy-label]');
        const prev = label ? label.textContent : '';
        if (label) label.textContent = 'Copied';
        window.setTimeout(() => {
          btn.classList.remove('is-copied');
          if (label) label.textContent = prev;
        }, 1600);
      } catch {
        /* clipboard blocked — the command is selectable text, no-op is fine */
      }
    });
  });
}

/* ---- Accessible tabs (CodeTabs) ---------------------------------------- */
function initTabs() {
  document.querySelectorAll('[data-tabs]').forEach((group) => {
    const tabs = Array.from(group.querySelectorAll('[role="tab"]'));
    const panels = Array.from(group.querySelectorAll('[role="tabpanel"]'));
    const select = (i) => {
      tabs.forEach((t, j) => {
        const on = i === j;
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        if (panels[j]) panels[j].toggleAttribute('hidden', !on);
      });
      if (tabs[i]) tabs[i].focus();
    };
    tabs.forEach((tab, i) => {
      tab.addEventListener('click', () => select(i));
      tab.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); select((i + 1) % tabs.length); }
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); select((i - 1 + tabs.length) % tabs.length); }
      });
    });
  });
}

/* ---- Reveal-on-scroll -------------------------------------------------- */
function initReveal() {
  const els = document.querySelectorAll('[data-reveal]');
  if (prefersReduced || !('IntersectionObserver' in window)) {
    els.forEach((el) => el.classList.add('is-in'));
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
      });
    },
    { rootMargin: '0px 0px -12% 0px', threshold: 0.15 },
  );
  els.forEach((el) => io.observe(el));
}

/* ---- Terminal type-out (once) ------------------------------------------ */
function initTerminals() {
  document.querySelectorAll('[data-terminal]').forEach((term) => {
    const cmd = term.querySelector('[data-term-cmd]');
    const body = term.querySelector('[data-term-body]');
    const verdict = term.querySelector('[data-verdict]');
    if (prefersReduced || !cmd) {
      term.classList.add('is-settled');
      if (verdict) verdict.classList.add('is-snapped');
      return;
    }
    const full = cmd.getAttribute('data-term-cmd') ?? cmd.textContent ?? '';
    const run = () => {
      cmd.textContent = '';
      term.classList.add('is-typing');
      let i = 0;
      const tick = () => {
        cmd.textContent = full.slice(0, i);
        i += 1;
        if (i <= full.length) {
          window.setTimeout(tick, 14 + ((i % 3) * 6));
        } else {
          term.classList.remove('is-typing');
          term.classList.add('is-settled');
          if (body) body.setAttribute('data-run', 'true');
          window.setTimeout(() => { if (verdict) verdict.classList.add('is-snapped'); }, 340);
        }
      };
      tick();
    };
    const io = new IntersectionObserver(
      (entries, obs) => { entries.forEach((e) => { if (e.isIntersecting) { run(); obs.disconnect(); } }); },
      { threshold: 0.4 },
    );
    io.observe(term);
  });
}

/* ---- Pipeline sequential activation + SVG connector draw --------------- */
function initPipelines() {
  document.querySelectorAll('[data-pipeline]').forEach((rail) => {
    const steps = Array.from(rail.querySelectorAll('[data-step]'));
    const draws = Array.from(rail.querySelectorAll('[data-draw]'));
    draws.forEach((p) => {
      const len = p.getTotalLength();
      p.style.strokeDasharray = String(len);
      p.style.strokeDashoffset = prefersReduced ? '0' : String(len);
    });
    if (prefersReduced) { steps.forEach((s) => s.classList.add('is-active')); return; }
    const io = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          steps.forEach((s, i) => window.setTimeout(() => s.classList.add('is-active'), i * 260));
          draws.forEach((p, i) => {
            p.style.transition = `stroke-dashoffset 520ms cubic-bezier(0.16,1,0.3,1) ${i * 260 + 120}ms`;
            p.style.strokeDashoffset = '0';
          });
          obs.disconnect();
        });
      },
      { threshold: 0.35 },
    );
    io.observe(rail);
  });
}

/* ---- Sticky nav elevation on scroll ------------------------------------ */
function initNav() {
  const nav = document.querySelector('[data-nav]');
  if (!nav) return;
  const onScroll = () => nav.classList.toggle('is-scrolled', window.scrollY > 8);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
}

initTheme();
initCopy();
initTabs();
initReveal();
initTerminals();
initPipelines();
initNav();
