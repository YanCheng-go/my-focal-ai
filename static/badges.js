// Shared badge computation for nav bar notification badges.
// Reads hidden_source_types and hidden_sources from config.json.
// Usage: include <script src="badges.js"></script> in each page.
//
// Two modes:
// 1. Auto: fetches data.json + config.json and computes badges (default)
// 2. Manual: call computeBadges(items, config) with pre-loaded data

(function() {
    function _compute(items, config) {
        var lastSeen = localStorage.getItem('ainews_last_seen');
        if (!lastSeen) {
            localStorage.setItem('ainews_last_seen', new Date().toISOString());
            return;
        }
        var lastSeenDate = new Date(lastSeen);
        var hiddenTypes = (config && config.hidden_source_types) || [];
        var hiddenSources = (config && config.hidden_sources) || [];
        var counts = {dashboard: 0, trends: 0, ccc: 0};
        (items || []).forEach(function(item) {
            var d = new Date(item.published_at || item.fetched_at);
            if (d > lastSeenDate) {
                if (!hiddenTypes.includes(item.source_type) && !hiddenSources.includes(item.source_name)) counts.dashboard++;
                if (item.source_type === 'github_trending' || item.source_type === 'github_trending_history') counts.trends++;
                if (hiddenSources.includes(item.source_name) && item.source_type !== 'github_trending' && item.source_type !== 'github_trending_history') counts.ccc++;
            }
        });
        Object.keys(counts).forEach(function(p) {
            var el = document.getElementById('badge-' + p);
            if (el && counts[p] > 0) {
                el.textContent = counts[p] > 99 ? '99+' : counts[p];
                el.classList.remove('hidden');
            }
        });
        localStorage.setItem('ainews_last_seen', new Date().toISOString());
    }

    // Expose for manual use (index.html calls this with pre-loaded data)
    window.computeBadges = function(items, config) { _compute(items, config); };

    // Auto mode: if no one calls computeBadges within 100ms, fetch and compute
    var called = false;
    var origCompute = window.computeBadges;
    window.computeBadges = function(items, config) { called = true; _compute(items, config); };

    setTimeout(function() {
        if (called) return;
        // Auto-fetch both data.json and config.json
        Promise.all([
            fetch('data.json').then(function(r) { return r.json(); }),
            fetch('config.json').then(function(r) { return r.json(); }).catch(function() { return {}; }),
        ]).then(function(results) {
            _compute(results[0].items || [], results[1]);
        }).catch(function() {});
    }, 100);
})();
