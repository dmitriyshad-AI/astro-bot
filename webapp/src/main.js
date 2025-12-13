const tg = window.Telegram?.WebApp;
if (tg) tg.ready();

const app = document.getElementById("app");
const STORAGE_KEY = "astroglass_last_chart";

function showToast(message) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2000);
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

const isTelegram = Boolean(tg);
const theme = tg?.themeParams || {};
const root = document.documentElement;
if (theme.bg_color) {
  root.style.setProperty("--text", theme.text_color || "#0f172a");
  root.style.setProperty("--muted", theme.hint_color || "#475569");
}

let statusText = isTelegram ? "Telegram WebApp" : "Браузер";
let statusDetail = tg?.initDataUnsafe?.user
  ? `Привет, ${tg.initDataUnsafe.user.first_name}${tg.initDataUnsafe.user.last_name ? " " + tg.initDataUnsafe.user.last_name : ""}`
  : "Гость";
let verifiedUser = null;
let form = {
  birth_date: "",
  birth_time: "",
  place: "",
};
let loading = false;
let error = "";
let result = null;
let chartDetails = null;
let placeSuggestions = [];
let placeLoading = false;
let currentTab = "highlights";
let insightsLoading = false;
let insightsText = "";
let askText = "";
let askLoading = false;
let chatHistory = [];
let recentCharts = [];
let insightsError = "";
let askError = "";
let lastChart = loadLastChart();

if (lastChart) {
  result = lastChart.result;
  chartDetails = lastChart.chartDetails;
  insightsText = lastChart.insightsText || "";
  chatHistory = lastChart.chatHistory || [];
}

function debounce(fn, delay = 300) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), delay);
  };
}

function formatDateInput(raw) {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  const parts = [];
  if (digits.length > 0) parts.push(digits.slice(0, 2));
  if (digits.length > 2) parts.push(digits.slice(2, 4));
  if (digits.length > 4) parts.push(digits.slice(4, 8));
  return parts.join(".");
}

function formatTimeInput(raw) {
  const digits = raw.replace(/\D/g, "").slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}:${digits.slice(2, 4)}`;
}

async function fetchWhoAmI(initData) {
  try {
    const res = await fetch("/api/auth/whoami", {
      method: "POST",
      headers: { Authorization: `tma ${initData}` },
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || "Auth failed");
    verifiedUser = data.user;
    statusText = "Verified";
    statusDetail = data.user?.first_name
      ? `Привет, ${data.user.first_name}${data.user.last_name ? " " + data.user.last_name : ""}`
      : "Пользователь";
    render();
  } catch (err) {
    statusText = "Auth error";
    statusDetail = err.message || "Не удалось проверить initData";
    verifiedUser = null;
    showToast(err.message || "Auth error");
    render();
  }
}

function validateForm() {
  const dateRe = /^\d{2}\.\d{2}\.\d{4}$/;
  if (!dateRe.test(form.birth_date)) return "Дата должна быть в формате ДД.ММ.ГГГГ";
  if (form.birth_time && !/^\d{2}:\d{2}$/.test(form.birth_time)) return "Время должно быть ЧЧ:ММ или оставьте пустым";
  if (!form.place) return "Укажите место рождения";
  return "";
}

const doPlaceSuggest = debounce(async (query) => {
  if (!query || query.length < 2) {
    placeSuggestions = [];
    placeLoading = false;
    render();
    return;
  }
  placeLoading = true;
  render();
  try {
    const res = await fetch(`/api/geo/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (data.ok) {
      placeSuggestions = [
        {
          display_name: data.location.display_name,
        },
      ];
    } else {
      placeSuggestions = [];
    }
  } catch {
    placeSuggestions = [];
  } finally {
    placeLoading = false;
    render();
  }
}, 400);

