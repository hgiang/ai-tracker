import { api } from "./api.js";
import {
  renderItemCard,
  renderSkeletonItems,
  renderSourceCard,
  renderPagination,
  renderEmpty,
  renderLoading,
  renderStatCard,
  renderMarkdown,
  formatDate,
} from "./components.js";

/* ========== State ========== */

const state = {
  sources: [],
  sourcesMap: {},
  feedParams: { page: 1, limit: 20, q: "", content_type: "", source_id: "", min_score: "" },
};

const $app = document.getElementById("app");
const $toasts = document.getElementById("toasts");

/* ========== Toast ========== */

function showToast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  $toasts.appendChild(el);
  setTimeout(() => {
    el.classList.add("toast-exit");
    el.addEventListener("animationend", () => el.remove());
  }, 3000);
}

/* ========== Theme ========== */

function initTheme() {
  const saved = localStorage.getItem("theme");
  const theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  });
}

/* ========== Router ========== */

function getRoute() {
  const hash = window.location.hash || "#/";
  return hash.replace("#", "") || "/";
}

function setActiveNav(route) {
  document.querySelectorAll(".nav-link").forEach((link) => {
    const linkRoute = link.getAttribute("data-route");
    const isActive =
      (linkRoute === "feed" && (route === "/" || route === "/feed")) ||
      (linkRoute === "sources" && route === "/sources") ||
      (linkRoute === "digest" && route === "/digest");
    link.classList.toggle("active", isActive);
  });
}

async function navigate() {
  const route = getRoute();
  setActiveNav(route);

  switch (route) {
    case "/":
    case "/feed":
      await renderFeedPage();
      break;
    case "/sources":
      await renderSourcesPage();
      break;
    case "/digest":
      await renderDigestPage();
      break;
    default:
      $app.innerHTML = renderEmpty("404", "Page not found", "The page you're looking for doesn't exist.");
  }
}

/* ========== Helpers ========== */

function setSources(list) {
  state.sources = list;
  state.sourcesMap = {};
  for (const s of list) {
    state.sourcesMap[s.id] = s;
  }
}

async function withButtonLoading(btn, label, asyncFn) {
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';
  try {
    await asyncFn();
  } catch (err) {
    showToast(`Failed: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

/* ========== Data Loading ========== */

async function loadSources() {
  if (state.sources.length > 0) return;
  try {
    setSources(await api.getSources());
  } catch (err) {
    console.error("Failed to load sources:", err);
  }
}

/* ========== Feed Page ========== */

let searchTimeout = null;

async function renderFeedPage() {
  await loadSources();

  $app.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">AI News Feed</h1>
        <p class="page-subtitle">Latest AI, ML, and deep learning news from across the web</p>
      </div>
    </div>
    <div class="filter-bar">
      <input class="search-input" type="text" placeholder="Search articles..."
        value="${state.feedParams.q}" id="feed-search">
      <select class="filter-select" id="feed-source">
        <option value="">All Sources</option>
        ${state.sources.map((s) => `<option value="${s.id}" ${state.feedParams.source_id == s.id ? "selected" : ""}>${s.name}</option>`).join("")}
      </select>
      <select class="filter-select" id="feed-type">
        <option value="">All Types</option>
        <option value="news" ${state.feedParams.content_type === "news" ? "selected" : ""}>News</option>
        <option value="discussion" ${state.feedParams.content_type === "discussion" ? "selected" : ""}>Discussion</option>
        <option value="paper" ${state.feedParams.content_type === "paper" ? "selected" : ""}>Paper</option>
        <option value="repo" ${state.feedParams.content_type === "repo" ? "selected" : ""}>Repo</option>
        <option value="post" ${state.feedParams.content_type === "post" ? "selected" : ""}>Post</option>
        <option value="article" ${state.feedParams.content_type === "article" ? "selected" : ""}>Article</option>
        <option value="podcast" ${state.feedParams.content_type === "podcast" ? "selected" : ""}>Podcast</option>
        <option value="video" ${state.feedParams.content_type === "video" ? "selected" : ""}>Video</option>
      </select>
      <select class="filter-select" id="feed-score">
        <option value="">Any Relevance</option>
        <option value="0.5" ${state.feedParams.min_score === "0.5" ? "selected" : ""}>50%+</option>
        <option value="0.3" ${state.feedParams.min_score === "0.3" ? "selected" : ""}>30%+</option>
        <option value="0.1" ${state.feedParams.min_score === "0.1" ? "selected" : ""}>10%+</option>
      </select>
    </div>
    <div class="card">
      <div class="item-list" id="feed-items">
        ${renderSkeletonItems(5)}
      </div>
      <div id="feed-pagination"></div>
    </div>
  `;

  bindFeedEvents();
  await loadFeedItems();
}

function bindFeedEvents() {
  const searchEl = document.getElementById("feed-search");
  searchEl?.addEventListener("input", (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      state.feedParams.q = e.target.value;
      state.feedParams.page = 1;
      loadFeedItems();
    }, 400);
  });

  for (const [id, param] of [
    ["feed-source", "source_id"],
    ["feed-type", "content_type"],
    ["feed-score", "min_score"],
  ]) {
    document.getElementById(id)?.addEventListener("change", (e) => {
      state.feedParams[param] = e.target.value;
      state.feedParams.page = 1;
      loadFeedItems();
    });
  }
}

