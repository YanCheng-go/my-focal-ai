// Shared badge computation for nav bar notification badges.
// Reads hidden_source_types and hidden_sources from config.json.
// Usage: include <script src="badges.js"></script> in each page.
//
// Two modes:
// 1. Manual: call computeBadges(items, config, currentPage) with pre-loaded data
// 2. Auto: if no manual call within 100ms, fetches data.json + config.json
//
// currentPage should be 'dashboard', 'trends', or 'ccc' — only that page's
// last-seen timestamp is updated. Pass null for pages without a badge.

(function() {
    var PAGES = ['dashboard', 'trends', 'ccc'];

    function _migrateLastSeen() {
        var old = localStorage.getItem('ainews_last_seen');
        if (old && !localStorage.getItem('ainews_last_seen_dashboard')) {
            PAGES.forEach(function(p) {
                localStorage.setItem('ainews_last_seen_' + p, old);
            });
            localStorage.removeItem('ainews_last_seen');
        }
    }

    function _compute(items, config, currentPage) {
        _migrateLastSeen();

        var hiddenTypes = (config && config.hidden_source_types) || [];
        var hiddenSources = (config && config.hidden_sources) || [];
        var counts = {dashboard: 0, ccc: 0};

        // First visit: initialise all timestamps and return (no badges to show)
        var hasAny = PAGES.some(function(p) {
            return localStorage.getItem('ainews_last_seen_' + p);
        });
        if (!hasAny) {
            var now = new Date().toISOString();
            PAGES.forEach(function(p) {
                localStorage.setItem('ainews_last_seen_' + p, now);
            });
            return;
        }

        var lastSeenDates = {};
        PAGES.forEach(function(p) {
            var ts = localStorage.getItem('ainews_last_seen_' + p);
            lastSeenDates[p] = ts ? new Date(ts) : null;
        });

        (items || []).forEach(function(item) {
            var d = new Date(item.fetched_at || item.published_at);

            if (lastSeenDates.dashboard && d > lastSeenDates.dashboard) {
                if (!hiddenTypes.includes(item.source_type) && !hiddenSources.includes(item.source_name))
                    counts.dashboard++;
            }
            // trends badge disabled — count was always noisy (50)
            if (lastSeenDates.ccc && d > lastSeenDates.ccc) {
                if (hiddenSources.includes(item.source_name) && item.source_type !== 'github_trending' && item.source_type !== 'github_trending_history')
                    counts.ccc++;
            }
        });

        Object.keys(counts).forEach(function(p) {
            var label = counts[p] > 99 ? '99+' : String(counts[p]);
            ['badge-' + p, 'badge-' + p + '-m'].forEach(function(id) {
                var el = document.getElementById(id);
                if (el && counts[p] > 0) {
                    el.textContent = label;
                    el.classList.remove('hidden');
                }
            });
        });

        // Expose the cutoff for the current page before updating it
        if (currentPage && lastSeenDates[currentPage]) {
            _lastSeenCutoff = lastSeenDates[currentPage];
        }

        // Only update the current page's last-seen timestamp
        if (currentPage && PAGES.indexOf(currentPage) !== -1) {
            localStorage.setItem('ainews_last_seen_' + currentPage, new Date().toISOString());
        }
    }

    // Detect current page from URL path
    function _detectPage() {
        var path = window.location.pathname;
        if (path === '/' || path === '/index.html' || path.endsWith('/index.html')) return 'dashboard';
        if (path.includes('trends')) return 'trends';
        if (path.includes('ccc')) return 'ccc';
        return null;
    }

    // Expose last-seen cutoff for the current page so renderers can highlight new items.
    // Set inside _compute before the timestamp is updated.
    var _lastSeenCutoff = null;
    window.isNewItem = function(item) {
        if (!_lastSeenCutoff) return false;
        var d = new Date(item.fetched_at || item.published_at);
        return d > _lastSeenCutoff;
    };

    // Auto mode: if no one calls computeBadges within 100ms, fetch and compute
    var called = false;
    window.computeBadges = function(items, config, currentPage) { called = true; _compute(items, config, currentPage); };

    setTimeout(function() {
        if (called) return;
        var page = _detectPage();
        var configP = window.getConfig ? window.getConfig() : fetch('config.json').then(function(r) { return r.ok ? r.json() : {}; }).catch(function() { return {}; });
        Promise.all([
            fetch('data.json').then(function(r) { return r.json(); }),
            configP,
        ]).then(function(results) {
            _compute(results[0].items || [], results[1], page);
        }).catch(function() {});
    }, 100);
})();