async function submitForm() {
  error = "";
  const validationError = validateForm();
  if (validationError) {
    error = validationError;
    render();
    return;
  }
  loading = true;
  result = null;
  chartDetails = null;
  insightsText = "";
  chatHistory = [];
  askText = "";
  askLoading = false;
  insightsError = "";
  askError = "";
  insightsLoading = false;
  render();
  try {
    const payload = {
      birth_date: form.birth_date,
      birth_time: form.birth_time || null,
      place: form.place,
      telegram_user_id: verifiedUser?.id,
    };
    const res = await fetch("/api/natal/calc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || "Ошибка расчёта");
    result = data;
    chartDetails = parseChart(data.chart);
    saveLastChart(result, chartDetails, insightsText, chatHistory);
  } catch (e) {
    error = e.message || "Ошибка запроса";
  } finally {
    loading = false;
    render();
  }
}

async function fetchInsights() {
  if (!result?.chart_id) {
    showToast("Сначала рассчитайте карту");
    return;
  }
  insightsLoading = true;
  insightsError = "";
  render();
  try {
    const res = await fetch(`/api/insights/${result.chart_id}`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || "Не удалось получить инсайты");
    insightsText = data.insights || "";
    saveLastChart(result, chartDetails, insightsText, chatHistory);
    if (!insightsText) showToast("Инсайты пока пустые");
  } catch (e) {
    insightsError = e.message || "Ошибка инсайтов";
    showToast(e.message || "Ошибка инсайтов");
  } finally {
    insightsLoading = false;
    render();
  }
}

async function sendQuestion() {
  if (!result?.chart_id) {
    showToast("Сначала рассчитайте карту");
    return;
  }
  if (!askText.trim()) {
    showToast("Введите вопрос");
    return;
  }
  askLoading = true;
  askError = "";
  render();
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chart_id: result.chart_id, question: askText.trim() }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || "Ошибка ответа");
    chatHistory = data.history || [...chatHistory, { question: askText.trim(), answer: data.answer }];
    askText = "";
    saveLastChart(result, chartDetails, insightsText, chatHistory);
  } catch (e) {
    askError = e.message || "Ошибка запроса";
    showToast(e.message || "Ошибка запроса");
  } finally {
    askLoading = false;
    render();
  }
}

async function fetchRecentCharts() {
  try {
    const res = await fetch("/api/charts/recent?limit=3");
    const data = await res.json();
    if (data.ok) {
      recentCharts = data.charts || [];
      render();
    }
  } catch {
    /* ignore */
  }
}

async function openChartById(chartId) {
  if (!chartId) return;
  loading = true;
  render();
  try {
    const res = await fetch(`/api/natal/${chartId}`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || "Не удалось открыть карту");
    result = {
      ok: true,
      chart_id: chartId,
      wheel_url: data.wheel_url,
      summary: data.summary,
      llm_summary: data.llm_summary,
      chart: data.chart,
    };
    chartDetails = parseChart(data.chart);
    insightsText = "";
    chatHistory = [];
    askText = "";
    askError = "";
    insightsError = "";
    saveLastChart(result, chartDetails, insightsText, chatHistory);
  } catch (e) {
    showToast(e.message || "Ошибка загрузки карты");
  } finally {
    loading = false;
    render();
  }
}

function parseChart(rawChart) {
  if (!rawChart) return null;
  let chartObj = rawChart;
  if (typeof rawChart === "string") {
    try {
      chartObj = JSON.parse(rawChart);
    } catch {
      return null;
    }
  }
  const subject = chartObj.subject || {};
  const aspects = chartObj.aspects || [];

  const highlightNames = ["sun", "moon", "ascendant", "medium_coeli"];
  const highlights = highlightNames
    .map((name) => {
      const key = Object.keys(subject).find((k) => k.toLowerCase() === name);
      if (!key || !subject[key]) return null;
      const pt = subject[key];
      return `${key.toUpperCase()}: ${pt.sign} ${pt.position.toFixed(2)}°`;
    })
    .filter(Boolean);

  const houses = [];
  const houseKeys = [
    "first_house",
    "second_house",
    "third_house",
    "fourth_house",
    "fifth_house",
    "sixth_house",
    "seventh_house",
    "eighth_house",
    "ninth_house",
    "tenth_house",
    "eleventh_house",
    "twelfth_house",
  ];
  houseKeys.forEach((hk, idx) => {
    if (subject[hk]) houses.push({ num: idx + 1, sign: subject[hk].sign, pos: subject[hk].position });
  });

  const majorAspects = aspects
    .filter((a) => ["conjunction", "opposition", "trine", "square", "sextile"].includes(a.aspect))
    .sort((a, b) => Math.abs(a.orbit) - Math.abs(b.orbit))
    .slice(0, 12)
    .map((a) => ({
      text: `${a.p1_name} — ${a.p2_name}: ${a.aspect} (орб ${Math.abs(a.orbit).toFixed(2)}°)`,
    }));

  const planetKeys = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto", "chiron"];
  const planets = planetKeys
    .map((k) => subject[k])
    .filter(Boolean)
    .map((pt) => `${pt.name}: ${pt.sign} ${pt.position.toFixed(2)}° (дом ${prettyHouse(pt.house)})${pt.retrograde ? " R" : ""}`);

  return {
    highlights,
    houses,
    aspects: majorAspects,
    planets,
  };
}

