// Simulated Alexa+ experience: voice-first, with a visible tool trace.
//
// Deliberate choices, because the real Alexa+ Web Simulator is not available to
// hackathon participants:
//   * voice is the primary input; typing is a fallback, not a peer
//   * speaking while the user talks is interrupted (barge-in) rather than queued
//   * a misheard request is recoverable in one tap, like a device prompt
//   * the answer is shown as a caption for the viewer, not as chat history

const dot = document.getElementById("dot");
const statusBox = document.getElementById("status");
const lead = document.getElementById("lead");
const orb = document.getElementById("orb");
const orbLabel = document.getElementById("orbLabel");
const heard = document.getElementById("heard");
const answerBox = document.getElementById("answer");
const latencyPill = document.getElementById("latency");
const retryButton = document.getElementById("retry");
const restartButton = document.getElementById("restart");
const typeToggle = document.getElementById("typeToggle");
const composer = document.getElementById("composer");
const input = document.getElementById("input");
const traceBox = document.getElementById("trace");
const toolsBox = document.getElementById("tools");
const diagToggle = document.getElementById("diagToggle");
const diagBody = document.getElementById("diagBody");

const SESSION_ID = "simulator";
const ORB_LABEL = {
  idle: "Tap to speak",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  error: "Tap to retry",
};

let phase = "idle";
let recognition = null;
let wantListening = false;
let lastRequest = "";
let ticker = null;

function setPhase(next, note) {
  phase = next;
  orb.className = "orb" + (next === "idle" ? "" : " " + next);
  orbLabel.textContent = ORB_LABEL[next] || ORB_LABEL.idle;
  if (note !== undefined) lead.textContent = note;
}

function setCaption(heardText, answerText) {
  heard.textContent = heardText || "";
  answerBox.textContent = answerText || "";
}

function showLatency(ms) {
  latencyPill.textContent = "answered in " + (ms / 1000).toFixed(1) + " s";
  latencyPill.classList.remove("hidden");
}

function startTicker() {
  const started = performance.now();
  stopTicker();
  ticker = window.setInterval(() => {
    lead.textContent = "Thinking… " + ((performance.now() - started) / 1000).toFixed(1) + " s";
  }, 100);
}

function stopTicker() {
  if (ticker) {
    window.clearInterval(ticker);
    ticker = null;
  }
}

function renderTrace(steps) {
  traceBox.innerHTML = "";
  if (!steps || !steps.length) {
    traceBox.innerHTML = '<p class="muted">No tool calls in this turn.</p>';
    return;
  }
  for (const step of steps) {
    const el = document.createElement("div");
    el.className = "step" + (step.needs_confirmation ? " confirm" : step.ok === false ? " error" : "");
    const args = Object.keys(step.arguments || {}).length
      ? '<div class="args">' + JSON.stringify(step.arguments) + "</div>"
      : "";
    const said = step.spoken ? '<div class="said">“' + step.spoken + '”</div>' : "";
    el.innerHTML = '<div class="name">' + step.tool + "</div>" + args + said;
    traceBox.appendChild(el);
  }
}

function speak(text) {
  if (!text || !("speechSynthesis" in window)) {
    setPhase("idle");
    return;
  }
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.03;
  utterance.pitch = 1.0;
  utterance.onend = () => {
    if (phase === "speaking") setPhase("idle", "Tap the orb to ask something else.");
  };
  setPhase("speaking", "Speaking the answer.");
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function stopSpeaking() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}

async function ask(text) {
  lastRequest = text;
  retryButton.classList.add("hidden");
  setCaption('You said: “' + text + '”', "");
  startTicker();
  setPhase("thinking");

  const started = performance.now();
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, session_id: SESSION_ID }),
    });
    const data = await response.json();
    stopTicker();
    showLatency(performance.now() - started);
    renderTrace(data.trace);

    if (data.error) {
      setPhase("error", "Something went wrong.");
      setCaption('You said: “' + text + '”', data.reply || data.error);
      retryButton.classList.remove("hidden");
      return;
    }
    setCaption('You said: “' + text + '”', data.reply || "(no answer)");
    speak(data.reply);
  } catch (error) {
    stopTicker();
    setPhase("error", "I could not reach the agent.");
    setCaption('You said: “' + text + '”', "The simulator could not reach the agent: " + error);
    retryButton.classList.remove("hidden");
  }
}

