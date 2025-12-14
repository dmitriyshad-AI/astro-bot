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

function haptic() {
  try {
    tg?.HapticFeedback?.impactOccurred("light");
  } catch {
    /* ignore */
  }
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
let compatForm = {
  self_date: "",
  self_time: "",
  self_place: "",
  partner_date: "",
  partner_time: "",
  partner_place: "",
};
let compatLoading = false;
let compatError = "";
let compatResult = null;
let debugEvents = [];
let selfPlaceSuggestions = [];
let partnerPlaceSuggestions = [];
let selfPlaceLoading = false;
let partnerPlaceLoading = false;
let modalContent = "";
let modalVisible = false;
let onboardingStep = 0;
let onboardingVisible = false;
const ONBOARDING_KEY = "astroglass_onboarding_done";

function copyShareText() {
  try {
    const parts = [];
    if (result?.llm_summary) parts.push(`Моя карта: ${result.llm_summary}`);
    if (compatResult?.score) parts.push(`Совместимость: ${compatResult.score.value ?? "?"} — ${compatResult.score.description ?? ""}`);
    if (compatResult?.key_aspects?.length) {
      const keyTxt = compatResult.key_aspects.slice(0, 3).map((a) => `${a.p1}—${a.p2} (${a.aspect})`).join("; ");
      parts.push(`Ключевые аспекты: ${keyTxt}`);
    }
    const text = parts.join("\n\n") || "AstroGlass";
    if (navigator.share) {
      navigator.share({ text }).catch(() => {});
    } else {
      navigator.clipboard?.writeText(text);
      showToast("Скопировано");
    }
  } catch {
    showToast("Не удалось скопировать");
  }
}

function showModal(text) {
  modalContent = text;
  modalVisible = true;
  haptic();
  render();
}

function shareCompatText() {
  try {
    const parts = [];
    if (compatResult?.score) parts.push(`Совместимость: ${compatResult.score.value ?? "?"} — ${compatResult.score.description ?? ""}`);
    if (compatResult?.key_aspects?.length) {
      const keyTxt = compatResult.key_aspects.slice(0, 3).map((a) => `${a.p1}—${a.p2} (${a.aspect})`).join("; ");
      parts.push(`Ключевые аспекты: ${keyTxt}`);
    }
    const text = parts.join("\n\n") || "Совместимость AstroGlass";
    if (navigator.share) {
      navigator.share({ text }).catch(() => {});
    } else {
      navigator.clipboard?.writeText(text);
      showToast("Скопировано");
    }
  } catch {
    showToast("Не удалось скопировать");
  }
}

function startOnboarding() {
  if (localStorage.getItem(ONBOARDING_KEY)) return;
  onboardingStep = 0;
  onboardingVisible = true;
  render();
}

function finishOnboarding() {
  onboardingVisible = false;
  localStorage.setItem(ONBOARDING_KEY, "1");
  render();
}

if (lastChart) {
  result = lastChart.result;
  chartDetails = lastChart.chartDetails;
  insightsText = lastChart.insightsText || "";
  chatHistory = lastChart.chatHistory || [];
  preloadCompatFromChart(result?.chart);
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

function preloadCompatFromChart(rawChart) {
  if (!rawChart) return;
  let chartObj = rawChart;
  if (typeof rawChart === "string") {
    try {
      chartObj = JSON.parse(rawChart);
    } catch {
      return;
    }
  }
  if (chartObj.birth_date) compatForm.self_date = chartObj.birth_date.split("-").reverse().join(".");
  if (chartObj.birth_time) compatForm.self_time = chartObj.birth_time.slice(0, 5);
  if (chartObj.location?.display_name) compatForm.self_place = chartObj.location.display_name;
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
      const item = { display_name: data.location.display_name };
      // Автоподстановка единственного результата без списка
      form.place = item.display_name;
      placeSuggestions = [];
      render();
      return;
    } else {
      placeSuggestions = [];
    }
  } catch {
    placeSuggestions = [];
  } finally {
    placeLoading = false;
    render();
  }
}, 700);