function prettyHouse(name) {
  if (!name) return "-";
  const mapping = {
    First_House: "1",
    Second_House: "2",
    Third_House: "3",
    Fourth_House: "4",
    Fifth_House: "5",
    Sixth_House: "6",
    Seventh_House: "7",
    Eighth_House: "8",
    Ninth_House: "9",
    Tenth_House: "10",
    Eleventh_House: "11",
    Twelfth_House: "12",
  };
  return mapping[name] || name;
}

function renderTabs() {
  const tabs = [
    { id: "highlights", label: "Основное" },
    { id: "planets", label: "Планеты" },
    { id: "houses", label: "Дома" },
    { id: "aspects", label: "Аспекты" },
    { id: "insights", label: "Инсайты" },
    { id: "chat", label: "Вопрос" },
    { id: "wheel", label: "Wheel" },
  ];
  return `
    <div class="tabs">
      ${tabs
        .map(
          (t) => `<button class="tab ${currentTab === t.id ? "active" : ""}" data-tab="${t.id}">${t.label}</button>`
        )
        .join("")}
    </div>
  `;
}

function renderResult() {
  if (!result) return "";
  const wheelLink = result.wheel_url || "";
  const chart = chartDetails;
  return `
    <div class="card" style="margin-top:12px;">
      <div class="muted" style="margin-bottom:8px;">Результат</div>
      ${renderTabs()}
      <div class="list">
        ${renderTabContent(chart, wheelLink)}
      </div>
      ${currentTab === "insights" ? renderInsightsButton() : ""}
    </div>
  `;
}

function renderTabContent(chart, wheelLink) {
  if (currentTab === "wheel") {
    return wheelLink
      ? `<div class="section-title">SVG wheel</div><div style="margin-top:8px; border-radius:12px; overflow:hidden; border:1px solid #e2e8f0;"><object data="${wheelLink}" type="image/svg+xml" style="width:100%; min-height:320px;"></object></div>`
      : "<div class='muted-small'>Нет SVG</div>";
  }
  if (currentTab === "insights") {
    if (insightsLoading) return "<div class='muted-small'>Генерирую инсайты...</div>";
    if (insightsText) return `<div class="list"><div>${insightsText.replace(/\n/g, "<br/>")}</div></div>`;
    return `
      ${insightsError ? `<div class="error">${insightsError}</div>` : ""}
      <div class='muted-small'>Нет инсайтов. Нажмите 'Сгенерировать инсайты'.</div>
    `;
  }
  if (currentTab === "chat") {
    const historyHtml =
      chatHistory && chatHistory.length
        ? chatHistory
            .map(
              (m) => `
            <div class="chat-item">
              <div class="chat-q">Вопрос: ${m.question}</div>
              <div class="chat-a">Ответ: ${m.answer || ""}</div>
            </div>`
            )
            .join("")
        : "<div class='muted-small'>Пока нет вопросов.</div>";
    return `
      <div class="field">
        <label for="ask">Вопрос по карте</label>
        <textarea class="input" id="ask" placeholder="Задайте вопрос" rows="3">${askText}</textarea>
      </div>
      ${askError ? `<div class="error">${askError}</div>` : ""}
      <div class="actions">
        <button class="btn" id="ask-btn" ${askLoading ? "disabled" : ""}>${askLoading ? "Отправляю..." : "Спросить"}</button>
      </div>
      <div class="section-title">История</div>
      <div class="list chat-list">${historyHtml}</div>
    `;
  }
  if (!chart) return "<div class='muted-small'>Нет данных</div>";
  if (currentTab === "highlights") {
    return `
      <div><strong>Summary:</strong> ${result.llm_summary ? result.llm_summary : result.summary ? result.summary.split("\\n")[0] : "—"}</div>
      <div class="section-title">Солнце / Луна / Asc / MC</div>
      <div class="pill-row">
        ${chart.highlights && chart.highlights.length ? chart.highlights.map((h) => `<span class="tag">${h}</span>`).join("") : "<div class='muted-small'>Нет данных</div>"}
      </div>
    `;
  }
  if (currentTab === "planets") {
    return chart.planets && chart.planets.length
      ? chart.planets.map((p) => `<div>${p}</div>`).join("")
      : "<div class='muted-small'>Нет данных</div>";
  }
  if (currentTab === "houses") {
    return chart.houses && chart.houses.length
      ? chart.houses.map((h) => `<div class="tag">Дом ${h.num}: ${h.sign} ${h.pos.toFixed(2)}°</div>`).join("")
      : "<div class='muted-small'>Нет данных</div>";
  }
  if (currentTab === "aspects") {
    return chart.aspects && chart.aspects.length
      ? chart.aspects.map((a) => `<div>${a.text}</div>`).join("")
      : "<div class='muted-small'>Нет аспектов</div>";
  }
  return "";
}

