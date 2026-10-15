(() => {
  const PAGE_SIZE = 20;
  const PENDING = new Set(["waiting", "processing"]);

  const els = {
    itemList: document.getElementById("itemList"),
    listEmpty: document.getElementById("listEmpty"),
    statusFilter: document.getElementById("statusFilter"),
    btnRefresh: document.getElementById("btnRefresh"),
    btnPrev: document.getElementById("btnPrev"),
    btnNext: document.getElementById("btnNext"),
    pageInfo: document.getElementById("pageInfo"),
    detailEmpty: document.getElementById("detailEmpty"),
    detailContent: document.getElementById("detailContent"),
    detailId: document.getElementById("detailId"),
    detailStatus: document.getElementById("detailStatus"),
    detailTime: document.getElementById("detailTime"),
    detailCreated: document.getElementById("detailCreated"),
    detailPdf: document.getElementById("detailPdf"),
    detailError: document.getElementById("detailError"),
    detailSummary: document.getElementById("detailSummary"),
    statTotal: document.getElementById("statTotal"),
    statPass: document.getElementById("statPass"),
    statFail: document.getElementById("statFail"),
    failChips: document.getElementById("failChips"),
    ruleList: document.getElementById("ruleList"),
  };

  let items = [];
  let selectedId = null;
  let detail = null;
  let ruleFilter = "all";
  let currentPage = 1;

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function parseRuleNumber(text) {
    const m = String(text ?? "").trim().match(/^(\d+)\s*[\.、．]/);
    return m ? m[1] : "";
  }

  function formatSeconds(v) {
    if (v == null || v === "") return "—";
    return `${v}s`;
  }

  async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`请求失败 ${res.status}: ${url}`);
    return res.json();
  }

  function filteredItems() {
    const st = els.statusFilter.value;
    if (st === "all") return items;
    return items.filter((it) => it.status === st);
  }

  function totalPages(list) {
    return Math.max(1, Math.ceil(list.length / PAGE_SIZE) || 1);
  }

  function renderList() {
    const list = filteredItems();
    const pages = totalPages(list);
    if (currentPage > pages) currentPage = pages;
    if (currentPage < 1) currentPage = 1;

    const start = (currentPage - 1) * PAGE_SIZE;
    const pageItems = list.slice(start, start + PAGE_SIZE);

    els.itemList.innerHTML = "";
    els.listEmpty.hidden = list.length > 0;

    for (const it of pageItems) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "item" + (it.item_id === selectedId ? " active" : "");
      btn.setAttribute("role", "listitem");
      btn.dataset.id = it.item_id;
      btn.innerHTML = `
        <div class="item-id">${escapeHtml(it.item_id)}</div>
        <div class="item-meta">
          <span class="badge ${escapeHtml(it.status || "")}">${escapeHtml(it.status || "?")}</span>
          <span>${escapeHtml(formatSeconds(it.processing_time))}</span>
          <span>${escapeHtml(it.create_time || "")}</span>
        </div>
      `;
      btn.addEventListener("click", () => selectItem(it.item_id));
      els.itemList.appendChild(btn);
    }

    const total = list.length;
    const from = total === 0 ? 0 : start + 1;
    const to = Math.min(start + PAGE_SIZE, total);
    els.pageInfo.textContent =
      total === 0
        ? "0 条"
        : `${from}-${to} / ${total} · ${currentPage}/${pages}`;
    els.btnPrev.disabled = currentPage <= 1 || total === 0;
    els.btnNext.disabled = currentPage >= pages || total === 0;
  }

  function parseFailChips(statText) {
    if (!statText) return [];
    return String(statText)
      .split(/[、,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function renderDetail() {
    if (!detail) {
      els.detailEmpty.hidden = false;
      els.detailContent.hidden = true;
      return;
    }

    els.detailEmpty.hidden = true;
    els.detailContent.hidden = false;

    els.detailId.textContent = detail.item_id || "";
    els.detailStatus.textContent = detail.status || "";
    els.detailStatus.className = `badge ${detail.status || ""}`;
    els.detailTime.textContent = `耗时 ${formatSeconds(detail.processing_time)}`;
    els.detailCreated.textContent = detail.create_time
      ? `创建 ${detail.create_time}`
      : "";

    if (detail.pdf_url) {
      els.detailPdf.hidden = false;
      els.detailPdf.href = detail.pdf_url;
      els.detailPdf.textContent = detail.pdf_url;
    } else {
      els.detailPdf.hidden = true;
    }

    const isError = detail.status === "error" || detail.error_message;
    if (detail.status === "error" || (detail.error_message && detail.status !== "success")) {
      els.detailError.hidden = false;
      els.detailError.textContent = detail.error_message || "处理失败";
    } else {
      els.detailError.hidden = true;
    }

    const reviews =
      detail.status === "success" && detail.result && Array.isArray(detail.result["审查结果"])
        ? detail.result["审查结果"]
        : [];

    if (!reviews.length) {
      els.detailSummary.hidden = true;
      els.ruleList.innerHTML = isError
        ? ""
        : `<p class="empty">${
            PENDING.has(detail.status)
              ? "任务处理中，可点击右上角「刷新」查看最新状态"
              : "暂无审查结果"
          }</p>`;
      return;
    }

    const pass = reviews.filter((r) => r["评估结果"] === "符合").length;
    const fail = reviews.filter((r) => r["评估结果"] === "不符合").length;
    els.detailSummary.hidden = false;
    els.statTotal.textContent = String(reviews.length);
    els.statPass.textContent = String(pass);
    els.statFail.textContent = String(fail);

    const chips = parseFailChips(detail.result["统计"]);
    els.failChips.innerHTML = chips.length
      ? chips.map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join("")
      : `<span class="meta">无不符合项</span>`;

    const shown = reviews.filter((r) => {
      const v = r["评估结果"];
      if (ruleFilter === "pass") return v === "符合";
      if (ruleFilter === "fail") return v === "不符合";
      return true;
    });

    els.ruleList.innerHTML = "";
    for (const r of shown) {
      const title = r["规则内容（需带规则序号）"] || "";
      const verdict = r["评估结果"] || "";
      const reason = r["理由"] || "";
      const num = parseRuleNumber(title) || "·";
      const isFail = verdict === "不符合";

      const article = document.createElement("article");
      article.className = "rule" + (isFail ? " fail" : "");
      article.innerHTML = `
        <button type="button" class="rule-toggle">
          <span class="rule-num">${escapeHtml(num)}</span>
          <span class="rule-title">${escapeHtml(title)}</span>
          <span class="badge ${isFail ? "error" : "success"}">${escapeHtml(verdict || "—")}</span>
        </button>
        <div class="rule-reason">${escapeHtml(reason || "（无理由）")}</div>
      `;
      article.querySelector(".rule-toggle").addEventListener("click", () => {
        article.classList.toggle("open");
      });
      els.ruleList.appendChild(article);
    }
  }

  async function loadItems() {
    items = await fetchJson("/audit/items");
    if (!Array.isArray(items)) items = [];
    renderList();
  }

  async function loadDetail(id) {
    try {
      const data = await fetchJson(`/audit/${encodeURIComponent(id)}`);
      if (selectedId !== id) return;
      detail = data;
      renderDetail();
    } catch (err) {
      detail = {
        item_id: id,
        status: "error",
        error_message: String(err.message || err),
      };
      renderDetail();
    }
  }

  async function selectItem(id) {
    selectedId = id;
    renderList();
    detail = { item_id: id, status: "processing" };
    renderDetail();
    els.detailSummary.hidden = true;
    els.ruleList.innerHTML = `<p class="empty">加载中…</p>`;
    await loadDetail(id);
  }

  els.statusFilter.addEventListener("change", () => {
    currentPage = 1;
    renderList();
  });
  els.btnPrev.addEventListener("click", () => {
    if (currentPage > 1) {
      currentPage -= 1;
      renderList();
    }
  });
  els.btnNext.addEventListener("click", () => {
    const pages = totalPages(filteredItems());
    if (currentPage < pages) {
      currentPage += 1;
      renderList();
    }
  });
  els.btnRefresh.addEventListener("click", async () => {
    await loadItems();
    if (selectedId) await loadDetail(selectedId);
  });

  document.querySelectorAll("[data-rule-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      ruleFilter = btn.dataset.ruleFilter;
      document.querySelectorAll("[data-rule-filter]").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      renderDetail();
    });
  });

  document.getElementById("btnExpandAll").addEventListener("click", () => {
    els.ruleList.querySelectorAll(".rule").forEach((el) => el.classList.add("open"));
  });
  document.getElementById("btnCollapseAll").addEventListener("click", () => {
    els.ruleList.querySelectorAll(".rule").forEach((el) => el.classList.remove("open"));
  });


  loadItems().catch((err) => {
    els.listEmpty.hidden = false;
    els.listEmpty.textContent = `加载失败：${err.message || err}`;
  });
})();
