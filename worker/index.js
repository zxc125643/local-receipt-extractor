const STATIC_ASSET_PATTERN = /\.[a-zA-Z0-9][a-zA-Z0-9_-]*$/;
const API_PREFIXES = [
  "/api/",
  "/open_api/",
  "/user_api/",
  "/admin/",
  "/telegram/",
  "/external/"
];

function shouldProxyToApi(pathname) {
  return API_PREFIXES.some((prefix) => pathname === prefix.slice(0, -1) || pathname.startsWith(prefix));
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (shouldProxyToApi(url.pathname)) {
      const response = await env.API.fetch(request);
      const headers = new Headers(response.headers);
      headers.set("Cache-Control", "no-store");
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers
      });
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return env.ASSETS.fetch(request);
    }

    const response = await env.ASSETS.fetch(request);
    if (response.status !== 404 || STATIC_ASSET_PATTERN.test(url.pathname)) {
      return response;
    }

    const indexUrl = new URL("/", url);
    return env.ASSETS.fetch(new Request(indexUrl, request));
  }
};