const doSelfPlaceSuggest = debounce(async (query) => {
  if (!query || query.length < 2) {
    selfPlaceSuggestions = [];
    selfPlaceLoading = false;
    render();
    return;
  }
  selfPlaceLoading = true;
  render();
  try {
    const res = await fetch(`/api/geo/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (data.ok) {
      const item = { display_name: data.location.display_name };
      compatForm.self_place = item.display_name;
      selfPlaceSuggestions = [];
      render();
      return;
    } else {
      selfPlaceSuggestions = [];
    }
  } catch {
    selfPlaceSuggestions = [];
  } finally {
    selfPlaceLoading = false;
    render();
  }
}, 700);

const doPartnerPlaceSuggest = debounce(async (query) => {
  if (!query || query.length < 2) {
    partnerPlaceSuggestions = [];
    partnerPlaceLoading = false;
    render();
    return;
  }
  partnerPlaceLoading = true;
  render();
  try {
    const res = await fetch(`/api/geo/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (data.ok) {
      const item = { display_name: data.location.display_name };
      compatForm.partner_place = item.display_name;
      partnerPlaceSuggestions = [];
      render();
      return;
    } else {
      partnerPlaceSuggestions = [];
    }
  } catch {
    partnerPlaceSuggestions = [];
  } finally {
    partnerPlaceLoading = false;
    render();
  }
}, 700);

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
  haptic();
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
    preloadCompatFromChart(data.chart);
  } catch (e) {
    error = e.message || "Ошибка запроса";
    debugEvents.push({ type: "error", msg: error, ts: Date.now() });
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
  haptic();
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
  haptic();
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
  haptic();
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
    preloadCompatFromChart(data.chart);
  } catch (e) {
    showToast(e.message || "Ошибка загрузки карты");
  } finally {
    loading = false;
    render();
  }
}