function attachFeedbackHandlers(container) {
  container.querySelectorAll(".btn-feedback").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const card = btn.closest("[data-item-id]");
      if (!card) return;
      const itemId = card.dataset.itemId;
      const value = btn.dataset.feedback;
      const wasActive = btn.classList.contains("is-active");
      const nextValue = wasActive ? null : value;

      // Optimistic UI: toggle classes immediately
      card.querySelectorAll(".btn-feedback").forEach((b) => {
        b.classList.remove("is-active");
        b.setAttribute("aria-pressed", "false");
        b.disabled = true;
      });
      if (nextValue) {
        btn.classList.add("is-active");
        btn.setAttribute("aria-pressed", "true");
      }

      try {
        await api.setFeedback(itemId, nextValue);
      } catch (err) {
        // Revert
        card.querySelectorAll(".btn-feedback").forEach((b) => {
          b.classList.remove("is-active");
          b.setAttribute("aria-pressed", "false");
        });
        if (wasActive) {
          btn.classList.add("is-active");
          btn.setAttribute("aria-pressed", "true");
        }
        showToast(`Couldn't save feedback: ${err.message}`, "error");
      } finally {
        card.querySelectorAll(".btn-feedback").forEach((b) => (b.disabled = false));
      }
    });
  });
}

async function loadFeedItems() {
  const $items = document.getElementById("feed-items");
  const $pagination = document.getElementById("feed-pagination");
  if (!$items) return;

  $items.innerHTML = renderSkeletonItems(5);

  try {
    const data = await api.getItems(state.feedParams);

    if (data.items.length === 0) {
      $items.innerHTML = renderEmpty(
        "&#128240;",
        "No articles found",
        "Try adjusting your filters or sync some sources first."
      );
      $pagination.innerHTML = "";
      return;
    }

    $items.innerHTML = data.items
      .map((item) => renderItemCard(item, state.sourcesMap))
      .join("");

    attachFeedbackHandlers($items);

    $pagination.innerHTML = renderPagination(data.page, data.limit, data.total);

    $pagination.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const page = parseInt(btn.dataset.page);
        if (page >= 1) {
          state.feedParams.page = page;
          loadFeedItems();
          $app.scrollTo({ top: 0, behavior: "smooth" });
        }
      });
    });
  } catch (err) {
    $items.innerHTML = renderEmpty(
      "&#9888;",
      "Failed to load items",
      err.message
    );
    $pagination.innerHTML = "";
  }
}

/* ========== Sources Page ========== */

function renderAddSourceModal() {
  return `
    <div id="add-source-modal" class="modal-overlay" style="display:none" role="dialog" aria-modal="true">
      <div class="modal">
        <div class="modal-header">
          <h2 class="modal-title">Add Source</h2>
          <button class="modal-close" id="modal-close" aria-label="Close">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label" for="source-type-picker">Source Type</label>
            <select class="filter-select" id="source-type-picker">
              <option value="reddit">Reddit (Subreddit)</option>
              <option value="arxiv">ArXiv (Category)</option>
              <option value="x">X (Add Account)</option>
              <option value="rss">RSS Feed</option>
              <option value="youtube">YouTube Channel</option>
              <option value="podcast">Podcast (RSS)</option>
              <option value="bluesky">Bluesky</option>
              <option value="github">GitHub</option>
            </select>
          </div>
          <div id="source-guided-fields"></div>
        </div>
        <div class="modal-footer">
          <button class="btn" id="modal-cancel">Cancel</button>
          <button class="btn btn-primary" id="modal-submit">Add</button>
        </div>
      </div>
    </div>
  `;
}

