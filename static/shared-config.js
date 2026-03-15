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
