// Lightweight interactive onboarding tour — zero dependencies.
// Trigger: after welcome modal on first visit, or via "?" nav button.
// localStorage key: myfocalai_toured
(function () {
  'use strict';

  var STORAGE_KEY = 'myfocalai_toured';

  function isMobile() {
    return window.innerWidth < 640;
  }

  var STEPS = [
    {
      target: '#search',
      title: 'Search',
      text: 'Search across titles, sources, and summaries.',
      position: 'bottom',
    },
    {
      target: '#filters',
      title: 'Filters',
      text: 'Sort by source type. Blue badges show new items since your last visit.',
      position: 'bottom',
    },
    {
      // First "New" card, or fall back to first card
      target: function () {
        return (
          document.querySelector('[data-url] .bg-blue-100') ||
          document.querySelector('[data-url]')
        );
      },
      title: 'New items',
      text: 'Blue-highlighted cards are new since you were last here.',
      position: 'top',
    },
    {
      target: function () {
        // Badges may be hidden — fall back to visible nav container
        var badge = document.querySelector('#badge-dashboard, #badge-ccc');
        if (badge && badge.offsetParent !== null) return badge;
        if (isMobile()) return document.getElementById('nav-links-mobile');
        return document.getElementById('nav-links-desktop');
      },
      title: 'Nav badges',
      text: 'Red badges on other pages show new items you haven\u2019t seen yet.',
      position: 'bottom',
    },
    {
      target: function () {
        if (isMobile()) {
          // Open mobile menu so user can see the links
          var mobile = document.getElementById('nav-links-mobile');
          if (mobile && mobile.classList.contains('hidden')) {
            window.toggleMobileMenu();
          }
          return mobile;
        }
        return document.getElementById('nav-links-desktop');
      },
      title: 'Explore pages',
      html: true,
      text: '<b>Trends</b> \u2014 trending GitHub repos, AI tools & agent skills<br><b>CCC</b> \u2014 Claude Code changelogs<br><b>Events</b> \u2014 upcoming AI events<br><b>Leaderboard</b> \u2014 top sources by volume<br><b>Admin</b> \u2014 manage your personal sources',
      position: 'bottom',
    },
  ];

  // ---- DOM helpers ----

  function createElement(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'style' && typeof attrs[k] === 'object') {
          Object.keys(attrs[k]).forEach(function (s) {
            el.style[s] = attrs[k][s];
          });
        } else if (k === 'className') {
          el.className = attrs[k];
        } else {
          el.setAttribute(k, attrs[k]);
        }
      });
    }
    (children || []).forEach(function (c) {
      if (typeof c === 'string') el.appendChild(document.createTextNode(c));
      else if (c) el.appendChild(c);
    });
    return el;
  }

  // ---- Tour engine ----

  var HIGHLIGHT_PROPS = ['position', 'zIndex', 'boxShadow', 'borderRadius'];
  var overlay, tooltip, currentStep;

  function resolveTarget(step) {
    if (typeof step.target === 'function') return step.target();
    // Comma-separated selectors — return first visible one
    var selectors = step.target.split(',');
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i].trim());
      if (el && el.offsetParent !== null) return el;
    }
    // Fallback
    if (step.fallback) return document.querySelector(step.fallback);
    return null;
  }

  function positionTooltip(target, position) {
    var rect = target.getBoundingClientRect();
    var gap = 12;
    var tw = Math.min(320, window.innerWidth - 32);
    tooltip.style.width = tw + 'px';

    // Reset
    tooltip.style.top = '';
    tooltip.style.bottom = '';
    tooltip.style.left = '';
    tooltip.style.right = '';

    var left = Math.max(
      16,
      Math.min(rect.left + rect.width / 2 - tw / 2, window.innerWidth - tw - 16)
    );

    if (position === 'bottom') {
      tooltip.style.top = rect.bottom + gap + window.scrollY + 'px';
      tooltip.style.left = left + 'px';
    } else {
      // top
      tooltip.style.left = left + 'px';
      // Place above the element
      var tooltipH = tooltip.offsetHeight || 120;
      tooltip.style.top = rect.top - gap - tooltipH + window.scrollY + 'px';
    }
  }

  function showStep(index) {
    currentStep = index;
    if (index >= STEPS.length) {
      endTour();
      return;
    }

    var step = STEPS[index];
    var target = resolveTarget(step);

    // Skip step if target missing
    if (!target) {
      showStep(index + 1);
      return;
    }

    // Scroll target into view
    target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Brief delay for scroll to settle
    setTimeout(function () {
      // Save original styles on the element so each target retains its own backup
      target.setAttribute('data-tour-active', 'true');
      target.setAttribute('data-tour-styles', JSON.stringify(
        HIGHLIGHT_PROPS.reduce(function (o, p) { o[p] = target.style[p]; return o; }, {})
      ));

      // Highlight ring on target
      if (!target.style.position || target.style.position === 'static') {
        target.style.position = 'relative';
      }
      target.style.zIndex = '1001';
      target.style.boxShadow = '0 0 0 4px rgba(59,130,246,0.5), 0 0 0 8px rgba(59,130,246,0.15)';
      if (!target.style.borderRadius) target.style.borderRadius = '8px';

      // Build tooltip content
      var stepLabel = (index + 1) + ' / ' + STEPS.length;

      tooltip.innerHTML = '';
      tooltip.appendChild(
        createElement('div', { style: { marginBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' } }, [
          createElement('span', { style: { fontWeight: '600', fontSize: '14px' } }, [step.title]),
          createElement('span', { style: { fontSize: '12px', color: '#9ca3af' } }, [stepLabel]),
        ])
      );
      var desc = createElement('p', { style: { fontSize: '13px', lineHeight: '1.6', color: '#6b7280', margin: '0 0 12px' } });
      if (step.html) {
        desc.innerHTML = step.text;
      } else {
        desc.textContent = step.text;
      }
      tooltip.appendChild(desc);

      var btnRow = createElement('div', { style: { display: 'flex', justifyContent: 'flex-end', gap: '8px' } });
      var skipBtn = createElement(
        'button',
        {
          style: {
            padding: '6px 14px',
            fontSize: '13px',
            borderRadius: '6px',
            border: '1px solid #e5e7eb',
            background: 'transparent',
            color: '#6b7280',
            cursor: 'pointer',
          },
        },
        ['Skip']
      );
      skipBtn.addEventListener('click', endTour);

      var isLast = index === STEPS.length - 1;
      var nextBtn = createElement(
        'button',
        {
          style: {
            padding: '6px 14px',
            fontSize: '13px',
            borderRadius: '6px',
            border: 'none',
            background: '#2563eb',
            color: '#fff',
            cursor: 'pointer',
            fontWeight: '500',
          },
        },
        [isLast ? 'Done' : 'Next']
      );
      nextBtn.addEventListener('click', function () {
        clearHighlight(target);
        showStep(index + 1);
      });

      btnRow.appendChild(skipBtn);
      btnRow.appendChild(nextBtn);
      tooltip.appendChild(btnRow);

      tooltip.style.display = 'block';
      positionTooltip(target, step.position);
      nextBtn.focus();
    }, 200);
  }

  function clearHighlight(el) {
    if (!el) return;
    var raw = el.getAttribute('data-tour-styles');
    var orig = raw ? JSON.parse(raw) : {};
    HIGHLIGHT_PROPS.forEach(function (p) { el.style[p] = orig[p] || ''; });
    el.removeAttribute('data-tour-active');
    el.removeAttribute('data-tour-styles');
  }

  function createOverlay() {
    overlay = createElement('div', {
      id: 'tour-overlay',
      style: {
        position: 'fixed',
        inset: '0',
        background: 'rgba(0,0,0,0.35)',
        zIndex: '1000',
        transition: 'opacity 0.2s',
      },
    });
    overlay.addEventListener('click', endTour);

    tooltip = createElement('div', {
      id: 'tour-tooltip',
      role: 'dialog',
      'aria-label': 'Onboarding tour',
      style: {
        position: 'absolute',
        zIndex: '1002',
        background: '#fff',
        borderRadius: '12px',
        padding: '16px',
        boxShadow: '0 8px 30px rgba(0,0,0,0.18)',
        display: 'none',
        maxWidth: '320px',
        color: '#111827',
      },
    });

    // Dark mode support
    if (document.documentElement.classList.contains('dark')) {
      tooltip.style.background = '#1f2937';
      tooltip.style.color = '#e5e7eb';
    }

    document.body.appendChild(overlay);
    document.body.appendChild(tooltip);

    // Escape key closes the tour
    document.addEventListener('keydown', handleKeyDown);
  }

  function handleKeyDown(e) {
    if (e.key === 'Escape') endTour();
  }

  function endTour() {
    // Clean up all highlighted elements
    var actives = document.querySelectorAll('[data-tour-active]');
    actives.forEach(function (el) { clearHighlight(el); });

    // Close mobile menu if we opened it during the tour
    var mobile = document.getElementById('nav-links-mobile');
    if (mobile && !mobile.classList.contains('hidden')) {
      window.toggleMobileMenu();
    }

    document.removeEventListener('keydown', handleKeyDown);

    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    if (tooltip && tooltip.parentNode) tooltip.parentNode.removeChild(tooltip);
    overlay = null;
    tooltip = null;

    localStorage.setItem(STORAGE_KEY, 'true');
  }

  // ---- Public API ----

  window.startTour = function () {
    if (overlay) return; // already running
    createOverlay();
    showStep(0);
  };

  // Auto-start after welcome modal closes on first visit
  window.startTourAfterWelcome = function () {
    if (localStorage.getItem(STORAGE_KEY) === 'true') return;
    // Slight delay so the page is fully rendered
    setTimeout(window.startTour, 600);
  };

  // Auto-start if navigated here via ?tour=1 (from "?" button on other pages)
  if (new URLSearchParams(window.location.search).get('tour') === '1') {
    history.replaceState(null, '', window.location.pathname);
    // Wait for feed to render before starting
    setTimeout(window.startTour, 800);
  }
})();
