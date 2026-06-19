const nameForm = document.getElementById("name-search");
const symptomPanel = document.getElementById("symptom-panel");
const symptomForm = document.getElementById("symptom-search"); // null when logged out
const modeName = document.getElementById("mode-name");
const modeSymptom = document.getElementById("mode-symptom");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");

const FIELDS = [
  ["indications", "Uses"],
  ["dosage", "Dosage"],
  ["warnings", "Warnings"],
  ["adverse_reactions", "Side effects"],
];

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function setMode(mode) {
  const isName = mode === "name";
  nameForm.hidden = !isName;
  symptomPanel.hidden = isName;
  modeName.classList.toggle("active", isName);
  modeSymptom.classList.toggle("active", !isName);
  statusEl.textContent = "";
  resultsEl.innerHTML = "";
}

modeName.addEventListener("click", () => setMode("name"));
modeSymptom.addEventListener("click", () => setMode("symptom"));

// Render a single drug's label as a card. `data` has heading/rxcui/label fields.
function labelCard(heading, rxcui, label, fallback) {
  if (!label) {
    return `<article class="result-card"><h2>${escapeHtml(heading)}</h2><p>${escapeHtml(fallback)}</p></article>`;
  }
  const rxcuiTag = rxcui ? ` <small>(RxCUI ${escapeHtml(rxcui)})</small>` : "";
  const sections = FIELDS.filter(([key]) => label[key])
    .map(
      ([key, title]) =>
        `<section class="label-field"><h3>${title}</h3><p>${escapeHtml(label[key])}</p></section>`
    )
    .join("");
  return `<article class="result-card"><h2>${escapeHtml(heading)}${rxcuiTag}</h2>${sections}</article>`;
}

function adverseEventsSection(events) {
  if (!events || events.length === 0) return "";
  const items = events
    .map(
      (e) =>
        `<li>${escapeHtml(e.term)}<span class="count">${e.count.toLocaleString()}</span></li>`
    )
    .join("");
  return `<section class="adverse-events">
      <h3>Most-reported adverse events</h3>
      <p class="caveat">Raw counts from FDA adverse-event reports — not incidence rates, and not adjusted for how widely the drug is used.</p>
      <ol>${items}</ol>
    </section>`;
}

function renderNameResult(data) {
  const card = labelCard(
    data.matched_name || data.query,
    data.rxcui,
    data.label,
    `No drug label found for "${data.matched_name || data.query}". Try a different name or spelling.`
  );
  return `${card}${adverseEventsSection(data.adverse_events)}<p class="disclaimer">${escapeHtml(data.disclaimer)}</p>`;
}

function renderSymptomResult(data) {
  const banner = `<div class="banner">${escapeHtml(data.disclaimer)}</div>`;

  if (data.emergency) {
    return `<div class="emergency">${escapeHtml(data.message)}</div>${banner}`;
  }
  if (!data.candidates || data.candidates.length === 0) {
    return `${banner}<p>No suggestions found. Please consult a clinician.</p>`;
  }
  const cards = data.candidates
    .map((c) =>
      labelCard(
        c.matched_name || c.name,
        c.rxcui,
        c.label,
        `Suggested: ${c.name}. No label details available.`
      )
    )
    .join("");
  return `${banner}${cards}`;
}

function renderError(message) {
  return `<div class="error"><strong>Couldn’t complete the search.</strong><br>${escapeHtml(message)}</div>`;
}

async function runSearch(endpoint, body, render, button) {
  statusEl.textContent = "Searching…";
  resultsEl.innerHTML = "";
  if (button) button.disabled = true;
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (response.status === 401) {
      resultsEl.innerHTML = `<div class="error"><strong>Please log in.</strong><br>Symptom search requires an account. <a href="/login">Log in</a> or <a href="/register">register</a>.</div>`;
      return;
    }
    if (!response.ok) {
      const detail =
        response.status >= 500
          ? "The server had a problem. Please try again in a moment."
          : `Request rejected (HTTP ${response.status}).`;
      resultsEl.innerHTML = renderError(detail);
      return;
    }
    const data = await response.json();
    resultsEl.innerHTML = render(data);
  } catch (err) {
    resultsEl.innerHTML = renderError(
      "Could not reach the server. Check your connection and try again."
    );
  } finally {
    statusEl.textContent = "";
    if (button) button.disabled = false;
  }
}

nameForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = document.getElementById("query").value.trim();
  if (!query) return;
  runSearch("/search/name", { query }, renderNameResult, nameForm.querySelector("button"));
});

if (symptomForm) {
  symptomForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const symptoms = document.getElementById("symptoms").value.trim();
    if (!symptoms) return;
    runSearch(
      "/search/symptom",
      { symptoms },
      renderSymptomResult,
      symptomForm.querySelector("button")
    );
  });
}
