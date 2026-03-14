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
        var counts = {dashboard: 0, trends: 0, ccc: 0};

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
            var d = new Date(item.fetched_at);

            if (lastSeenDates.dashboard && d > lastSeenDates.dashboard) {
                if (!hiddenTypes.includes(item.source_type) && !hiddenSources.includes(item.source_name))
                    counts.dashboard++;
            }
            if (lastSeenDates.trends && d > lastSeenDates.trends) {
                if (item.source_type === 'github_trending' || item.source_type === 'github_trending_history')
                    counts.trends++;
            }
            if (lastSeenDates.ccc && d > lastSeenDates.ccc) {
                if (hiddenSources.includes(item.source_name) && item.source_type !== 'github_trending' && item.source_type !== 'github_trending_history')
                    counts.ccc++;
            }
        });

        Object.keys(counts).forEach(function(p) {
            var el = document.getElementById('badge-' + p);
            if (el && counts[p] > 0) {
                el.textContent = counts[p] > 99 ? '99+' : counts[p];
                el.classList.remove('hidden');
            }
        });

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

    window.computeBadges = function(items, config, currentPage) { _compute(items, config, currentPage); };

    // Auto mode: if no one calls computeBadges within 100ms, fetch and compute
    var called = false;
    window.computeBadges = function(items, config, currentPage) { called = true; _compute(items, config, currentPage); };

    setTimeout(function() {
        if (called) return;
        var page = _detectPage();
        Promise.all([
            fetch('data.json').then(function(r) { return r.json(); }),
            fetch('config.json').then(function(r) { return r.json(); }).catch(function() { return {}; }),
        ]).then(function(results) {
            _compute(results[0].items || [], results[1], page);
        }).catch(function() {});
    }, 100);
})();
