// Shared config.json loader — single fetch, cached promise.
// Usage: getConfig().then(function(config) { ... })
(function() {
    var _promise = null;
    window.getConfig = function() {
        if (!_promise) {
            _promise = fetch('config.json')
                .then(function(r) { return r.ok ? r.json() : {}; })
                .catch(function() { return {}; });
        }
        return _promise;
    };
})();

// Shared source form constants and validation.
window.FIELD_PLACEHOLDERS = {
    handle: { twitter: '@username', luma: 'event-handle' },
    channel_id: { youtube: 'UCxxxxxxx (use Quick Add to auto-fill)' },
    name: { _default: 'Display name for this source' },
    url: { rss: 'https://example.com/feed.xml', arxiv: 'https://export.arxiv.org/api/query?...', leaderboard: 'https://...', event_links: 'https://...' },
    route: { rsshub: 'twitter/user/karpathy (see docs.rsshub.app)' },
    query: { arxiv_queries: 'ti:LLM+AND+cat:cs.AI' },
    scraper: { events: 'anthropic or google' },
};

window.TYPE_HINTS = {
    twitter: 'Tip: paste a Twitter/X profile URL above to auto-fill.',
    youtube: 'Tip: paste any YouTube video or channel URL above to auto-fill.',
    rss: 'Tip: paste any blog URL above \u2014 RSS feed will be auto-discovered.',
    arxiv: 'Tip: paste an arXiv paper or category URL above to auto-fill.',
    rsshub: 'Tip: paste an rsshub.app URL above, or enter a route from docs.rsshub.app.',
    luma: 'Tip: paste a lu.ma URL above to auto-fill.',
    events: 'Scraper must be one of: anthropic, google.',
    github_trending: 'Fetches daily trending repos from trendshift.io.',
    arxiv_queries: 'Uses the arXiv API query syntax. Example: ti:LLM+AND+cat:cs.AI',
};

window.validateSourceFields = function(sourceType, config, name) {
    if (sourceType === 'youtube') {
        var cid = config.channel_id || '';
        if (!/^UC[\w-]{22}$/.test(cid)) {
            return 'Invalid YouTube channel_id: must start with "UC" followed by 22 characters. Use Quick Add to paste a URL.';
        }
    }
    if (sourceType === 'twitter') {
        var handle = config.handle || '';
        if (!/^[A-Za-z0-9_]{1,15}$/.test(handle)) {
            return 'Invalid Twitter handle: 1-15 alphanumeric characters or underscores, without @.';
        }
    }
    if (['rss', 'arxiv', 'leaderboard', 'event_links'].indexOf(sourceType) !== -1) {
        var url = config.url || '';
        if (!/^https?:\/\/.+/.test(url)) {
            return 'Invalid URL: must start with http:// or https://';
        }
    }
    if (sourceType === 'events') {
        var scraper = config.scraper || '';
        if (scraper !== 'anthropic' && scraper !== 'google') {
            return 'Invalid scraper: must be "anthropic" or "google".';
        }
    }
    if (!name && sourceType !== 'twitter' && sourceType !== 'luma') {
        return 'Name is required.';
    }
    return null;
};
