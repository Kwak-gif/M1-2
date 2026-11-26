(() => {
  const API_BASE_URL = (
    (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) ||
    "http://127.0.0.1:8000"
  ).replace(/\/+$/, "");

  // 상태 관리 (순수 바닐라 JS)
  const state = {
    symbol: "005930",
    stockName: "삼성전자",
    stocks: [],
    summary: null,
    statistics: null,
    dataItems: [],
    conversations: [],
    currentConversationId: null,
    chartPoints: [],
  };

  // DOM 참조
  const el = {
    stockSelect: document.getElementById("stockSelect"),
    exportCsvBtn: document.getElementById("exportCsvBtn"),
    exportJsonBtn: document.getElementById("exportJsonBtn"),
    themeToggleBtn: document.getElementById("themeToggleBtn"),
    serverStatusBadge: document.getElementById("serverStatusBadge"),
    coldStartBanner: document.getElementById("coldStartBanner"),
    errorBanner: document.getElementById("errorBanner"),
    errorBannerText: document.getElementById("errorBannerText"),
    closeErrorBtn: document.getElementById("closeErrorBtn"),

    kpiStockTitle: document.getElementById("kpiStockTitle"),
    kpiPeriod: document.getElementById("kpiPeriod"),
    kpiLatestClose: document.getElementById("kpiLatestClose"),
    kpiLatestChange: document.getElementById("kpiLatestChange"),
    kpiAverage: document.getElementById("kpiAverage"),
    kpiVsAverage: document.getElementById("kpiVsAverage"),
    kpiHighLow: document.getElementById("kpiHighLow"),
    kpiRangePosition: document.getElementById("kpiRangePosition"),
    kpiTrend: document.getElementById("kpiTrend"),
    kpiCount: document.getElementById("kpiCount"),

    statMa20: document.getElementById("statMa20"),
    statMa60: document.getElementById("statMa60"),
    statMa120: document.getElementById("statMa120"),
    statRet1y: document.getElementById("statRet1y"),
    statVol: document.getElementById("statVol"),
    statMdd: document.getElementById("statMdd"),

    chartTitle: document.getElementById("chartTitle"),
    stockChart: document.getElementById("stockChart"),
    chartTooltip: document.getElementById("chartTooltip"),

    conversationList: document.getElementById("conversationList"),
    newChatBtn: document.getElementById("newChatBtn"),
    tabChatBtn: document.getElementById("tabChatBtn"),
    tabDataBtn: document.getElementById("tabDataBtn"),
    chatPanel: document.getElementById("chatPanel"),
    dataPanel: document.getElementById("dataPanel"),

    chatMessages: document.getElementById("chatMessages"),
    chatLoading: document.getElementById("chatLoading"),
    chatForm: document.getElementById("chatForm"),
    chatInput: document.getElementById("chatInput"),
    sendChatBtn: document.getElementById("sendChatBtn"),
    useToolsCheckbox: document.getElementById("useToolsCheckbox"),

    dataForm: document.getElementById("dataForm"),
    dataFormTitle: document.getElementById("dataFormTitle"),
    editItemId: document.getElementById("editItemId"),
    inputDate: document.getElementById("inputDate"),
    inputValue: document.getElementById("inputValue"),
    inputMemo: document.getElementById("inputMemo"),
    saveDataBtn: document.getElementById("saveDataBtn"),
    cancelEditBtn: document.getElementById("cancelEditBtn"),
    dataFormFeedback: document.getElementById("dataFormFeedback"),
    tableSearchInput: document.getElementById("tableSearchInput"),
    tableCountBadge: document.getElementById("tableCountBadge"),
    dataTableBody: document.getElementById("dataTableBody"),
  };

  // 포맷터
  const fmtWon = (val) =>
    val === null || val === undefined ? "-" : `${Math.round(Number(val)).toLocaleString("ko-KR")}원`;
  const fmtPct = (val) => {
    if (val === null || val === undefined) return "-";
    const num = Number(val);
    return `${num > 0 ? "+" : ""}${num.toFixed(2)}%`;
  };

  function showError(msg) {
    el.errorBannerText.textContent = msg;
    el.errorBanner.classList.remove("hidden");
  }

  function hideError() {
    el.errorBanner.classList.add("hidden");
  }

  function setServerStatus(kind, text) {
    el.serverStatusBadge.className = `status-badge status-${kind}`;
    el.serverStatusBadge.textContent = text;
  }

  // Render 무료 티어 콜드스타트 대비 60초 타임아웃 지원 fetch 래퍼
  async function apiFetch(path, options = {}, timeoutMs = 65000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const coldTimer = setTimeout(() => {
      el.coldStartBanner.classList.remove("hidden");
    }, 2500);

    try {
      const resp = await fetch(`${API_BASE_URL}${path}`, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
        signal: controller.signal,
      });

      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try {
          const errBody = await resp.json();
          detail = errBody.detail || JSON.stringify(errBody);
        } catch (_) {
          // ignore
        }
        throw new Error(detail);
      }
      return await resp.json();
    } catch (err) {
      if (err.name === "AbortError") {
        throw new Error("서버 응답 시간이 초과되었습니다. Render 무료 서버가 깨어나는 중일 수 있으니 잠시 후 다시 시도해 주세요.");
      }
      throw err;
    } finally {
      clearTimeout(timer);
      clearTimeout(coldTimer);
      el.coldStartBanner.classList.add("hidden");
    }
  }

  // 다크 모드 (보너스)
  function initTheme() {
    const saved = localStorage.getItem("stockpulse_theme");
    if (saved === "dark") {
      document.body.classList.add("dark");
      el.themeToggleBtn.textContent = "☀️ 라이트 모드";
    }
    el.themeToggleBtn.addEventListener("click", () => {
      const isDark = document.body.classList.toggle("dark");
      localStorage.setItem("stockpulse_theme", isDark ? "dark" : "light");
      el.themeToggleBtn.textContent = isDark ? "☀️ 라이트 모드" : "🌙 다크 모드";
      drawStockChart();
    });
  }

  // 종목 목록 로드
  async function loadStocks() {
    const data = await apiFetch("/api/stocks");
    state.stocks = data.stocks || [];
    if (state.stocks.length > 0) {
      el.stockSelect.innerHTML = "";
      state.stocks.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.symbol;
        opt.textContent = `${s.stock_name} (${s.symbol}) · ${s.count}일`;
        el.stockSelect.appendChild(opt);
      });
      if (!state.stocks.some((s) => s.symbol === state.symbol)) {
        state.symbol = state.stocks[0].symbol;
      }
      el.stockSelect.value = state.symbol;
      const found = state.stocks.find((s) => s.symbol === state.symbol);
      state.stockName = found ? found.stock_name : state.symbol;
    }
  }

  // 요약 + 보너스 심화 통계 + 목록 일괄 로드
  async function refreshStockDashboard() {
    const sym = encodeURIComponent(state.symbol);
    const [summary, stats, listRes] = await Promise.all([
      apiFetch(`/api/data/summary?symbol=${sym}`),
      apiFetch(`/api/data/statistics?symbol=${sym}`),
      apiFetch(`/api/data?symbol=${sym}`),
    ]);

    state.summary = summary;
    state.statistics = stats;
    state.dataItems = listRes.items || [];
    state.stockName = summary.stock_name || state.stockName;

    renderSummaryCards(summary);
    renderBonusStats(stats);
    drawStockChart();
    renderDataTable();
    el.dataFormTitle.textContent = `장 마감 데이터 추가 — ${state.stockName} (${state.symbol})`;
  }

  function renderSummaryCards(summary) {
    const m = summary.metrics || {};
    el.kpiStockTitle.textContent = `${summary.stock_name} (${summary.symbol})`;
    el.kpiPeriod.textContent = summary.period || "데이터 없음";

    el.kpiLatestClose.textContent = fmtWon(m.latest_close);
    const chg = Number(m.latest_change_pct || 0);
    el.kpiLatestChange.textContent = `${m.latest_date || "-"} · 전일 대비 ${fmtPct(chg)}`;
    el.kpiLatestChange.className = `kpi-sub ${chg > 0 ? "text-up" : chg < 0 ? "text-down" : ""}`;

    el.kpiAverage.textContent = fmtWon(m.average);
    const vsAvg = Number(m.vs_average_pct || 0);
    el.kpiVsAverage.textContent = `1년 평균가 대비 ${fmtPct(vsAvg)}`;
    el.kpiVsAverage.className = `kpi-sub ${vsAvg > 0 ? "text-up" : vsAvg < 0 ? "text-down" : ""}`;

    el.kpiHighLow.textContent = `${fmtWon(m.max)} / ${fmtWon(m.min)}`;
    el.kpiRangePosition.textContent = `1년 가격대 중 하위 ${Number(m.position_in_range_pct || 0).toFixed(1)}% 위치`;

    el.kpiTrend.textContent = summary.trend || "-";
    el.kpiCount.textContent = `총 ${summary.count || 0}거래일 저장됨`;
  }

  function renderBonusStats(stats) {
    const ma = stats.moving_averages || {};
    const ret = stats.returns_pct || {};
    const risk = stats.risk_metrics || {};

    el.statMa20.textContent = fmtWon(ma.ma20);
    el.statMa60.textContent = fmtWon(ma.ma60);
    el.statMa120.textContent = fmtWon(ma.ma120);
    el.statRet1y.textContent = fmtPct(ret.return_1y);
    el.statVol.textContent = `${Number(risk.daily_volatility_pct || 0).toFixed(2)}%`;
    el.statMdd.textContent = `${Number(risk.max_drawdown_pct || 0).toFixed(2)}%`;
  }

  // 보너스: 순수 HTML5 Canvas 1년 종가 + 20일선 + 평균가 기준선 차트
  function drawStockChart() {
    const canvas = el.stockChart;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(320, rect.width || 800);
    const height = 220;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const series = (state.statistics && state.statistics.series) || [];
    const avgVal = state.summary && state.summary.metrics ? state.summary.metrics.average : null;
    el.chartTitle.textContent = `${state.stockName} (${state.symbol}) 1년 종가 추세 & 평균가 기준선`;

    const styles = getComputedStyle(document.body);
    const gridColor = styles.getPropertyValue("--chart-grid").trim() || "#e2e8f0";
    const textColor = styles.getPropertyValue("--text-muted").trim() || "#64748b";
    const closeColor = styles.getPropertyValue("--chart-close").trim() || "#2563eb";
    const ma20Color = styles.getPropertyValue("--chart-ma20").trim() || "#f59e0b";
    const avgColor = styles.getPropertyValue("--chart-avg").trim() || "#ef4444";

    if (series.length < 2) {
      ctx.fillStyle = textColor;
      ctx.font = "13px sans-serif";
      ctx.fillText("시각화할 데이터가 부족합니다.", 20, 40);
      state.chartPoints = [];
      return;
    }

    const pad = { top: 18, right: 20, bottom: 28, left: 74 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;

    const allVals = series.flatMap((s) => [s.value, s.ma20]);
    if (avgVal) allVals.push(avgVal);
    let minY = Math.min(...allVals);
    let maxY = Math.max(...allVals);
    if (minY === maxY) {
      minY *= 0.95;
      maxY *= 1.05;
    } else {
      const margin = (maxY - minY) * 0.08;
      minY = Math.max(0, minY - margin);
      maxY += margin;
    }

    const xOf = (i) => pad.left + (i / (series.length - 1)) * plotW;
    const yOf = (v) => pad.top + ((maxY - v) / (maxY - minY)) * plotH;

    // 가로 그리드 & Y축 가격 라벨
    ctx.strokeStyle = gridColor;
    ctx.fillStyle = textColor;
    ctx.font = "11px sans-serif";
    ctx.lineWidth = 1;
    for (let g = 0; g <= 4; g++) {
      const val = minY + ((maxY - minY) * g) / 4;
      const y = yOf(val);
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(width - pad.right, y);
      ctx.stroke();
      ctx.fillText(Math.round(val).toLocaleString("ko-KR"), 6, y + 4);
    }

    // X축 날짜 라벨 (5개 구간)
    for (let k = 0; k <= 4; k++) {
      const idx = Math.round(((series.length - 1) * k) / 4);
      const x = xOf(idx);
      ctx.fillText(series[idx].date.slice(2), Math.max(pad.left, Math.min(x - 24, width - 66)), height - 8);
    }

    // 1년 평균가 기준 점선
    if (avgVal) {
      const avgY = yOf(avgVal);
      ctx.save();
      ctx.strokeStyle = avgColor;
      ctx.setLineDash([5, 5]);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(pad.left, avgY);
      ctx.lineTo(width - pad.right, avgY);
      ctx.stroke();
      ctx.restore();
    }

    // 20일 이동평균선
    ctx.strokeStyle = ma20Color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    series.forEach((pt, idx) => {
      const x = xOf(idx);
      const y = yOf(pt.ma20);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // 일별 종가 선
    ctx.strokeStyle = closeColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    const chartPoints = [];
    series.forEach((pt, idx) => {
      const x = xOf(idx);
      const y = yOf(pt.value);
      chartPoints.push({ x, y, ...pt });
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    state.chartPoints = chartPoints;
  }

  function initChartTooltip() {
    el.stockChart.addEventListener("mousemove", (e) => {
      if (!state.chartPoints.length) return;
      const rect = el.stockChart.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      let nearest = state.chartPoints[0];
      let minDist = Math.abs(mouseX - nearest.x);
      for (const pt of state.chartPoints) {
        const d = Math.abs(mouseX - pt.x);
        if (d < minDist) {
          minDist = d;
          nearest = pt;
        }
      }
      el.chartTooltip.innerHTML = `
        <div><strong>${nearest.date}</strong></div>
        <div>종가: ${fmtWon(nearest.value)} (${fmtPct(nearest.change_pct)})</div>
        <div>20일선: ${fmtWon(nearest.ma20)}</div>
        ${nearest.memo ? `<div style="margin-top:4px;color:#fde68a;">${escapeHtml(nearest.memo)}</div>` : ""}
      `;
      const leftPos = Math.min(rect.width - 260, Math.max(8, nearest.x + 12));
      const topPos = Math.max(8, nearest.y - 40);
      el.chartTooltip.style.left = `${leftPos}px`;
      el.chartTooltip.style.top = `${topPos}px`;
      el.chartTooltip.classList.remove("hidden");
    });

    el.stockChart.addEventListener("mouseleave", () => {
      el.chartTooltip.classList.add("hidden");
    });
    window.addEventListener("resize", () => drawStockChart());
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // 대화 기록 사이드바
  async function loadConversations() {
    const res = await apiFetch("/api/conversations");
    state.conversations = res.items || [];
    renderConversationList();
  }

  function renderConversationList() {
    if (!state.conversations.length) {
      el.conversationList.innerHTML = `<li class="empty-hint">저장된 대화가 없습니다.</li>`;
      return;
    }
    el.conversationList.innerHTML = "";
    state.conversations.forEach((conv) => {
      const li = document.createElement("li");
      li.className = `conv-item ${conv.id === state.currentConversationId ? "active" : ""}`;
      const dateStr = (conv.updated_at || "").slice(0, 16).replace("T", " ");
      li.innerHTML = `
        <div class="conv-meta">
          <div class="conv-title">${escapeHtml(conv.title)}</div>
          <div class="conv-date">${escapeHtml(dateStr)} · 메시지 ${conv.message_count || 0}건</div>
        </div>
        <button class="conv-del-btn" type="button" title="대화 삭제">🗑</button>
      `;

      li.querySelector(".conv-meta").addEventListener("click", () => openConversation(conv.id));
      li.querySelector(".conv-del-btn").addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm("이 대화 기록을 삭제하시겠습니까?")) return;
        try {
          await apiFetch(`/api/conversations/${encodeURIComponent(conv.id)}`, { method: "DELETE" });
          if (state.currentConversationId === conv.id) {
            resetChatView();
          }
          await loadConversations();
        } catch (err) {
          showError(`대화 삭제 실패: ${err.message}`);
        }
      });
      el.conversationList.appendChild(li);
    });
  }

  async function openConversation(convId) {
    try {
      const conv = await apiFetch(`/api/conversations/${encodeURIComponent(convId)}`);
      state.currentConversationId = conv.id;

      // 대화에 연결된 종목이 다르면 종목 드롭다운도 동기화
      if (conv.symbol && conv.symbol !== state.symbol) {
        state.symbol = conv.symbol;
        el.stockSelect.value = conv.symbol;
        await refreshStockDashboard();
      }

      switchTab("chat");
      el.chatMessages.innerHTML = "";
      (conv.messages || []).forEach((m) => appendChatBubble(m.role, m.content, m.tools_used));
      renderConversationList();
    } catch (err) {
      showError(`대화 불러오기 실패: ${err.message}`);
    }
  }

  function resetChatView() {
    state.currentConversationId = null;
    el.chatMessages.innerHTML = `
      <div class="chat-welcome">
        현재 선택 종목: <strong>${escapeHtml(state.stockName)} (${escapeHtml(state.symbol)})</strong><br/>
        위의 3대 역할 버튼을 누르거나 자유롭게 질문해 보세요.
      </div>
    `;
    renderConversationList();
  }

  function appendChatBubble(role, content, toolsUsed = []) {
    const welcome = el.chatMessages.querySelector(".chat-welcome");
    if (welcome) welcome.remove();

    const bubble = document.createElement("div");
    bubble.className = `msg-bubble ${role === "user" ? "msg-user" : "msg-assistant"}`;

    if (role === "assistant" && Array.isArray(toolsUsed) && toolsUsed.length > 0) {
      const badgeRow = document.createElement("div");
      badgeRow.className = "tools-badge-row";
      toolsUsed.forEach((t) => {
        const b = document.createElement("span");
        b.className = "tool-badge";
        b.textContent = `🔧 도구 호출: ${t.tool}`;
        badgeRow.appendChild(b);
      });
      bubble.appendChild(badgeRow);
    }

    const textNode = document.createElement("div");
    textNode.textContent = content;
    bubble.appendChild(textNode);

    el.chatMessages.appendChild(bubble);
    el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
  }

  async function sendChatMessage(messageText) {
    const text = messageText.trim();
    if (!text) return;

    hideError();
    appendChatBubble("user", text);
    el.chatInput.value = "";
    el.chatLoading.classList.remove("hidden");
    el.sendChatBtn.disabled = true;

    try {
      const res = await apiFetch("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          symbol: state.symbol,
          message: text,
          conversation_id: state.currentConversationId,
          use_tools: el.useToolsCheckbox.checked,
        }),
      });
      state.currentConversationId = res.conversation_id;
      appendChatBubble("assistant", res.reply, res.tools_used || []);
      await loadConversations();
    } catch (err) {
      showError(`AI 응답 생성 실패: ${err.message}`);
      appendChatBubble("assistant", `⚠️ 오류가 발생했습니다: ${err.message}`);
    } finally {
      el.chatLoading.classList.add("hidden");
      el.sendChatBtn.disabled = false;
      el.chatInput.focus();
    }
  }

  // 데이터 관리 (CRUD)
  function renderDataTable() {
    const q = (el.tableSearchInput.value || "").trim().toLowerCase();
    const reversed = [...state.dataItems].reverse();
    const filtered = q
      ? reversed.filter(
          (item) =>
            item.date.toLowerCase().includes(q) ||
            (item.memo || "").toLowerCase().includes(q) ||
            String(item.value).includes(q)
        )
      : reversed;

    el.tableCountBadge.textContent = `${filtered.length}건 표시 (전체 ${state.dataItems.length}건)`;

    if (!filtered.length) {
      el.dataTableBody.innerHTML = `<tr><td colspan="5" class="empty-hint">표시할 데이터가 없습니다.</td></tr>`;
      return;
    }

    el.dataTableBody.innerHTML = "";
    filtered.forEach((item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(item.date)}</td>
        <td>${escapeHtml(item.stock_name)}</td>
        <td class="num">${fmtWon(item.value)}</td>
        <td>${escapeHtml(item.memo || "-")}</td>
        <td>
          <button type="button" class="btn btn-outline btn-sm edit-btn">수정</button>
          <button type="button" class="btn btn-danger delete-btn">삭제</button>
        </td>
      `;
      tr.querySelector(".edit-btn").addEventListener("click", () => startEditItem(item));
      tr.querySelector(".delete-btn").addEventListener("click", () => deleteItem(item));
      el.dataTableBody.appendChild(tr);
    });
  }

  function startEditItem(item) {
    el.editItemId.value = item.id;
    el.inputDate.value = item.date;
    el.inputValue.value = Math.round(item.value);
    el.inputMemo.value = item.memo || "";
    el.dataFormTitle.textContent = `데이터 수정 중 (${item.date} · ${item.stock_name})`;
    el.saveDataBtn.textContent = "수정 완료";
    el.cancelEditBtn.classList.remove("hidden");
    el.inputValue.focus();
  }

  function cancelEditItem() {
    el.editItemId.value = "";
    el.dataForm.reset();
    el.inputDate.value = new Date().toISOString().slice(0, 10);
    el.dataFormTitle.textContent = `장 마감 데이터 추가 — ${state.stockName} (${state.symbol})`;
    el.saveDataBtn.textContent = "데이터 저장";
    el.cancelEditBtn.classList.add("hidden");
  }

  async function deleteItem(item) {
    if (!confirm(`${item.date} (${fmtWon(item.value)}) 데이터를 삭제하시겠습니까?`)) return;
    try {
      await apiFetch(`/api/data/${encodeURIComponent(item.id)}`, { method: "DELETE" });
      el.dataFormFeedback.textContent = `✅ ${item.date} 데이터가 삭제되었습니다.`;
      await Promise.all([loadStocks(), refreshStockDashboard()]);
    } catch (err) {
      showError(`데이터 삭제 실패: ${err.message}`);
    }
  }

  // 보너스: CSV / JSON 내보내기
  function downloadBlob(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function exportCsv() {
    if (!state.dataItems.length) return showError("내보낼 데이터가 없습니다.");
    const header = "date,symbol,stock_name,value,memo";
    const rows = state.dataItems.map((r) => {
      const safeMemo = `"${String(r.memo || "").replace(/"/g, '""')}"`;
      return `${r.date},${r.symbol},${r.stock_name},${r.value},${safeMemo}`;
    });
    // Excel 한글 깨짐 방지용 UTF-8 BOM 추가
    const csvContent = "\uFEFF" + [header, ...rows].join("\n");
    downloadBlob(`${state.symbol}_${state.stockName}_1y.csv`, csvContent, "text/csv;charset=utf-8;");
  }

  function exportJson() {
    if (!state.dataItems.length) return showError("내보낼 데이터가 없습니다.");
    const payload = {
      exported_at: new Date().toISOString(),
      symbol: state.symbol,
      stock_name: state.stockName,
      summary: state.summary,
      items: state.dataItems,
    };
    downloadBlob(
      `${state.symbol}_${state.stockName}_1y.json`,
      JSON.stringify(payload, null, 2),
      "application/json;charset=utf-8;"
    );
  }

  // 탭 전환
  function switchTab(tab) {
    const isChat = tab === "chat";
    el.tabChatBtn.classList.toggle("active", isChat);
    el.tabDataBtn.classList.toggle("active", !isChat);
    el.chatPanel.classList.toggle("hidden", !isChat);
    el.dataPanel.classList.toggle("hidden", isChat);
  }

  // 이벤트 바인딩
  function bindEvents() {
    el.closeErrorBtn.addEventListener("click", hideError);
    el.tabChatBtn.addEventListener("click", () => switchTab("chat"));
    el.tabDataBtn.addEventListener("click", () => switchTab("data"));
    el.newChatBtn.addEventListener("click", () => {
      switchTab("chat");
      resetChatView();
    });

    el.stockSelect.addEventListener("change", async () => {
      state.symbol = el.stockSelect.value;
      resetChatView();
      cancelEditItem();
      try {
        await refreshStockDashboard();
      } catch (err) {
        showError(`종목 데이터 로드 실패: ${err.message}`);
      }
    });

    document.querySelectorAll(".chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const prompt = btn.getAttribute("data-prompt");
        if (prompt) sendChatMessage(prompt);
      });
    });

    el.chatForm.addEventListener("submit", (e) => {
      e.preventDefault();
      sendChatMessage(el.chatInput.value);
    });

    document.querySelectorAll(".tag-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tag = btn.getAttribute("data-tag") || "";
        if (!el.inputMemo.value.startsWith(tag)) {
          el.inputMemo.value = tag + el.inputMemo.value;
        }
        el.inputMemo.focus();
      });
    });

    el.cancelEditBtn.addEventListener("click", cancelEditItem);
    el.tableSearchInput.addEventListener("input", renderDataTable);
    el.exportCsvBtn.addEventListener("click", exportCsv);
    el.exportJsonBtn.addEventListener("click", exportJson);

    el.dataForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      hideError();
      const editId = el.editItemId.value;
      const payload = {
        symbol: state.symbol,
        stock_name: state.stockName,
        date: el.inputDate.value,
        value: Number(el.inputValue.value),
        memo: el.inputMemo.value.trim(),
      };

      el.saveDataBtn.disabled = true;
      try {
        if (editId) {
          await apiFetch(`/api/data/${encodeURIComponent(editId)}`, {
            method: "PUT",
            body: JSON.stringify(payload),
          });
          el.dataFormFeedback.textContent = `✅ ${payload.date} 데이터가 수정되었습니다.`;
        } else {
          await apiFetch("/api/data", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          el.dataFormFeedback.textContent = `✅ ${payload.date} 장 마감 데이터가 추가되었습니다.`;
        }
        cancelEditItem();
        await Promise.all([loadStocks(), refreshStockDashboard()]);
      } catch (err) {
        showError(`데이터 저장 실패: ${err.message}`);
      } finally {
        el.saveDataBtn.disabled = false;
      }
    });
  }

  // 앱 초기화
  async function init() {
    initTheme();
    initChartTooltip();
    bindEvents();
    el.inputDate.value = new Date().toISOString().slice(0, 10);

    try {
      await apiFetch("/");
      setServerStatus("ok", "서버 연결됨");
      await loadStocks();
      await Promise.all([refreshStockDashboard(), loadConversations()]);
      resetChatView();
    } catch (err) {
      setServerStatus("err", "서버 연결 실패");
      showError(`백엔드(${API_BASE_URL})에 연결할 수 없습니다: ${err.message}`);
    }
  }

  init();
})();
