// Simulated Alexa+ front end: voice in, voice out, and a visible tool trace.

const transcript = document.getElementById("transcript");
const traceBox = document.getElementById("trace");
const toolsBox = document.getElementById("tools");
const statusBox = document.getElementById("status");
const mic = document.getElementById("mic");
const hint = document.getElementById("hint");
const input = document.getElementById("input");
const composer = document.getElementById("composer");

const SESSION_ID = "web";
let recognition = null;
let listening = false;

function bubble(who, text) {
  const el = document.createElement("div");
  el.className = `bubble ${who}`;
  el.innerHTML = `<div class="who">${who === "user" ? "You" : "Agent"}</div>`;
  const body = document.createElement("div");
  body.textContent = text;
  el.appendChild(body);
  transcript.appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
  return el;
}

function renderTrace(steps) {
  traceBox.innerHTML = "";
  for (const step of steps) {
    const el = document.createElement("div");
    el.className = "step" + (step.needs_confirmation ? " confirm" : step.ok === false ? " error" : "");
    const args = Object.keys(step.arguments || {}).length
      ? `<div class="args">${JSON.stringify(step.arguments)}</div>` : "";
    const said = step.spoken ? `<div class="said">“${step.spoken}”</div>` : "";
    el.innerHTML = `<div class="name">${step.tool}</div>${args}${said}`;
    traceBox.appendChild(el);
  }
  if (!steps.length) {
    traceBox.innerHTML = `<p class="muted">No tool calls yet.</p>`;
  }
}

function speak(text) {
  if (!text || !("speechSynthesis" in window)) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = 1.02;
  utter.pitch = 1.0;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}

async function ask(text) {
  if (!text.trim()) return;
  bubble("user", text);
  input.value = "";
  hint.textContent = "Thinking…";

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, session_id: SESSION_ID }),
    });
    const data = await res.json();
    bubble("agent", data.reply || "(no answer)");
    renderTrace(data.trace || []);
    speak(data.reply);
  } catch (err) {
    bubble("agent", `Request failed: ${err}`);
  } finally {
    hint.textContent = "Press the orb and ask a question, or type below.";
  }
}

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (data.connected) {
      statusBox.textContent = `MCP connected · ${data.tools.length} tools`;
      statusBox.className = "status ok";
      toolsBox.innerHTML = data.tools.map((t) => `<li>${t}</li>`).join("");
    } else {
      statusBox.textContent = "MCP server unreachable";
      statusBox.className = "status bad";
      toolsBox.innerHTML = `<li>${data.mcp_url}</li>`;
    }
  } catch {
    statusBox.textContent = "simulator offline";
    statusBox.className = "status bad";
  }
}

function setupSpeech() {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) {
    hint.textContent = "Speech recognition unavailable in this browser — type below instead.";
    return;
  }
  recognition = new Ctor();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onresult = (event) => {
    const text = event.results[0][0].transcript;
    hint.textContent = `Heard: “${text}”`;
    ask(text);
  };
  recognition.onend = () => {
    listening = false;
    mic.classList.remove("listening");
  };
  recognition.onerror = () => {
    listening = false;
    mic.classList.remove("listening");
    hint.textContent = "Microphone unavailable — type below instead.";
  };
}

mic.addEventListener("click", () => {
  if (!recognition) return;
  if (listening) {
    recognition.stop();
    return;
  }
  window.speechSynthesis?.cancel();
  listening = true;
  mic.classList.add("listening");
  hint.textContent = "Listening…";
  recognition.start();
});

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(input.value);
});

document.getElementById("reset").addEventListener("click", async () => {
  await fetch(`/api/reset?session_id=${SESSION_ID}`, { method: "POST" });
  transcript.innerHTML = "";
  renderTrace([]);
  hint.textContent = "Conversation cleared.";
});

setupSpeech();
checkHealth();
setInterval(checkHealth, 15000);