// ---------- voice input ----------

function buildRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return null;

  const instance = new Recognition();
  instance.lang = "en-US";
  instance.continuous = false;
  instance.interimResults = true;
  instance.maxAlternatives = 1;

  instance.onstart = () => {
    wantListening = true;
    setPhase("listening", "Listening — ask about invoices, customers, or cash flow.");
  };

  instance.onresult = (event) => {
    let interim = "";
    let finalText = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const chunk = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += chunk;
      else interim += chunk;
    }
    if (interim) lead.textContent = "Listening… “" + interim.trim() + "”";
    if (finalText.trim()) {
      wantListening = false;
      ask(finalText.trim());
    }
  };

  instance.onerror = (event) => {
    wantListening = false;
    if (event.error === "no-speech") {
      setPhase("error", "I didn't catch that. Tap the orb and try again.");
    } else if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      setPhase("idle", "Microphone blocked — allow access, or use “Type instead”.");
      showComposer();
    } else {
      setPhase("idle", "Voice input stopped. Tap the orb to try again.");
    }
  };

  instance.onend = () => {
    wantListening = false;
    if (phase === "listening") setPhase("idle", "Tap the orb and ask a question.");
  };

  return instance;
}

function startListening() {
  if (!recognition) return;
  stopSpeaking();           // barge-in: talking to the device interrupts it
  try {
    recognition.start();
  } catch (error) {
    // start() throws if it is already running; ignore.
  }
}

function stopListening() {
  if (recognition && wantListening) recognition.stop();
}

function onOrb() {
  if (phase === "speaking" || phase === "thinking") {
    stopSpeaking();
    stopTicker();
    setPhase("idle");
  }
  if (phase === "listening") {
    stopListening();
    return;
  }
  startListening();
}

// ---------- typing fallback ----------

function showComposer() {
  composer.classList.remove("hidden");
  typeToggle.classList.add("hidden");
  input.focus();
}

function hideComposer() {
  composer.classList.add("hidden");
  typeToggle.classList.remove("hidden");
}

// ---------- wiring ----------

orb.addEventListener("click", onOrb);

retryButton.addEventListener("click", () => {
  if (lastRequest) ask(lastRequest);
});

restartButton.addEventListener("click", async () => {
  stopSpeaking();
  stopTicker();
  await fetch("/api/reset?session_id=" + SESSION_ID, { method: "POST" });
  setCaption("", "");
  renderTrace([]);
  latencyPill.classList.add("hidden");
  retryButton.classList.add("hidden");
  setPhase("idle", "Conversation cleared. Tap the orb and ask a question.");
});

typeToggle.addEventListener("click", showComposer);

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  hideComposer();
  ask(text);
});

diagToggle.addEventListener("click", () => {
  const hidden = diagBody.classList.toggle("hidden");
  diagToggle.textContent = hidden ? "How it works" : "Hide";
});

document.addEventListener("keydown", (event) => {
  if (event.code !== "Space") return;
  if (document.activeElement === input) return;
  event.preventDefault();
  onOrb();
});

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    if (data.connected) {
      dot.className = "dot ok";
      statusBox.textContent = "MCP connected · " + data.tools.length + " tools";
      toolsBox.innerHTML = data.tools.map((tool) => "<li>" + tool + "</li>").join("");
    } else {
      dot.className = "dot bad";
      statusBox.textContent = "MCP server unreachable";
      toolsBox.innerHTML = "<li>" + data.mcp_url + "</li>";
    }
  } catch (error) {
    dot.className = "dot bad";
    statusBox.textContent = "simulator offline";
  }
}

recognition = buildRecognition();
if (!recognition) {
  lead.textContent = "This browser has no speech recognition — type the request instead.";
  showComposer();
}
setPhase("idle");
renderTrace([]);
checkHealth();
window.setInterval(checkHealth, 15000);
