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
        <div class="actions">
          <button class="btn" id="continue-btn">Продолжить</button>
        </div>
      </div>
      ${renderDebugBlock()}
    </div>
    <div class="toast"></div>
  `;

  document.getElementById("continue-btn")?.addEventListener("click", () => {
    showToast("Скоро: ввод данных рождения");
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