function renderGuidedFields(type) {
  switch (type) {
    case "reddit":
      return `
        <div class="form-group">
          <label class="form-label" for="field-subreddit">Subreddit</label>
          <input class="search-input" id="field-subreddit" type="text" placeholder="e.g. AINews" />
        </div>`;
    case "arxiv":
      return `
        <div class="form-group">
          <label class="form-label" for="field-category">ArXiv Category</label>
          <input class="search-input" id="field-category" type="text" placeholder="e.g. cs.LG" />
        </div>`;
    case "x":
      return `
        <p class="form-hint">Handle will be added to the existing X source.</p>
        <div class="form-group">
          <label class="form-label" for="field-handle">X Handle</label>
          <input class="search-input" id="field-handle" type="text" placeholder="e.g. karpathy (without @)" />
        </div>`;
    case "rss":
      return `
        <div class="form-group">
          <label class="form-label" for="field-name">Name</label>
          <input class="search-input" id="field-name" type="text" placeholder="e.g. OpenAI Blog" />
        </div>
        <div class="form-group">
          <label class="form-label" for="field-url">Feed URL</label>
          <input class="search-input" id="field-url" type="url" placeholder="https://example.com/feed.xml" />
        </div>`;
    case "youtube":
      return `
        <div class="form-group">
          <label class="form-label" for="field-name">Channel Name</label>
          <input class="search-input" id="field-name" type="text" placeholder="e.g. Two Minute Papers" />
        </div>
        <div class="form-group">
          <label class="form-label" for="field-channel-id">Channel ID</label>
          <input class="search-input" id="field-channel-id" type="text" placeholder="e.g. UCbfYPyITQ-7l4upoX8nvctg" />
          <p class="form-hint">Find it in the channel URL: youtube.com/channel/<strong>CHANNEL_ID</strong></p>
        </div>`;
    case "podcast":
      return `
        <div class="form-group">
          <label class="form-label" for="field-name">Podcast Name</label>
          <input class="search-input" id="field-name" type="text" placeholder="e.g. TWIML AI Podcast" />
        </div>
        <div class="form-group">
          <label class="form-label" for="field-url">RSS Feed URL</label>
          <input class="search-input" id="field-url" type="url" placeholder="https://example.com/podcast/feed" />
        </div>`;
    case "bluesky":
      return `
        <div class="form-group">
          <label class="form-label" for="field-name">Name</label>
          <input class="search-input" id="field-name" type="text" placeholder="e.g. Bluesky AI Voices" />
        </div>`;
    case "github":
      return `
        <div class="form-group">
          <label class="form-label" for="field-name">Name</label>
          <input class="search-input" id="field-name" type="text" placeholder="e.g. GitHub Trending" />
        </div>`;
    default:
      return "";
  }
}

