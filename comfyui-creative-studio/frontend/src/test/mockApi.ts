import { vi } from "vitest";

type Handler = (url: URL, init?: RequestInit) => unknown;

/** Install a fetch mock that routes "/api/..." paths to handlers ("METHOD /path" or "/path"). */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = init?.method ?? "GET";
    let body: unknown;
    if (typeof init?.body === "string") body = JSON.parse(init.body);
    calls.push({ method, path: url.pathname + url.search, body });
    const key = [`${method} ${url.pathname}`, url.pathname].find((k) => k in routes);
    if (!key) return new Response(JSON.stringify({ detail: `no mock for ${method} ${url.pathname}` }), { status: 404, headers: { "content-type": "application/json" } });
    const r = routes[key];
    const data = typeof r === "function" ? (r as Handler)(url, init) : r;
    return new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}
