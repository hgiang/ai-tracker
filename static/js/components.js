/* ========== Helper Functions ========== */

export function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now - d;
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function scoreClass(score) {
  if (score >= 0.5) return "high";
  if (score >= 0.2) return "mid";
  return "low";
}

const _escapeEl = document.createElement("div");
function escapeHtml(str) {
  _escapeEl.textContent = str;
  return _escapeEl.innerHTML;
}

function getDomain(url) {
  try {
    return new URL(url).hostname.replace("www.", "");
  } catch {
    return "";
  }
}

/* ========== Markdown Renderer (lightweight) ========== */

export function renderMarkdown(text) {
  if (!text) return "";
  return text
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, text, url) => {
      const safeUrl = /^https?:\/\//i.test(url) ? url : "#";
      return `<a href="${safeUrl}" target="_blank" rel="noopener">${text}</a>`;
    })
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/gs, "<ul>$&</ul>")
    .replace(/^(?!<[hulo])(.*\S.*)$/gm, "<p>$1</p>")
    .replace(/\n{2,}/g, "");
}

/* ========== Component Renderers ========== */

function typeTagClass(type) {
  const map = {
    paper: "tag-type-paper",
    repo: "tag-type-repo",
    post: "tag-type-post",
    discussion: "tag-type-discussion",
    podcast: "tag-type-podcast",
    video: "tag-type-video",
  };
  return map[type] || "tag-type";
}

function sourceTypeLabel(source) {
  if (source.adapter_type === "rss") {
    const ct = source.config?.content_type;
    if (ct === "podcast") return { label: "Podcast", cls: "tag-type-podcast" };
    if (ct === "video") return { label: "YouTube", cls: "tag-type-video" };
    return { label: "RSS", cls: "tag-type" };
  }
  const map = {
    hackernews: { label: "HN", cls: "tag-type-discussion" },
    reddit: { label: "Reddit", cls: "tag-type-discussion" },
    arxiv: { label: "arXiv", cls: "tag-type-paper" },
    github: { label: "GitHub", cls: "tag-type-repo" },
    x: { label: "X", cls: "tag-type-post" },
    bluesky: { label: "Bluesky", cls: "tag-type-post" },
    hf_papers: { label: "HF Papers", cls: "tag-type-paper" },
    polymarket: { label: "Polymarket", cls: "tag-type" },
  };
  return map[source.adapter_type] || { label: source.adapter_type, cls: "tag-type" };
}

export function renderItemCard(item, sourcesMap = {}) {
  const score = Math.round((item.relevance_score || 0) * 100);
  const cls = scoreClass(item.relevance_score || 0);
  const source = sourcesMap[item.source_id];
  const sourceName = source ? source.name : `Source #${item.source_id}`;
  const domain = getDomain(item.url);

  const paperActions = item.content_type === "paper" ? `
    <div class="paper-actions">
      <a href="/summary?item_id=${item.id}" target="_blank" rel="noopener"
         class="btn btn-sm btn-summary">Summary</a>
      <a href="/notebook?item_id=${item.id}" target="_blank" rel="noopener"
         class="btn btn-sm btn-notebook">Notebook</a>
    </div>` : "";

  return `
    <div class="item-card" data-item-id="${item.id}">
      <div class="item-score ${cls}">${score}%</div>
      <div class="item-content">
        <div style="display:flex;align-items:flex-start;gap:0.5rem">
          <a class="item-title" href="${escapeHtml(item.url)}" target="_blank" rel="noopener"
             style="flex:1">
            ${escapeHtml(item.title)}
          </a>
          ${paperActions}
        </div>
        ${item.summary ? `<div class="item-summary">${escapeHtml(item.summary)}</div>` : ""}
        <div class="item-meta">
          ${item.author ? `<span class="item-author">${escapeHtml(item.author)}</span><span class="item-meta-divider"></span>` : ""}
          <span>${sourceName}</span>
          <span class="item-meta-divider"></span>
          <span>${domain}</span>
          ${item.published_at ? `<span class="item-meta-divider"></span><span>${formatDate(item.published_at)}</span>` : ""}
          ${item.points != null ? `<span class="item-meta-divider"></span><span>${item.points} pts</span>` : ""}
          ${item.comment_count != null ? `<span class="item-meta-divider"></span><span>${item.comment_count} comments</span>` : ""}
        </div>
        <div class="item-footer">
          <div class="item-tags">
            <span class="tag tag-source">${escapeHtml(sourceName)}</span>
            <span class="tag ${typeTagClass(item.content_type)}">${item.content_type}</span>
          </div>
          ${renderFeedbackButtons(item)}
        </div>
      </div>
    </div>
  `;
}