async function handleAddSourceSubmit() {
  const type = document.getElementById("source-type-picker").value;

  try {
    if (type === "x") {
      const handle = document.getElementById("field-handle")?.value.trim().replace(/^@/, "");
      if (!handle) { showToast("Handle is required", "error"); return; }

      const xSource = state.sources.find((s) => s.adapter_type === "x");
      if (!xSource) { showToast("X source not found — sync default sources first", "error"); return; }

      const currentAccounts = xSource.config?.accounts || "";
      const existing = currentAccounts ? currentAccounts.split(",").map((h) => h.trim()) : [];
      if (existing.includes(handle)) { showToast(`@${handle} is already in the X source`, "error"); return; }

      const updated = [...existing, handle].join(",");
      await api.patchSourceConfig(xSource.slug, { accounts: updated });
      showToast(`Added @${handle} to X source`, "success");

    } else {
      let name, url, config;

      if (type === "reddit") {
        const sub = document.getElementById("field-subreddit")?.value.trim();
        if (!sub) { showToast("Subreddit is required", "error"); return; }
        name = `Reddit r/${sub}`;
        url = `https://reddit.com/r/${sub}`;
        config = { subreddit: sub };

      } else if (type === "arxiv") {
        const cat = document.getElementById("field-category")?.value.trim();
        if (!cat) { showToast("Category is required", "error"); return; }
        name = `arXiv ${cat}`;
        url = "https://arxiv.org";
        config = { category: cat };

      } else if (type === "rss") {
        name = document.getElementById("field-name")?.value.trim();
        url = document.getElementById("field-url")?.value.trim();
        if (!name || !url) { showToast("Name and URL are required", "error"); return; }
        config = null;

      } else if (type === "youtube") {
        name = document.getElementById("field-name")?.value.trim();
        const channelId = document.getElementById("field-channel-id")?.value.trim();
        if (!name || !channelId) { showToast("Name and Channel ID are required", "error"); return; }
        url = `https://www.youtube.com/feeds/videos.xml?channel_id=${channelId}`;
        config = { content_type: "video" };

      } else if (type === "podcast") {
        name = document.getElementById("field-name")?.value.trim();
        url = document.getElementById("field-url")?.value.trim();
        if (!name || !url) { showToast("Name and URL are required", "error"); return; }
        config = { content_type: "podcast" };

      } else {
        name = document.getElementById("field-name")?.value.trim();
        const defaults = { bluesky: "https://bsky.app", github: "https://github.com" };
        url = defaults[type] || "https://example.com";
        if (!name) { showToast("Name is required", "error"); return; }
        config = null;
      }

      await api.createSource({ name, adapter_type: type, url, config });
      showToast(`Added "${name}"`, "success");
    }

    document.getElementById("add-source-modal").style.display = "none";
    state.sources = [];
    await renderSourcesPage();

  } catch (err) {
    showToast(`Failed: ${err.message}`, "error");
  }
}

