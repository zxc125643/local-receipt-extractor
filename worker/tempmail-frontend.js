const API_PREFIXES = [
  "/api/",
  "/open_api/",
  "/user_api/",
  "/admin/",
  "/telegram/",
  "/external/"
];

function shouldProxyToApi(pathname) {
  if (pathname === "/admin" || pathname === "/admin/") {
    return false;
  }

  return API_PREFIXES.some((prefix) => pathname === prefix.slice(0, -1) || pathname.startsWith(prefix));
}

const FIRST_NAMES = [
  "james", "mary", "john", "patricia", "robert", "jennifer", "michael", "linda",
  "william", "elizabeth", "david", "barbara", "richard", "susan", "joseph", "jessica",
  "thomas", "sarah", "charles", "karen", "christopher", "nancy", "daniel", "lisa",
  "matthew", "betty", "anthony", "margaret", "mark", "sandra", "donald", "ashley",
  "steven", "kimberly", "paul", "emily", "andrew", "donna", "joshua", "michelle",
  "kenneth", "carol", "kevin", "amanda", "brian", "melissa", "george", "deborah",
  "edward", "stephanie", "ronald", "rebecca", "timothy", "laura", "jason", "sharon",
  "jeffrey", "cynthia", "ryan", "kathleen", "jacob", "amy", "gary", "angela",
  "nicholas", "shirley", "eric", "anna", "jonathan", "brenda", "stephen", "pamela",
  "larry", "nicole", "justin", "emma", "scott", "samantha", "brandon", "katherine"
];

const LAST_NAMES = [
  "smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis",
  "rodriguez", "martinez", "hernandez", "lopez", "gonzalez", "wilson", "anderson",
  "thomas", "taylor", "moore", "jackson", "martin", "lee", "perez", "thompson",
  "white", "harris", "sanchez", "clark", "ramirez", "lewis", "robinson", "walker",
  "young", "allen", "king", "wright", "scott", "torres", "nguyen", "hill",
  "flores", "green", "adams", "nelson", "baker", "hall", "rivera", "campbell",
  "mitchell", "carter", "roberts", "gomez", "phillips", "evans", "turner", "diaz",
  "parker", "cruz", "edwards", "collins", "reyes", "stewart", "morris", "morales",
  "murphy", "cook", "rogers", "gutierrez", "ortiz", "morgan", "cooper", "peterson",
  "bailey", "reed", "kelly", "howard", "ramos", "kim", "cox", "ward"
];

function randomItem(items) {
  const values = new Uint32Array(1);
  crypto.getRandomValues(values);
  return items[values[0] % items.length];
}

function randomDigits(length) {
  const values = new Uint8Array(length);
  crypto.getRandomValues(values);
  return Array.from(values, (value) => String(value % 10)).join("");
}

function createHumanAddressName() {
  const first = randomItem(FIRST_NAMES);
  const last = randomItem(LAST_NAMES);
  const patterns = [
    () => `${first}.${last}`,
    () => `${first}${last}`,
    () => `${first}_${last}`,
    () => `${first}.${last}${randomDigits(2)}`,
    () => `${first}${last}${randomDigits(3)}`,
    () => `${first[0]}${last}${randomDigits(2)}`
  ];

  return randomItem(patterns)();
}

async function maybeAddHumanName(request) {
  const url = new URL(request.url);
  const shouldAddName = request.method === "POST"
    && (url.pathname === "/api/new_address" || url.pathname === "/admin/new_address");

  if (!shouldAddName) {
    return request;
  }

  let body;
  try {
    body = await request.clone().json();
  } catch {
    body = {};
  }

  if (body && typeof body === "object" && !Array.isArray(body) && !body.name) {
    body.name = createHumanAddressName();
  }

  const headers = new Headers(request.headers);
  headers.set("Content-Type", "application/json");

  return new Request(request.url, {
    method: request.method,
    headers,
    body: JSON.stringify(body),
    redirect: request.redirect
  });
}

const SERVICE_WORKER = `self.addEventListener("install",()=>self.skipWaiting());
self.addEventListener("activate",(event)=>{event.waitUntil(caches.keys().then((keys)=>Promise.all(keys.map((key)=>caches.delete(key)))).then(()=>self.clients.claim()))});
self.addEventListener("fetch",(event)=>{event.respondWith(fetch(event.request))});`;

const INDEX_HTML = `<!DOCTYPE html>
<html lang="en">

<head>
  <meta charset="UTF-8">
  <link rel="icon" href="/logo.png">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Temp Email</title>
  <meta name="description" content="Temp Email">
  <meta name="theme-color" media="(prefers-color-scheme: light)" content="#000">
  <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#ffffff">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="Temp Email">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="icon" href="/logo.png" sizes="any">
  <link rel="apple-touch-icon" href="/logo.png">
  <script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"></script>
  <script type="module" crossorigin src="/assets/index-BsjNziEK.js"></script>
  <link rel="stylesheet" crossorigin href="/assets/index-D5K8M3PG.css">
<link rel="manifest" href="/manifest.webmanifest"><script id="vite-plugin-pwa:register-sw" src="/registerSW.js"></script></head>

<body>
  <div id="app"></div>
</body>

</html>
`;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/sw.js") {
      return new Response(SERVICE_WORKER, {
        headers: {
          "Content-Type": "text/javascript; charset=UTF-8",
          "Cache-Control": "no-store"
        }
      });
    }

    if (shouldProxyToApi(url.pathname)) {
      const apiRequest = await maybeAddHumanName(request);
      const response = await env.API.fetch(apiRequest);
      const headers = new Headers(response.headers);
      headers.set("Cache-Control", "no-store");

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers
      });
    }

    if (url.pathname === "/index.html" || !url.pathname.includes(".")) {
      return new Response(INDEX_HTML, {
        headers: {
          "Content-Type": "text/html; charset=UTF-8",
          "Cache-Control": "no-store"
        }
      });
    }

    return env.ASSETS.fetch(new Request(url, request));
  }
};
