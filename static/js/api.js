const BASE = "/api";

async function request(path, options = {}) {
  const url = `${BASE}${path}`;
  const resp = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`${resp.status}: ${text || resp.statusText}`);
  }

  return resp.json();
}

export const api = {
  getItems(params = {}) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, v);
    }
    const query = qs.toString();
    return request(`/items${query ? `?${query}` : ""}`);
  },

  getItem(id) {
    return request(`/items/${id}`);
  },

  getSources() {
    return request("/sources");
  },

  syncAll() {
    return request("/sources/sync", { method: "POST" });
  },

  syncSource(slug) {
    return request(`/sources/sync/${slug}`, { method: "POST" });
  },

  getLatestDigest() {
    return request("/digests/latest");
  },

  generateDigest(targetDate) {
    const qs = targetDate ? `?target_date=${targetDate}` : "";
    return request(`/digests/generate${qs}`, { method: "POST" });
  },

  cleanup() {
    return request("/digests/cleanup", { method: "POST" });
  },

  clearDatabase() {
    return request("/items/clear", { method: "POST" });
  },

  createSource(data) {
    return request("/sources", { method: "POST", body: JSON.stringify(data) });
  },

  patchSourceConfig(slug, config) {
    return request(`/sources/${slug}/config`, {
      method: "PATCH",
      body: JSON.stringify({ config }),
    });
  },

  deleteSource(slug) {
    return request(`/sources/${slug}`, { method: "DELETE" });
  },
};