async function renderSourcesPage() {
  $app.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">Sources</h1>
        <p class="page-subtitle">Manage your AI news sources</p>
      </div>
      <div class="page-actions">
        <button class="btn btn-primary" id="add-source-btn">Add Source</button>
        <button class="btn btn-danger" id="clear-db-btn">Clear Database</button>
        <button class="btn btn-primary" id="sync-all-btn">Sync All Sources</button>
      </div>
    </div>
    <div class="source-grid" id="source-grid">
      ${renderLoading()}
    </div>
    <div class="card" id="sync-results" style="display:none;margin-top:1rem">
      <div class="card-body">
        <strong>Sync Results</strong>
        <div class="sync-results" id="sync-results-list"></div>
      </div>
    </div>
    ${renderAddSourceModal()}
  `;

  try {
    setSources(await api.getSources());
    document.getElementById("source-grid").innerHTML = state.sources
      .map(renderSourceCard)
      .join("");

    bindSourceEvents();
  } catch (err) {
    document.getElementById("source-grid").innerHTML = renderEmpty(
      "&#9888;",
      "Failed to load sources",
      err.message
    );
  }
}

function bindSourceEvents() {
  document.getElementById("clear-db-btn")?.addEventListener("click", (e) => {
    if (!confirm("This will delete ALL items and reset all sync checkpoints. Continue?")) return;
    withButtonLoading(e.currentTarget, "Clear Database", async () => {
      const result = await api.clearDatabase();
      showToast(`Cleared ${result.deleted} items from database`, "success");
      state.sources = [];
      await loadSources();
    });
  });

  document.getElementById("sync-all-btn")?.addEventListener("click", (e) => {
    withButtonLoading(e.currentTarget, "Sync All Sources", async () => {
      const results = await api.syncAll();
      showSyncResults(results);
      showToast(`Synced ${results.length} sources`, "success");
      state.sources = [];
      await loadSources();
    });
  });

  document.querySelectorAll(".btn-sync").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const slug = e.currentTarget.dataset.slug;
      withButtonLoading(e.currentTarget, "Sync Now", async () => {
        const result = await api.syncSource(slug);
        showSyncResults([result]);
        showToast(`${slug}: ${result.new} new items`, "success");
      });
    });
  });

  // Add Source modal
  const modal = document.getElementById("add-source-modal");
  const typePicker = document.getElementById("source-type-picker");
  const guidedFields = document.getElementById("source-guided-fields");

  function openModal() {
    modal.style.display = "flex";
    guidedFields.innerHTML = renderGuidedFields(typePicker.value);
  }

  function closeModal() {
    modal.style.display = "none";
  }

  document.getElementById("add-source-btn")?.addEventListener("click", openModal);
  document.getElementById("modal-close")?.addEventListener("click", closeModal);
  document.getElementById("modal-cancel")?.addEventListener("click", closeModal);
  modal?.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

  typePicker?.addEventListener("change", () => {
    guidedFields.innerHTML = renderGuidedFields(typePicker.value);
  });

  document.getElementById("modal-submit")?.addEventListener("click", handleAddSourceSubmit);

  // Per-card remove buttons
  document.querySelectorAll(".btn-remove").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      const slug = e.currentTarget.dataset.slug;
      const name = e.currentTarget.dataset.name;
      if (!confirm(`Remove "${name}"? This cannot be undone.`)) return;
      try {
        await api.deleteSource(slug);
        showToast(`Removed "${name}"`, "success");
        state.sources = [];
        await renderSourcesPage();
      } catch (err) {
        showToast(`Failed to remove: ${err.message}`, "error");
      }
    });
  });
}

function showSyncResults(results) {
  const $container = document.getElementById("sync-results");
  const $list = document.getElementById("sync-results-list");
  if (!$container || !$list) return;

  $container.style.display = "block";
  $list.innerHTML = results
    .map(
      (r) => `
    <div class="sync-result-item">
      <span>${r.source}</span>
      <div class="sync-stat">
        <span>Fetched: <strong>${r.fetched}</strong></span>
        <span>New: <strong>${r.new}</strong></span>
        <span>Dupes: <strong>${r.duplicates}</strong></span>
      </div>
    </div>
  `
    )
    .join("");
}

/* ========== Digest Page ========== */

async function renderDigestPage() {
  $app.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">Daily Digest</h1>
        <p class="page-subtitle">AI-curated summary of top articles</p>
      </div>
      <div class="page-actions">
        <button class="btn btn-primary" id="generate-digest-btn">Generate Today's Digest</button>
        <button class="btn" id="cleanup-btn">Cleanup Old Data</button>
      </div>
    </div>
    <div id="digest-container">
      ${renderLoading()}
    </div>
  `;

  document.getElementById("generate-digest-btn")?.addEventListener("click", (e) => {
    withButtonLoading(e.currentTarget, "Generate Today's Digest", async () => {
      await api.generateDigest();
      showToast("Digest generated", "success");
      await loadDigest();
    });
  });

  document.getElementById("cleanup-btn")?.addEventListener("click", (e) => {
    withButtonLoading(e.currentTarget, "Cleanup Old Data", async () => {
      const result = await api.cleanup();
      showToast(`Cleaned up ${result.deleted} expired items`, "success");
    });
  });

  await loadDigest();
}

async function loadDigest() {
  const $container = document.getElementById("digest-container");
  if (!$container) return;

  try {
    const digest = await api.getLatestDigest();

    $container.innerHTML = `
      <div class="stats-row">
        ${renderStatCard(digest.item_count, "Articles")}
        ${renderStatCard(digest.date, "Date")}
        ${renderStatCard(formatDate(digest.created_at), "Generated")}
      </div>
      <div class="card">
        <div class="digest-content">
          ${renderMarkdown(digest.content)}
        </div>
      </div>
    `;
  } catch (err) {
    if (err.message.includes("404")) {
      $container.innerHTML = `
        <div class="card">
          ${renderEmpty(
            "&#128196;",
            "No digest yet",
            "Sync some sources first, then generate a digest to see your daily summary."
          )}
        </div>
      `;
    } else {
      $container.innerHTML = `
        <div class="card">
          ${renderEmpty("&#9888;", "Failed to load digest", err.message)}
        </div>
      `;
    }
  }
}

/* ========== Init ========== */

function init() {
  initTheme();
  window.addEventListener("hashchange", navigate);
  navigate();
}

init();
