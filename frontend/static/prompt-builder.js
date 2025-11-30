const API_BASE = "http://127.0.0.1:8000";

const surveyForm = document.getElementById("promptSurvey");
const promptPreview = document.getElementById("promptPreview");
const generatePromptBtn = document.getElementById("generatePromptBtn");
const sendPromptBtn = document.getElementById("sendPromptBtn");
const resetBtn = document.getElementById("resetBtn");
const apiStatus = document.getElementById("apiStatus");
const runStatus = document.getElementById("runStatus");
const generationResult = document.getElementById("generationResult");
const runIdEl = document.getElementById("runId");
const runMessageEl = document.getElementById("runMessage");
const runFilesEl = document.getElementById("runFiles");
const htmlOnlyToggle = document.getElementById("htmlOnlyToggle");
const debugToggle = document.getElementById("debugToggle");
const charCount = document.getElementById("charCount");
const modeBadge = document.getElementById("modeBadge");
const debugBadge = document.getElementById("debugBadge");

let isSubmitting = false;

document.addEventListener("DOMContentLoaded", () => {
  attachListeners();
  updatePrompt();
  checkHealth();
});

function attachListeners() {
  const formControls = surveyForm.querySelectorAll("input, textarea");
  formControls.forEach((field) => {
    field.addEventListener("input", () => updatePrompt());
  });

  generatePromptBtn.addEventListener("click", () => {
    updatePrompt();
    runStatus.textContent = "Prompt refreshed from survey responses.";
  });

  resetBtn.addEventListener("click", () => {
    surveyForm.reset();
    updatePrompt();
    runStatus.textContent = "Survey cleared. Start fresh to shape a new prompt.";
  });

  sendPromptBtn.addEventListener("click", sendToModel);
  htmlOnlyToggle.addEventListener("change", updateBadges);
  debugToggle.addEventListener("change", updateBadges);
  promptPreview.addEventListener("input", () => {
    charCount.textContent = `${promptPreview.value.length} chars`;
    runStatus.textContent = "Prompt edited manually.";
  });
}

async function checkHealth() {
  try {
    const resp = await fetch(`${API_BASE}/health`);
    if (!resp.ok) throw new Error();
    setApiStatus("connected", "API connected");
  } catch (err) {
    setApiStatus("error", "API unavailable");
    runStatus.textContent = "Cannot reach the API. Start the backend to generate.";
    sendPromptBtn.disabled = true;
  }
}

function setApiStatus(state, label) {
  apiStatus.textContent = label;
  apiStatus.classList.remove("ok", "warn", "error");
  apiStatus.classList.add(state === "connected" ? "ok" : state);
}

function collectSurveyData() {
  const val = (id) => (document.getElementById(id)?.value || "").trim();
  return {
    purpose: val("sitePurpose"),
    theme: val("themeStyle"),
    colors: val("colorPalette"),
    typography: val("typography"),
    hero: val("heroText"),
    menu: val("menuItems"),
    about: val("aboutText"),
    contact: val("contactInfo"),
    extras: val("extraSections"),
    constraints: val("constraints"),
  };
}

function formatList(raw, fallback) {
  const tokens = raw
    .split(/[\n,]/)
    .map((t) => t.trim())
    .filter(Boolean);
  if (!tokens.length) return fallback;
  if (tokens.length === 1) return tokens[0];
  if (tokens.length === 2) return `${tokens[0]} and ${tokens[1]}`;
  const last = tokens.pop();
  return `${tokens.join(", ")}, and ${last}`;
}

function buildPrompt(data) {
  const filled = (value, fallback) => value || fallback;
  const prompt = `f"""
You are the Locable builder agent. Use Bootstrap 5 and the template retrieval context to generate a complete website from this survey. Blend the provided details with strong defaults and keep responses deterministic.

Project purpose: ${filled(data.purpose, "Infer a concise purpose from context and keep the build focused.")}
Theme and tone: ${filled(data.theme, "Modern, conversion-focused, mobile-first layout with confident visuals.")}
Color palette: ${filled(data.colors, "Pick a cohesive palette with a strong accent and readable contrast.")}
Typography preferences: ${filled(data.typography, "Readable modern sans-serif headings with complementary body text.")}

Content plan:
- Hero focus and CTA: ${filled(data.hero, "Punchy headline with supporting value props and a primary CTA.")}
- Navigation / menu items: ${formatList(data.menu, "Home, About, Services, Gallery, Blog, Contact")}
- About / story: ${filled(data.about, "Explain the brand story, credibility, and differentiators.")}
- Contact & CTA details: ${filled(data.contact, "Include contact form plus direct email/phone and hours/location if relevant.")}
- Extra sections or must-have features: ${filled(data.extras, "Testimonials, highlights/feature grid, FAQ, and a rich footer.")}

Constraints or must-avoid: ${filled(data.constraints, "Keep performance-friendly, accessible, and avoid heavy video or animation unless requested.")}

Use these inputs to write the site files through your tools and keep the tone polished and natural."""`;
  return prompt.trim();
}

function updatePrompt() {
  const prompt = buildPrompt(collectSurveyData());
  promptPreview.value = prompt;
  charCount.textContent = `${prompt.length} chars`;
  updateBadges();
}

function updateBadges() {
  const modeText = htmlOnlyToggle.checked ? "Mode: html-only template" : "Mode: full build";
  const debugText = debugToggle.checked ? "Debug: on" : "Debug: off";
  modeBadge.textContent = modeText;
  debugBadge.textContent = debugText;
}

async function sendToModel() {
  if (isSubmitting) return;
  const prompt = promptPreview.value.trim();
  if (!prompt) {
    runStatus.textContent = "Fill out the survey to generate a prompt before sending.";
    return;
  }

  isSubmitting = true;
  toggleButtons(true);
  runStatus.textContent = "Sending prompt to model...";

  try {
    const resp = await fetch(`${API_BASE}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        debug: !!debugToggle.checked,
        mode: htmlOnlyToggle.checked ? "html-only" : "full",
      }),
    });

    const payload = await resp.json();
    if (!resp.ok) {
      throw new Error(payload.detail || "Generation failed");
    }

    runIdEl.textContent = payload.run_id || "n/a";
    runMessageEl.textContent = payload.message || "Generation completed.";
    renderFiles(payload.files || []);
    generationResult.hidden = false;
    runStatus.textContent = `Model responded with ${payload.files.length} file(s).`;
  } catch (err) {
    generationResult.hidden = true;
    runStatus.textContent = `Error: ${err.message}`;
  } finally {
    isSubmitting = false;
    toggleButtons(false);
  }
}

function renderFiles(files) {
  if (!files.length) {
    runFilesEl.textContent = "No files returned yet.";
    return;
  }
  const list = files.map((f) => `- ${f}`).join("\n");
  runFilesEl.textContent = list;
}

function toggleButtons(disabled) {
  sendPromptBtn.disabled = disabled;
  generatePromptBtn.disabled = disabled;
  resetBtn.disabled = disabled;
}
