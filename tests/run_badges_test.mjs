// Run badges.js tests in a minimal DOM environment using Node.js
// No dependencies needed — we simulate just enough of the browser API.

import { readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── Minimal DOM + localStorage stubs ──
const store = {};
const localStorage = {
    getItem(k) { return store[k] ?? null; },
    setItem(k, v) { store[k] = String(v); },
    removeItem(k) { delete store[k]; },
};

const elements = {};
function makeEl(id) {
    return {
        id,
        _textContent: '',
        get textContent() { return this._textContent; },
        set textContent(v) { this._textContent = String(v); },
        classList: {
            _set: new Set(['hidden']),
            add(c) { this._set.add(c); },
            remove(c) { this._set.delete(c); },
            contains(c) { return this._set.has(c); },
        },
    };
}
['badge-dashboard', 'badge-trends', 'badge-ccc'].forEach(id => { elements[id] = makeEl(id); });

const window = { location: { pathname: '/index.html' } };
const document = {
    getElementById(id) { return elements[id] || null; },
    addEventListener() {},
};

// Inject globals
globalThis.window = window;
globalThis.document = document;
globalThis.localStorage = localStorage;
globalThis.setTimeout = () => {}; // suppress auto-mode (tests call computeBadges explicitly)
globalThis.fetch = () => Promise.reject(new Error('no network in test'));

// ── Load badges.js ──
const badgesCode = readFileSync(join(__dirname, '..', 'static', 'badges.js'), 'utf-8');
const fn = new Function('window', 'document', 'localStorage', 'setTimeout', 'fetch', badgesCode);
fn(window, document, localStorage, globalThis.setTimeout, globalThis.fetch);

// Bring globals to local scope
const { computeBadges, isNewItem } = window;

// ── Test harness ──
let passed = 0, failed = 0;
function assert(condition, name) {
    if (condition) {
        console.log(`  PASS: ${name}`);
        passed++;
    } else {
        console.log(`  FAIL: ${name}`);
        failed++;
    }
}

function resetStorage() {
    Object.keys(store).forEach(k => delete store[k]);
}

function resetBadges() {
    Object.values(elements).forEach(el => {
        el.textContent = '';
        el.classList._set = new Set(['hidden']);
    });
}

// ── Items ──
const oldItem = { published_at: '2026-03-10T00:00:00Z', source_type: 'rss', source_name: 'Test' };
const newItem = { published_at: '2026-03-15T12:00:00Z', source_type: 'rss', source_name: 'Test' };
const trendingItem = { published_at: '2026-03-15T12:00:00Z', source_type: 'github_trending', source_name: 'Trending' };

// ── Tests ──
console.log('\nbadges.js tests\n');

// 1
resetStorage();
assert(isNewItem(newItem) === false, 'isNewItem returns false before any computeBadges call');

// 2 — First visit
resetStorage(); resetBadges();
computeBadges([newItem], {}, 'dashboard');
assert(isNewItem(newItem) === false, 'First visit: isNewItem returns false (no prior cutoff)');

// 3 — Second visit
resetBadges();
store['ainews_last_seen_dashboard'] = '2026-03-12T00:00:00Z';
store['ainews_last_seen_trends'] = '2026-03-12T00:00:00Z';
store['ainews_last_seen_ccc'] = '2026-03-12T00:00:00Z';
computeBadges([oldItem, newItem], {}, 'dashboard');
assert(isNewItem(newItem) === true, 'Second visit: item after last-seen is new');
assert(isNewItem(oldItem) === false, 'Second visit: item before last-seen is not new');

// 4 — Badge count
const badge = elements['badge-dashboard'];
assert(badge.textContent === '1', 'Badge count shows 1 new dashboard item');
assert(!badge.classList.contains('hidden'), 'Badge element is visible');

// 5 — After visiting, last-seen updated
resetBadges();
computeBadges([oldItem, newItem], {}, 'dashboard');
assert(isNewItem(newItem) === false, 'After visit: previously new item is no longer new');
assert(elements['badge-dashboard'].classList.contains('hidden'), 'Badge hidden after revisit');

// 6 — fetched_at fallback
resetBadges();
store['ainews_last_seen_dashboard'] = '2026-03-12T00:00:00Z';
store['ainews_last_seen_trends'] = '2026-03-12T00:00:00Z';
store['ainews_last_seen_ccc'] = '2026-03-12T00:00:00Z';
const itemNoPublished = { fetched_at: '2026-03-15T12:00:00Z', source_type: 'rss', source_name: 'Test' };
computeBadges([itemNoPublished], {}, 'dashboard');
assert(isNewItem(itemNoPublished) === true, 'isNewItem falls back to fetched_at');

// 7 — Independent page cutoffs
resetBadges();
store['ainews_last_seen_dashboard'] = '2026-03-14T00:00:00Z';
store['ainews_last_seen_trends'] = '2026-03-10T00:00:00Z';
store['ainews_last_seen_ccc'] = '2026-03-14T00:00:00Z';
computeBadges([trendingItem], {}, 'trends');
assert(isNewItem(trendingItem) === true, 'Trends page: item after Mar 10 cutoff is new');

// 8 — hidden_source_types excluded from badge
resetBadges();
store['ainews_last_seen_dashboard'] = '2026-03-12T00:00:00Z';
store['ainews_last_seen_trends'] = '2026-03-12T00:00:00Z';
store['ainews_last_seen_ccc'] = '2026-03-12T00:00:00Z';
const hiddenItem = { published_at: '2026-03-15T12:00:00Z', source_type: 'github_trending', source_name: 'Repo' };
computeBadges([hiddenItem], { hidden_source_types: ['github_trending'] }, 'dashboard');
assert(elements['badge-dashboard'].classList.contains('hidden'), 'Hidden source_type excluded from dashboard badge');

// 9 — Migration
resetStorage(); resetBadges();
store['ainews_last_seen'] = '2026-03-11T00:00:00Z';
computeBadges([newItem], {}, 'dashboard');
assert(!('ainews_last_seen' in store), 'Migration removes old key');
assert(isNewItem(newItem) === true, 'After migration: new items correctly identified');

// ── Summary ──
console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
