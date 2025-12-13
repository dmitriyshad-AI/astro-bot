const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
}

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

const isTelegram = Boolean(tg);
const userName = tg?.initDataUnsafe?.user?.first_name
  ? `${tg.initDataUnsafe.user.first_name}${tg.initDataUnsafe.user.last_name ? " " + tg.initDataUnsafe.user.last_name : ""}`
  : null;

const theme = tg?.themeParams || {};
const root = document.documentElement;
if (theme.bg_color) {
  root.style.setProperty("--text", theme.text_color || "#0f172a");
  root.style.setProperty("--muted", theme.hint_color || "#475569");
}

app.innerHTML = `
  <div class="page">
    <div class="hero">
      <h1>AstroGlass</h1>
      <p>Лёгкая астрология в мини‑приложении Telegram.</p>
    </div>
    <div class="card">
      <div class="status-row">
        <div>
          <div class="pill">${isTelegram ? "Telegram WebApp" : "Браузер"}</div>
          <div class="muted">${userName ? `Привет, ${userName}` : "Гость"}</div>
        </div>
        <div class="muted">Status</div>
      </div>
      <div class="actions">
        <button class="btn" id="continue-btn">Продолжить</button>
      </div>
    </div>
  </div>
  <div class="toast"></div>
`;

document.getElementById("continue-btn")?.addEventListener("click", () => {
  showToast("Скоро: ввод данных рождения");
});