function renderFeedbackButtons(item) {
  const verdict = item.user_feedback || "";
  const upActive = verdict === "up" ? "is-active" : "";
  const downActive = verdict === "down" ? "is-active" : "";
  return `
    <div class="feedback-buttons" role="group" aria-label="Rate this item">
      <button class="btn-feedback ${upActive}" data-feedback="up"
              aria-pressed="${verdict === "up"}" title="Useful — show me more like this">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M7 10v12"/>
          <path d="M15 5.88L14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H7V10l4.59-7.59A1 1 0 0 1 13 3a2 2 0 0 1 2 2v.88z"/>
        </svg>
      </button>
      <button class="btn-feedback ${downActive}" data-feedback="down"
              aria-pressed="${verdict === "down"}" title="Not useful — hide more like this">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M17 14V2"/>
          <path d="M9 18.12L10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H17v12l-4.59 7.59A1 1 0 0 1 11 21a2 2 0 0 1-2-2v-.88z"/>
        </svg>
      </button>
    </div>
  `;
}

export function renderSkeletonItems(count = 5) {
  return Array.from({ length: count }, () => `
    <div class="skeleton-card">
      <div class="skeleton skeleton-score"></div>
      <div class="skeleton-content">
        <div class="skeleton skeleton-line" style="width:80%"></div>
        <div class="skeleton skeleton-line" style="width:50%"></div>
      </div>
    </div>
  `).join("");
}

export function renderSourceCard(source) {
  const badgeClass = source.enabled ? "enabled" : "disabled";
  const badgeText = source.enabled ? "Active" : "Disabled";
  const { label, cls } = sourceTypeLabel(source);

  return `
    <div class="card source-card">
      <div class="source-header">
        <span class="source-name">${escapeHtml(source.name)}</span>
        <div style="display:flex;gap:0.4rem;align-items:center">
          <span class="tag ${cls}">${label}</span>
          <span class="source-badge ${badgeClass}">${badgeText}</span>
        </div>
      </div>
      <div class="source-url" title="${escapeHtml(source.url)}">${escapeHtml(source.url)}</div>
      <div class="source-actions">
        <button class="btn btn-sm btn-sync" data-slug="${escapeHtml(source.slug)}" ${!source.enabled ? "disabled" : ""}>
          Sync Now
        </button>
        <button class="btn btn-sm btn-danger btn-remove" data-slug="${escapeHtml(source.slug)}" data-name="${escapeHtml(source.name)}">
          Remove
        </button>
      </div>
    </div>
  `;
}

export function renderPagination(page, limit, total) {
  const totalPages = Math.ceil(total / limit);
  if (totalPages <= 1) return "";

  const start = (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);

  return `
    <div class="pagination">
      <button class="btn btn-sm" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>
        Prev
      </button>
      <span class="pagination-info">${start}-${end} of ${total}</span>
      <button class="btn btn-sm" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""}>
        Next
      </button>
    </div>
  `;
}

export function renderEmpty(icon, title, text) {
  return `
    <div class="empty-state">
      <div class="empty-state-icon">${icon}</div>
      <div class="empty-state-title">${title}</div>
      <div class="empty-state-text">${text}</div>
    </div>
  `;
}

export function renderLoading() {
  return `
    <div class="loading-overlay">
      <span class="spinner"></span>
      <span>Loading...</span>
    </div>
  `;
}

export function renderStatCard(value, label) {
  return `
    <div class="card stat-card">
      <div class="stat-value">${value}</div>
      <div class="stat-label">${label}</div>
    </div>
  `;
}