function renderDebugBlock() {
  if (isTelegram) return "";
  if (qs("debug") !== "1") return "";
  return `
    <div class="card" style="margin-top:12px;">
      <div class="muted" style="margin-bottom:8px;">Debug validate initData (browser)</div>
      <textarea id="debug-initdata" style="width:100%; min-height:80px; border-radius:8px; padding:8px; border:1px solid #e2e8f0;"></textarea>
      <div class="actions" style="margin-top:10px;">
        <button class="btn" id="debug-validate">Validate</button>
      </div>
    </div>
  `;
}

function renderRecentCharts() {
  if (!recentCharts || !recentCharts.length) {
    return `
      <div class="card" style="margin-top:12px;">
        <div class="muted">Недавние карты</div>
        <div class="muted-small">Пока нет сохранённых карт</div>
        ${lastChart ? `<div class="actions" style="margin-top:10px;"><button class="btn secondary" data-open-chart="${lastChart?.result?.chart_id || ""}">Открыть последнюю</button></div>` : ""}
      </div>
    `;
  }
  const items = recentCharts
    .map(
      (c) => {
        const datePart = c.birth_date ? c.birth_date : "Дата?";
        const timePart = c.birth_time ? `, ${c.birth_time}` : "";
        const placePart = c.place ? ` — ${c.place}` : "";
        const summaryPart = c.summary ? `<div class="muted-small">${c.summary}</div>` : "";
        return `
      <div class="recent-item">
        <div>
          <div class="recent-summary">${datePart}${timePart}${placePart}</div>
          ${summaryPart}
        </div>
        <button class="btn secondary" data-open-chart="${c.id}">Открыть</button>
      </div>`
        ;
      }
    )
    .join("");
  return `
    <div class="card" style="margin-top:12px;">
      <div class="muted" style="margin-bottom:8px;">Недавние карты</div>
      <div class="recent-list">${items}</div>
      ${lastChart ? `<div class="actions" style="margin-top:10px;"><button class="btn secondary" data-open-chart="${lastChart?.result?.chart_id || ""}">Открыть последнюю</button></div>` : ""}
    </div>
  `;
}

function renderInsightsButton() {
  if (!result?.chart_id) return "";
  const label = insightsLoading ? "Генерирую..." : insightsText ? "Обновить инсайты" : "Сгенерировать инсайты";
  return `
    <div class="actions" style="margin-top:12px;">
      <button class="btn" id="insights-btn" ${insightsLoading ? "disabled" : ""}>${label}</button>
    </div>
  `;
}

function saveLastChart(res, chart, insights, chat) {
  try {
    if (!res) {
      localStorage.removeItem(STORAGE_KEY);
      lastChart = null;
      return;
    }
    lastChart = { result: res, chartDetails: chart, insightsText: insights || "", chatHistory: chat || [] };
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(lastChart)
    );
  } catch {
    /* ignore */
  }
}