async function calcCompat() {
  compatError = "";
  compatLoading = true;
  compatResult = null;
  render();
  haptic();
  try {
    if (!compatForm.self_date || !/^\d{2}\.\d{2}\.\d{4}$/.test(compatForm.self_date)) {
      throw new Error("Укажите дату рождения (я)");
    }
    if (!compatForm.partner_date || !/^\d{2}\.\d{2}\.\d{4}$/.test(compatForm.partner_date)) {
      throw new Error("Укажите дату партнёра");
    }
    if (!compatForm.self_place) throw new Error("Укажите место рождения (я)");
    if (!compatForm.partner_place) throw new Error("Укажите место партнёра");
    const payload = {
      self_birth_date: compatForm.self_date,
      self_birth_time: compatForm.self_time || null,
      self_place: compatForm.self_place,
      partner_birth_date: compatForm.partner_date,
      partner_birth_time: compatForm.partner_time || null,
      partner_place: compatForm.partner_place,
      telegram_user_id: verifiedUser?.id,
    };
    const res = await fetch("/api/compatibility/calc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || "Ошибка совместимости");
    compatResult = {
      id: data.compatibility_id,
      score: data.score,
      key_aspects: data.key_aspects,
      top_aspects: data.top_aspects,
      overlays: data.overlays,
      wheel_url: data.wheel_url,
    };
  } catch (e) {
    compatError = e.message || "Ошибка запроса";
    debugEvents.push({ type: "compat_error", msg: compatError, ts: Date.now() });
    showToast(compatError);
  } finally {
    if (debugEvents.length > 20) debugEvents = debugEvents.slice(-20);
    compatLoading = false;
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

function buildInsightsCards(text) {
  if (!text) return [];
  const cleaned = text.replace(/\r/g, "").trim();
  if (!cleaned) return [];
  const numbered = cleaned.split(/\n?\s*\d+\)\s*/).filter((s) => s.trim().length > 0);
  const blocks =
    numbered.length > 1
      ? numbered
      : cleaned
          .split(/\n{2,}/)
          .map((s) => s.trim())
          .filter(Boolean);
  return blocks.map((block, idx) => {
    let body = block;
    let evidence = [];
    const evMatch = block.match(/основ[а-яё ]*на:?\s*(.+)/i);
    if (evMatch) {
      evidence = evMatch[1]
        .split(/[;•,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      body = block.replace(evMatch[0], "").trim();
    }
    return {
      title: `✨ Пункт ${idx + 1}`,
      body,
      evidence,
    };
  });
}

function renderInsightCards(text) {
  const cards = buildInsightsCards(text);
  if (!cards.length) return "<div class='muted-small'>Нет инсайтов</div>";
  return `
    <div class="insight-grid">
      ${cards
        .map(
          (c) => `
        <div class="insight-card">
          <div class="insight-title">${c.title}</div>
          <div class="insight-body">${c.body.replace(/\n/g, "<br/>")}</div>
          ${
            c.evidence && c.evidence.length
              ? `<div class="chips">${c.evidence.map((e) => `<span class="chip">Основано: ${e}</span>`).join("")}</div>`
              : ""
          }
        </div>`
        )
        .join("")}
    </div>
  `;
}

function renderTabs() {
  const primary = [
    { id: "highlights", label: "Основное" },
    { id: "chat", label: "Вопрос астрологу" },
    { id: "compat", label: "Совместимость" },
    { id: "insights", label: "Инсайты" },
  ];
  const pro = [
    { id: "planets", label: "Планеты" },
    { id: "houses", label: "Дома" },
    { id: "aspects", label: "Аспекты" },
    { id: "wheel", label: "Wheel" },
  ];
  return `
    <div class="tabs-group">
      <div class="tabs-title">Режим</div>
      <div class="tabs">
        ${primary
          .map(
            (t) => `<button class="tab ${currentTab === t.id ? "active" : ""}" data-tab="${t.id}">${t.label}</button>`
          )
          .join("")}
      </div>
    </div>
    <div class="tabs-group">
      <div class="tabs-title muted-small">Для профессионального астролога</div>
      <div class="tabs tabs-compact">
        ${pro
          .map(
            (t) => `<button class="tab ${currentTab === t.id ? "active" : ""}" data-tab="${t.id}">${t.label}</button>`
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderResult() {
  if (!result) return "";
  const wheelLink = result.wheel_url || "";
  const chart = chartDetails;
  if (loading) {
    return `
      <div class="card glass-card skeleton-card" style="margin-top:12px;">
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-line"></div>
        <div class="skeleton skeleton-line short"></div>
      </div>
    `;
  }
  return `
    <div class="card glass-card" style="margin-top:12px;">
      <div class="muted" style="margin-bottom:8px;">Результат</div>
      ${renderTabs()}
      <div class="list">
        ${renderTabContent(chart, wheelLink)}
      </div>
      <div class="actions" style="margin-top:10px; gap:10px;">
        ${currentTab === "insights" ? renderInsightsButton() : ""}
        <button class="btn ghost" id="share-btn" title="Скопировать результат">Скопировать</button>
      </div>
    </div>
  `;
}

function renderCompat() {
  const score = compatResult?.score;
  const keyAspects = compatResult?.key_aspects || [];
  const topAspects = compatResult?.top_aspects || [];
  const wheelLink = compatResult?.wheel_url;
  const overlays = compatResult?.overlays || {};
  if (compatLoading) {
    return `
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton skeleton-line"></div>
      <div class="skeleton skeleton-line short"></div>
    `;
  }
  const keyHtml = keyAspects.length
    ? keyAspects
        .map(
          (a, idx) =>
            `<div class="clickable" data-aspect="${idx}" data-aspect-type="key">💞 ${a.p1} — ${a.p2}: ${a.aspect} (орб ${Math.abs(a.orbit).toFixed(2)}°)</div>`
        )
        .join("")
    : "<div class='muted-small'>Нет данных</div>";
  const topHtml = topAspects.length
    ? topAspects
        .map(
          (a, idx) =>
            `<div class="clickable" data-aspect="${idx}" data-aspect-type="top">🔗 ${a.p1} — ${a.p2}: ${a.aspect} (орб ${Math.abs(a.orbit).toFixed(2)}°)</div>`
        )
        .join("")
    : "<div class='muted-small'>Нет данных</div>";
  return `
    <div class="section-title">Моя карта</div>
    <div class="field">
      <label for="self_date">Дата</label>
      <input class="input" id="self_date" type="text" inputmode="numeric" placeholder="ДД.ММ.ГГГГ" value="${compatForm.self_date}" />
    </div>
    <div class="field">
      <label for="self_time">Время</label>
      <input class="input" id="self_time" type="text" inputmode="numeric" placeholder="ЧЧ:ММ или пусто" value="${compatForm.self_time}" />
    </div>
    <div class="field">
      <label for="self_place">Место</label>
      <input class="input" id="self_place" type="text" placeholder="Город, страна" value="${compatForm.self_place}" />
      ${selfPlaceLoading ? '<div class="muted-small"><span class="spinner"></span> Поиск...</div>' : ""}
      ${
        selfPlaceSuggestions.length
          ? `<div class="suggestions">${selfPlaceSuggestions
              .map((s, idx) => `<div data-self-sidx="${idx}">${s.display_name}</div>`)
              .join("")}</div>`
          : ""
      }
    </div>
    <div class="section-title">Партнёр</div>
    <div class="field">
      <label for="partner_date">Дата</label>
      <input class="input" id="partner_date" type="text" inputmode="numeric" placeholder="ДД.ММ.ГГГГ" value="${compatForm.partner_date}" />
    </div>
    <div class="field">
      <label for="partner_time">Время</label>
      <input class="input" id="partner_time" type="text" inputmode="numeric" placeholder="ЧЧ:ММ или пусто" value="${compatForm.partner_time}" />
    </div>
    <div class="field">
      <label for="partner_place">Место</label>
      <input class="input" id="partner_place" type="text" placeholder="Город, страна" value="${compatForm.partner_place}" />
      ${partnerPlaceLoading ? '<div class="muted-small"><span class="spinner"></span> Поиск...</div>' : ""}
      ${
        partnerPlaceSuggestions.length
          ? `<div class="suggestions">${partnerPlaceSuggestions
              .map((s, idx) => `<div data-partner-sidx="${idx}">${s.display_name}</div>`)
              .join("")}</div>`
          : ""
      }
    </div>
    ${compatError ? `<div class="error">${compatError}</div>` : ""}
      <div class="actions" style="margin-top:10px;">
        <button class="btn" id="compat-calc" ${compatLoading ? "disabled" : ""}>${compatLoading ? "Считаю..." : "Совместимость"}</button>
        ${compatResult ? `<button class="btn ghost" id="share-compat">Поделиться</button>` : ""}
      </div>
    ${
      compatResult
        ? `
      <div class="section-title" style="margin-top:12px;">Score</div>
      <div class="pill">❤️ ${score?.value ?? "?"} — ${score?.description ?? "Оценка отношений"}</div>
      <div class="section-title">🔑 Ключевые аспекты</div>
      <div class="list">${keyHtml}</div>
      <div class="section-title">⭐ Топ аспектов</div>
      <div class="list">${topHtml}</div>
      <div class="section-title">🏠 Домовые наложения</div>
      <div class="list">
        ${
          overlays.first_in_second?.length
            ? overlays.first_in_second
                .map((o, idx) => `<div class="clickable" data-overlay="first_${idx}">🌟 Моя точка ${o.point} в его/ее доме ${prettyHouse(o.house)}</div>`)
                .join("")
            : "<div class='muted-small'>Нет данных</div>"
        }
        ${
          overlays.second_in_first?.length
            ? overlays.second_in_first
                .map((o, idx) => `<div class="clickable" data-overlay="second_${idx}">🌟 Его/ее точка ${o.point} в моём доме ${prettyHouse(o.house)}</div>`)
                .join("")
            : ""
        }
      </div>
      <div class="section-title">Wheel</div>
      ${wheelLink ? `<div style="margin-top:8px; border-radius:12px; overflow:hidden; border:1px solid #e2e8f0;"><object data="${wheelLink}" type="image/svg+xml" style="width:100%; min-height:320px;"></object></div>` : "<div class='muted-small'>Нет SVG</div>"}
    `
        : ""
    }
  `;
}

function renderTabContent(chart, wheelLink) {
  if (currentTab === "wheel") {
    return wheelLink
      ? `<div class="section-title">🌀 Wheel</div><div class="wheel-frame"><object data="${wheelLink}" type="image/svg+xml" style="width:100%; min-height:320px;"></object></div>`
      : "<div class='muted-small'>Нет SVG</div>";
  }
  if (currentTab === "compat") {
    return renderCompat();
  }
  if (currentTab === "insights") {
    if (insightsLoading)
      return `
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-line"></div>
        <div class="skeleton skeleton-line short"></div>
      `;
    const insightsSource = insightsText || result.llm_summary || result.summary || "";
    if (insightsSource) return renderInsightCards(insightsSource);
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
    const mainText = result.llm_summary || result.summary || "";
    const mainBlock = mainText ? renderInsightCards(mainText) : "<div class='muted-small'>Нет основного описания</div>";
    return `
      <div class="section-title">✨ Главное</div>
      ${mainBlock}
      <div class="section-title">🌞🌙 Asc / MC</div>
      <div class="pill-row">
        ${chart.highlights && chart.highlights.length ? chart.highlights.map((h) => `<span class="tag">✨ ${h}</span>`).join("") : "<div class='muted-small'>Нет данных</div>"}
      </div>
    `;
  }
  if (currentTab === "planets") {
    return chart.planets && chart.planets.length
      ? chart.planets
          .map(
            (p, idx) =>
              `<div class="clickable planet-item" data-planet="${idx}">🪐 ${p}</div>`
          )
          .join("")
      : "<div class='muted-small'>Нет данных</div>";
  }
  if (currentTab === "houses") {
    return chart.houses && chart.houses.length
      ? chart.houses.map((h) => `<div class="tag">🏠 Дом ${h.num}: ${h.sign} ${h.pos.toFixed(2)}°</div>`).join("")
      : "<div class='muted-small'>Нет данных</div>";
  }
  if (currentTab === "aspects") {
    return chart.aspects && chart.aspects.length
      ? chart.aspects
          .map(
            (a, idx) =>
              `<div class="clickable aspect-item" data-aspect-native="${idx}">🔗 ${a.text}</div>`
          )
          .join("")
      : "<div class='muted-small'>Нет аспектов</div>";
  }
  return "";
}

function renderDebugBlock() {
  if (isTelegram) return "";
  if (qs("debug") !== "1") return "";
  const diag = window.__debugInfo;
  const errors = debugEvents.slice(-10).reverse();
  return `
    <div class="card" style="margin-top:12px;">
      <div class="muted" style="margin-bottom:8px;">Debug validate initData (browser)</div>
      <textarea id="debug-initdata" style="width:100%; min-height:80px; border-radius:8px; padding:8px; border:1px solid #e2e8f0;"></textarea>
      <div class="actions" style="margin-top:10px;">
        <button class="btn" id="debug-validate">Validate</button>
      </div>
      <div class="muted" style="margin-top:10px;">Diagnostics</div>
      <div class="muted-small">
        ${diag ? `
          OpenAI: ${diag.openai_configured ? "yes" : "no"}<br/>
          WebApp URL set: ${diag.webapp_public_url_set ? "yes" : "no"}<br/>
          Dist available: ${diag.dist_available ? "yes" : "no"}<br/>
          Telegram token: ${diag.telegram_token_set ? "yes" : "no"}
        ` : "нет данных"}
      </div>
      <div class="muted" style="margin-top:10px;">Последние ошибки</div>
      <div class="muted-small">
        ${errors.length ? errors.map((e) => `<div>${new Date(e.ts).toLocaleTimeString()} — ${e.type}: ${e.msg}</div>`).join("") : "нет"}
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
          <input class="input" id="birth_date" type="text" inputmode="numeric" placeholder="ДД.ММ.ГГГГ" value="${form.birth_date}" />
        </div>
        <div class="row">
          <div class="field">
            <label for="birth_time">Время</label>
            <input class="input" id="birth_time" type="text" inputmode="numeric" placeholder="ЧЧ:ММ или пусто" value="${form.birth_time}" />
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
    ${modalVisible ? `
      <div class="modal-backdrop" id="modal-close"></div>
      <div class="modal-sheet glass-card">
        <div class="section-title">Детали</div>
        <div class="muted" style="margin-top:6px;">${modalContent}</div>
        <div class="actions" style="margin-top:12px;">
          <button class="btn" id="modal-close">Закрыть</button>
        </div>
      </div>
    ` : ""}
    ${onboardingVisible ? renderOnboarding() : ""}
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
  document.querySelectorAll("[data-self-sidx]")?.forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.selfSidx);
      if (!Number.isNaN(idx) && selfPlaceSuggestions[idx]) {
        compatForm.self_place = selfPlaceSuggestions[idx].display_name;
        selfPlaceSuggestions = [];
        render();
      }
    });
  });
  document.querySelectorAll("[data-partner-sidx]")?.forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.partnerSidx);
      if (!Number.isNaN(idx) && partnerPlaceSuggestions[idx]) {
        compatForm.partner_place = partnerPlaceSuggestions[idx].display_name;
        partnerPlaceSuggestions = [];
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
        haptic();
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
  document.getElementById("share-btn")?.addEventListener("click", copyShareText);

  document.getElementById("compat-calc")?.addEventListener("click", () => {
    compatForm.self_date = formatDateInput(document.getElementById("self_date").value);
    compatForm.self_time = formatTimeInput(document.getElementById("self_time").value);
    compatForm.self_place = document.getElementById("self_place").value.trim();
    compatForm.partner_date = formatDateInput(document.getElementById("partner_date").value);
    compatForm.partner_time = formatTimeInput(document.getElementById("partner_time").value);
    compatForm.partner_place = document.getElementById("partner_place").value.trim();
    calcCompat();
  });
  document.getElementById("self_place")?.addEventListener("input", (e) => {
    compatForm.self_place = e.target.value;
    doSelfPlaceSuggest(compatForm.self_place);
  });
  document.getElementById("partner_place")?.addEventListener("input", (e) => {
    compatForm.partner_place = e.target.value;
    doPartnerPlaceSuggest(compatForm.partner_place);
  });
  // Автоформат дат/времени в совместимости
  document.getElementById("self_date")?.addEventListener("input", (e) => {
    const formatted = formatDateInput(e.target.value);
    e.target.value = formatted;
    compatForm.self_date = formatted;
  });
  document.getElementById("self_time")?.addEventListener("input", (e) => {
    const formatted = formatTimeInput(e.target.value);
    e.target.value = formatted;
    compatForm.self_time = formatted;
  });
  document.getElementById("partner_date")?.addEventListener("input", (e) => {
    const formatted = formatDateInput(e.target.value);
    e.target.value = formatted;
    compatForm.partner_date = formatted;
  });
  document.getElementById("partner_time")?.addEventListener("input", (e) => {
    const formatted = formatTimeInput(e.target.value);
    e.target.value = formatted;
    compatForm.partner_time = formatted;
  });
  document.querySelectorAll("[data-aspect]")?.forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.aspect);
      const type = el.dataset.aspectType;
      const list = type === "key" ? compatResult?.key_aspects : compatResult?.top_aspects;
      if (!list || Number.isNaN(idx) || !list[idx]) return;
      const a = list[idx];
      modalContent = `${a.p1} — ${a.p2}: ${a.aspect} (орб ${Math.abs(a.orbit).toFixed(2)}°)`;
      modalVisible = true;
      haptic();
      render();
    });
  });
  document.getElementById("share-compat")?.addEventListener("click", shareCompatText);
  document.getElementById("modal-close")?.addEventListener("click", () => {
    modalVisible = false;
    render();
  });
  document.querySelectorAll(".aspect-item")?.forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.aspectNative);
      if (chartDetails?.aspects && !Number.isNaN(idx) && chartDetails.aspects[idx]) {
        showModal(chartDetails.aspects[idx].text);
      }
    });
  });
  document.querySelectorAll(".planet-item")?.forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.planet);
      if (chartDetails?.planets && !Number.isNaN(idx) && chartDetails.planets[idx]) {
        showModal(chartDetails.planets[idx]);
      }
    });
  });
  document.querySelectorAll("[data-overlay]")?.forEach((el) => {
    el.addEventListener("click", () => {
      const id = el.dataset.overlay;
      if (!compatResult?.overlays || !id) return;
      const [kind, idxStr] = id.split("_");
      const idx = Number(idxStr);
      const list = kind === "first" ? compatResult.overlays.first_in_second : compatResult.overlays.second_in_first;
      if (!list || Number.isNaN(idx) || !list[idx]) return;
      const item = list[idx];
      showModal(kind === "first" ? `Моя точка ${item.point} в его/ее доме ${prettyHouse(item.house)}` : `Его/ее точка ${item.point} в моём доме ${prettyHouse(item.house)}`);
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

// fetch debug info for diagnostics
if (qs("debug") === "1") {
  fetch("/api/debug/info")
    .then((r) => r.json())
    .then((d) => {
      if (d.ok) {
        window.__debugInfo = d.debug;
        render();
      }
    })
    .catch(() => {});
}
