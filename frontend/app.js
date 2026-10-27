const API = window.API_BASE.replace(/\/$/, "");
const $ = (id) => document.getElementById(id);
let mode = "login";
let chart = null;
let timer = null;

// ---------- API helper ----------
async function api(path, opts = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(API + path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
    },
  });
  if (res.status === 401 && token) { logout(); throw new Error("세션이 만료되었습니다"); }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((e) => e.msg).join(", ") : "요청 실패 (" + res.status + ")");
  }
  return data;
}

// ---------- 로그인 / 회원가입 ----------
function setMode(m) {
  mode = m;
  $("tab-login").classList.toggle("active", m === "login");
  $("tab-signup").classList.toggle("active", m === "signup");
  $("auth-submit").textContent = m === "login" ? "로그인" : "회원가입";
  $("auth-msg").textContent = "";
}
$("tab-login").onclick = () => setMode("login");
$("tab-signup").onclick = () => setMode("signup");

$("auth-form").onsubmit = async (e) => {
  e.preventDefault();
  const btn = $("auth-submit");
  btn.disabled = true;
  $("auth-msg").className = "msg";
  $("auth-msg").textContent = "처리 중... (무료 서버는 첫 요청에 30초 정도 걸릴 수 있음)";
  try {
    const data = await api("/api/auth/" + mode, {
      method: "POST",
      body: JSON.stringify({ username: $("username").value.trim(), password: $("password").value }),
    });
    localStorage.setItem("token", data.token);
    localStorage.setItem("username", data.username);
    showDashboard();
  } catch (err) {
    $("auth-msg").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
};

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("username");
  clearInterval(timer);
  $("dash-view").classList.add("hidden");
  $("auth-view").classList.remove("hidden");
}
$("logout").onclick = logout;

// ---------- 대시보드 ----------
const deviceId = () => $("device-select").value || "xiao-s3-01";

async function showDashboard() {
  $("auth-view").classList.add("hidden");
  $("dash-view").classList.remove("hidden");
  $("who").textContent = localStorage.getItem("username") + " 님";
  try {
    const devices = await api("/api/devices");
    const sel = $("device-select");
    sel.innerHTML = devices.map((d) => `<option>${d.device_id}</option>`).join("");
    sel.onchange = refresh;
  } catch (err) { $("dash-msg").textContent = err.message; }
  refresh();
  clearInterval(timer);
  timer = setInterval(refresh, 3000);
}

function timeAgo(iso) {
  if (!iso) return null;
  return Math.round((Date.now() - new Date(iso).getTime()) / 1000);
}

async function refresh() {
  try {
    const id = encodeURIComponent(deviceId());
    const [led, hist] = await Promise.all([
      api("/api/led?device_id=" + id),
      api("/api/sensor/history?limit=50&device_id=" + id),
    ]);
    const last = hist[hist.length - 1];
    $("v-temp").textContent = last?.temperature != null ? last.temperature.toFixed(1) + " °C" : "--";
    $("v-analog").textContent = last?.analog ?? "--";
    $("v-rssi").textContent = last?.rssi != null ? last.rssi + " dBm" : "--";

    const ago = timeAgo(led.last_seen);
    const online = ago != null && ago < 15;
    $("v-online").textContent = online ? "🟢 온라인" : "⚪ 오프라인";
    $("v-seen").textContent = ago != null ? `마지막 수신 ${ago}초 전` : "수신 기록 없음";

    $("led-dot").classList.toggle("on", led.state);
    $("led-text").textContent = led.state ? "ON" : "OFF";

    drawChart(hist);
    $("dash-msg").textContent = "";
  } catch (err) {
    $("dash-msg").textContent = err.message;
  }
}

async function setLed(state) {
  try {
    await api("/api/led", { method: "POST", body: JSON.stringify({ device_id: deviceId(), state }) });
    refresh();
  } catch (err) { $("dash-msg").textContent = err.message; }
}
$("led-on").onclick = () => setLed(true);
$("led-off").onclick = () => setLed(false);

function drawChart(hist) {
  const labels = hist.map((r) => new Date(r.created_at).toLocaleTimeString());
  const temp = hist.map((r) => r.temperature);
  const analog = hist.map((r) => r.analog);
  if (!chart) {
    chart = new Chart($("chart"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "온도 (°C)", data: temp, borderColor: "#2f6fed", yAxisID: "y", tension: 0.3, pointRadius: 0 },
          { label: "아날로그", data: analog, borderColor: "#f59e0b", yAxisID: "y1", tension: 0.3, pointRadius: 0 },
        ],
      },
      options: {
        animation: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          y: { position: "left", title: { display: true, text: "°C" } },
          y1: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "ADC" } },
        },
      },
    });
  } else {
    chart.data.labels = labels;
    chart.data.datasets[0].data = temp;
    chart.data.datasets[1].data = analog;
    chart.update();
  }
}

if (localStorage.getItem("token")) showDashboard();
