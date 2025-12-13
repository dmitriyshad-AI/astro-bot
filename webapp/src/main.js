const tg = window.Telegram?.WebApp;
if (tg) tg.ready();

const app = document.getElementById("app");

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
    showToast(err.message || "Auth error");
  }
}

async function submitForm() {
  error = "";
  loading = true;
  result = null;
  chartDetails = null;
  render();
  try {
    if (!form.birth_date || !form.place) {
      throw new Error("Заполните дату и место.");
    }
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
  } catch (e) {
    error = e.message || "Ошибка запроса";
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

  return {
    highlights,
    houses,
    aspects: majorAspects,
  };
}

function renderResult() {
  if (!result) return "";
  const wheelLink = result.wheel_url || "";
  const chart = chartDetails;
  return `
    <div class="card" style="margin-top:12px;">
      <div class="muted" style="margin-bottom:8px;">Результат</div>
      <div class="list">
        <div><strong>Summary:</strong> ${result.summary ? result.summary.split("\\n")[0] : "—"}</div>
        <div><strong>Wheel:</strong> <a class="link" href="${wheelLink}" target="_blank">Скачать SVG</a></div>
      </div>
      ${chart ? renderChartSections(chart) : ""}
    </div>
  `;
}

function renderChartSections(chart) {
  return `
    <div class="section-title">Солнце / Луна / Asc / MC</div>
    <div class="pill-row">
      ${chart.highlights && chart.highlights.length ? chart.highlights.map((h) => `<span class="tag">${h}</span>`).join("") : "<div class='muted-small'>Нет данных</div>"}
    </div>
    <div class="section-title">Дома (куспиды)</div>
    <div class="grid">
      ${chart.houses && chart.houses.length ? chart.houses.map((h) => `<div class="tag">Дом ${h.num}: ${h.sign} ${h.pos.toFixed(2)}°</div>`).join("") : "<div class='muted-small'>Нет данных</div>"}
    </div>
    <div class="section-title">Основные аспекты</div>
    <div class="list">
      ${
        chart.aspects && chart.aspects.length
          ? chart.aspects.map((a) => `<div>${a.text}</div>`).join("")
          : "<div class='muted-small'>Нет аспектов</div>"
      }
    </div>
  `;
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
            <input class="input" id="birth_time" type="text" placeholder="ЧЧ:ММ или не знаю" value="${form.birth_time}" />
          </div>
          <div class="field">
            <label>&nbsp;</label>
            <span class="muted-small">Можно оставить пустым</span>
          </div>
        </div>
        <div class="field">
          <label for="place">Место рождения</label>
          <input class="input" id="place" type="text" placeholder="Город, страна" value="${form.place}" />
        </div>
        ${error ? `<div class="error">${error}</div>` : ""}
        <div class="actions">
          <button class="btn" id="continue-btn" ${loading ? "disabled" : ""}>${loading ? "Считаю..." : "Рассчитать"}</button>
        </div>
      </div>
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
}

render();

if (isTelegram && tg?.initData) {
  fetchWhoAmI(tg.initData);
} else if (qs("debug") === "1") {
  showToast("Debug mode: можно вставить initData");
}