function loadLastChart() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function render() {
  app.innerHTML = `
    <div class="page">
      <div class="hero">
        <h1>AstroGlass</h1>
        <p>Лёгкая астрология в мини‑приложении Telegram.</p>
      </div>
      <div class="card">
        <div class="status-row">
          <div>
            <div class="pill">${statusText}</div>
            <div class="muted">${statusDetail}</div>
          </div>
          <div class="muted">${verifiedUser ? "auth" : "guest"}</div>
        </div>
        <div class="field">
          <label for="birth_date">Дата рождения</label>
          <input class="input" id="birth_date" type="text" placeholder="ДД.ММ.ГГГГ" value="${form.birth_date}" />
        </div>
        <div class="row">
          <div class="field">
            <label for="birth_time">Время</label>
            <input class="input" id="birth_time" type="text" placeholder="ЧЧ:ММ или пусто" value="${form.birth_time}" />
          </div>
          <div class="field">
            <label>&nbsp;</label>
            <span class="muted-small">Можно оставить пустым</span>
          </div>
        </div>
        <div class="field">
          <label for="place">Место рождения</label>
          <input class="input" id="place" type="text" placeholder="Город, страна" value="${form.place}" />
          ${placeLoading ? '<div class="muted-small"><span class="spinner"></span> Поиск...</div>' : ""}
          ${
            placeSuggestions && placeSuggestions.length
              ? `<div class="suggestions">${placeSuggestions
                  .map((s, idx) => `<div data-sidx="${idx}">${s.display_name}</div>`)
                  .join("")}</div>`
              : ""
          }
        </div>
        ${error ? `<div class="error">${error}</div>` : ""}
        ${loading ? `<div class="loading">Считаю...</div>` : ""}
        <div class="actions">
      <button class="btn" id="continue-btn" ${loading ? "disabled" : ""}>${loading ? "Считаю..." : "Рассчитать"}</button>
      <button class="btn secondary" id="clear-btn">Очистить</button>
    </div>
  </div>
  ${renderRecentCharts()}
  ${renderResult()}
  ${renderDebugBlock()}
</div>
<div class="toast"></div>
`;

  document.getElementById("continue-btn")?.addEventListener("click", () => {
    form.birth_date = document.getElementById("birth_date").value.trim();
    form.birth_time = document.getElementById("birth_time").value.trim();
    form.place = document.getElementById("place").value.trim();
    submitForm();
  });

  document.getElementById("clear-btn")?.addEventListener("click", () => {
    form = { birth_date: "", birth_time: "", place: "" };
    error = "";
    result = null;
    chartDetails = null;
    placeSuggestions = [];
    insightsText = "";
    insightsLoading = false;
    chatHistory = [];
    askText = "";
    askLoading = false;
    saveLastChart(null, null, null, null);
    render();
  });

  document.getElementById("place")?.addEventListener("input", (e) => {
    form.place = e.target.value;
    doPlaceSuggest(form.place);
  });

  document.getElementById("birth_date")?.addEventListener("input", (e) => {
    const formatted = formatDateInput(e.target.value);
    e.target.value = formatted;
    form.birth_date = formatted;
  });
  document.getElementById("birth_time")?.addEventListener("input", (e) => {
    const formatted = formatTimeInput(e.target.value);
    e.target.value = formatted;
    form.birth_time = formatted;
  });
  document.getElementById("ask")?.addEventListener("input", (e) => {
    askText = e.target.value;
  });

  document.querySelectorAll(".suggestions div")?.forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.sidx);
      if (!Number.isNaN(idx) && placeSuggestions[idx]) {
        form.place = placeSuggestions[idx].display_name;
        placeSuggestions = [];
        render();
      }
    });
  });

  document.querySelectorAll(".tab")?.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      if (tab) {
        currentTab = tab;
        render();
      }
    });
  });

  const debugBtn = document.getElementById("debug-validate");
  if (debugBtn) {
    debugBtn.addEventListener("click", async () => {
      const val = document.getElementById("debug-initdata").value.trim();
      if (!val) return;
      try {
        const res = await fetch("/api/auth/whoami", {
          method: "POST",
          headers: { Authorization: `tma ${val}` },
        });
        const data = await res.json();
        showToast(data.ok ? "valid" : data.error?.message || "invalid");
      } catch (e) {
        showToast("error");
      }
    });
  }

  document.getElementById("insights-btn")?.addEventListener("click", fetchInsights);
  document.getElementById("ask-btn")?.addEventListener("click", sendQuestion);
  document.querySelectorAll("[data-open-chart]")?.forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = btn.getAttribute("data-open-chart");
      if (cid) openChartById(cid);
    });
  });
}

render();

if (isTelegram && tg?.initData) {
  fetchWhoAmI(tg.initData);
} else if (qs("debug") === "1") {
  showToast("Debug mode: можно вставить initData");
}

fetchRecentCharts();
