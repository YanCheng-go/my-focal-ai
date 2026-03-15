import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.1.0/index.js";

// Custom metrics
const errorRate = new Rate("errors");
const pageLoadTrend = new Trend("page_load_duration", true);
const apiTrend = new Trend("api_duration", true);

// Configuration via env vars:
//   k6 run -e BASE_URL=... -e PROFILE=smoke tests/perf/load-test.js
const BASE_URL = __ENV.BASE_URL || "https://myfocalai.vercel.app";
const PROFILE = __ENV.PROFILE || "load";
const IS_LOCAL = BASE_URL.includes("localhost") || BASE_URL.includes("127.0.0.1");

// --- Profiles ---
const profiles = {
  smoke: {
    scenarios: {
      browse: {
        executor: "ramping-vus",
        startVUs: 1,
        stages: [{ duration: "10s", target: 1 }],
      },
    },
  },
  load: {
    scenarios: {
      browse: {
        executor: "ramping-vus",
        startVUs: 1,
        stages: [
          { duration: "30s", target: 10 },
          { duration: "1m", target: 20 },
          { duration: "30s", target: 0 },
        ],
      },
    },
  },
  stress: {
    scenarios: {
      browse: {
        executor: "ramping-vus",
        startVUs: 1,
        stages: [
          { duration: "30s", target: 20 },
          { duration: "1m", target: 50 },
          { duration: "1m", target: 80 },
          { duration: "30s", target: 0 },
        ],
      },
    },
  },
};

const profile = profiles[PROFILE];
if (!profile) {
  throw new Error(`Unknown profile "${PROFILE}". Use: smoke, load, stress`);
}

export const options = {
  ...profile,
  thresholds: {
    http_req_duration: ["p(95)<2000"],
    errors: ["rate<0.05"],
    page_load_duration: ["p(95)<3000"],
    api_duration: ["p(95)<1500"],
  },
};

// Save JSON summary when RESULTS_DIR is set
export function handleSummary(data) {
  const out = { stdout: textSummary(data, { indent: " ", enableColors: true }) };
  if (__ENV.RESULTS_DIR) {
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    out[`${__ENV.RESULTS_DIR}/${PROFILE}-${ts}.json`] = JSON.stringify(data, null, 2);
  }
  return out;
}

// Simulate a user browsing the site
export default function () {
  // API endpoints only exist on local FastAPI, not on Vercel static site
  const actions = [
    { weight: 40, fn: browseDashboard },
    { weight: 15, fn: browseTrends },
    { weight: 10, fn: browseEvents },
    { weight: 10, fn: browseCCC },
    { weight: 5, fn: browseLeaderboard },
  ];
  if (IS_LOCAL) {
    actions.push(
      { weight: 10, fn: fetchApiItems },
      { weight: 5, fn: fetchDigest },
      { weight: 5, fn: fetchBadgeCounts },
    );
  }

  const total = actions.reduce((sum, a) => sum + a.weight, 0);
  let rand = Math.random() * total;
  for (const action of actions) {
    rand -= action.weight;
    if (rand <= 0) {
      action.fn();
      break;
    }
  }

  sleep(Math.random() * 2 + 1); // 1-3s think time
}

// --- Page scenarios ---

function browseDashboard() {
  group("Dashboard", () => {
    const page = http.get(`${BASE_URL}/`);
    pageLoadTrend.add(page.timings.duration);
    checkResponse(page, "dashboard page");

    const responses = http.batch([
      ["GET", `${BASE_URL}/data.json`],
      ["GET", `${BASE_URL}/config.json`],
      ["GET", `${BASE_URL}/nav.js`],
      ["GET", `${BASE_URL}/badges.js`],
    ]);
    for (const res of responses) {
      checkResponse(res, "dashboard asset");
    }
  });
}

function browseTrends() {
  group("Trends", () => {
    const page = http.get(`${BASE_URL}/trends`);
    pageLoadTrend.add(page.timings.duration);
    checkResponse(page, "trends page");

    const data = http.get(`${BASE_URL}/data.json`);
    checkResponse(data, "trends data");
  });
}

function browseEvents() {
  group("Events", () => {
    const page = http.get(`${BASE_URL}/events`);
    pageLoadTrend.add(page.timings.duration);
    checkResponse(page, "events page");

    const data = http.get(`${BASE_URL}/data.json`);
    checkResponse(data, "events data");
  });
}

function browseCCC() {
  group("CCC", () => {
    const page = http.get(`${BASE_URL}/ccc`);
    pageLoadTrend.add(page.timings.duration);
    checkResponse(page, "ccc page");

    const data = http.get(`${BASE_URL}/data.json`);
    checkResponse(data, "ccc data");
  });
}

function browseLeaderboard() {
  group("Leaderboard", () => {
    const page = http.get(`${BASE_URL}/leaderboard`);
    pageLoadTrend.add(page.timings.duration);
    checkResponse(page, "leaderboard page");

    const config = http.get(`${BASE_URL}/config.json`);
    checkResponse(config, "leaderboard config");
  });
}

// --- API scenarios ---

function fetchApiItems() {
  group("API: /api/items", () => {
    const res1 = http.get(`${BASE_URL}/api/items?limit=50&offset=0`);
    apiTrend.add(res1.timings.duration);
    checkResponse(res1, "api items default");

    const res2 = http.get(`${BASE_URL}/api/items?limit=50&offset=50`);
    apiTrend.add(res2.timings.duration);
    checkResponse(res2, "api items page 2");
  });
}

function fetchDigest() {
  group("API: /api/digest", () => {
    const res = http.get(`${BASE_URL}/api/digest?hours=24`);
    apiTrend.add(res.timings.duration);
    checkResponse(res, "api digest");
  });
}

function fetchBadgeCounts() {
  group("API: /api/badge-counts", () => {
    const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    const res = http.get(
      `${BASE_URL}/api/badge-counts?since_dashboard=${since}&since_trends=${since}&since_ccc=${since}`,
    );
    apiTrend.add(res.timings.duration);
    checkResponse(res, "api badge-counts");
  });
}

// --- Helpers ---

function checkResponse(res, name) {
  const ok = check(res, {
    [`${name}: status 200`]: (r) => r.status === 200,
    [`${name}: body not empty`]: (r) => r.body && r.body.length > 0,
  });
  errorRate.add(!ok);
}
