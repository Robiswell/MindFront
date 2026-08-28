"use strict";

const state = { csrfToken: "", mode: "preflight" };

const modes = {
  preflight: {
    label: "Paste your draft or describe the conversation",
    button: "Help me prepare",
  },
  interpret: {
    label: "Paste the message or describe what happened",
    button: "Help me understand",
  },
  debrief: {
    label: "Paste your notes or tell Mindfront what happened",
    button: "Help me debrief",
  },
  career_review: {
    label: "Describe the work, result, or signal you want to assess",
    button: "Review my evidence",
  },
};

document.addEventListener("DOMContentLoaded", async () => {
  wireTabs();
  wireModes();
  wireForms();
  applyMode("preflight");
  await loadBootstrap();
});

function wireTabs() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-tab]").forEach((item) => {
        item.classList.toggle("is-active", item === button);
      });
      document.querySelectorAll("[data-panel]").forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.panel === button.dataset.tab);
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

function wireModes() {
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => applyMode(button.dataset.mode));
  });
}

function applyMode(mode) {
  state.mode = mode;
  document.querySelector("#assist-mode").value = mode;
  document.querySelector("#assist-label").textContent = modes[mode].label;
  document.querySelector("#assist-submit span").textContent = modes[mode].button;
  document.querySelector("#career-options").hidden = mode !== "career_review";
  document.querySelectorAll("[data-mode]").forEach((button) => {
    const selected = button.dataset.mode === mode;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-checked", selected ? "true" : "false");
  });
}

async function loadBootstrap() {
  const status = document.querySelector("#local-status");
  try {
    const response = await fetch("/api/bootstrap", { cache: "no-store" });
    if (!response.ok) throw new Error("The local service is unavailable.");
    const payload = await response.json();
    state.csrfToken = payload.csrfToken;
    if (!payload.profileAvailable) {
      status.classList.add("is-warning");
      status.querySelector("span:last-child").textContent = "Profile setup needed";
      showToast("Communication help needs the encrypted self-profile. Document review is ready.");
    }
  } catch (error) {
    status.classList.add("is-warning");
    status.querySelector("span:last-child").textContent = "Local service unavailable";
    showToast(error.message);
  }
}

function wireForms() {
  document.querySelector("#assist-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToObject(event.currentTarget);
    payload.mode = state.mode;
    await submit("/api/assist", payload, "#assist-submit", "#assist-result", renderAssist);
  });

  document.querySelector("#audit-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToObject(event.currentTarget);
    payload.containsPersonalData = document.querySelector("#audit-personal").checked;
    payload.containsCustomerConfidentialData =
      document.querySelector("#audit-confidential").checked;
    await submit("/api/artifact", payload, "#audit-submit", "#audit-result", renderAudit);
  });
}

function formToObject(form) {
  const payload = {};
  new FormData(form).forEach((value, key) => {
    payload[key] = typeof value === "string" ? value.trim() : value;
  });
  return payload;
}

async function submit(path, payload, buttonSelector, panelSelector, renderer) {
  const button = document.querySelector(buttonSelector);
  const panel = document.querySelector(panelSelector);
  const label = button.querySelector("span").textContent;
  if (!state.csrfToken) {
    renderError(panel, [{ message: "Refresh the page so the private local session can start." }]);
    return;
  }

  button.disabled = true;
  button.querySelector("span").textContent =
    path === "/api/artifact" ? "Reviewing..." : "Thinking...";
  panel.hidden = false;
  panel.classList.remove("is-error");
  panel.innerHTML = resultHeader("Mindfront is working", "Processing on this computer", "Local");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const response = await fetch(path, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-Mindfront-Token": state.csrfToken,
      },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok || body.status !== "ok") {
      renderError(panel, body.errors || [{ message: body.message || "Mindfront paused safely." }]);
      return;
    }
    renderer(panel, body.result);
  } catch (error) {
    renderError(panel, [{ message: error.message || "The local request did not finish." }]);
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = label;
  }
}

function renderAssist(panel, result) {
  const assistance = result.assistance || {};
  const values = flattenHelpfulValues(assistance);
  const bottomLine =
    pickByKey(assistance, ["shortVersion", "suggestedWording", "recommendedWording", "exactAsk",
      "recommendation", "bottomLine", "interpretation", "summary"]) ||
    stringValue(result.clarifyingQuestion) ||
    values[0] ||
    "Mindfront completed the review. Open more details below.";
  const nextAction =
    pickByKey(assistance, ["nextAction", "recommendedNextAction", "followUp",
      "clarifyingQuestion", "interruptionSafeSentence", "checkpoint"]) ||
    stringValue(result.clarifyingQuestion) ||
    values.find((value) => value !== bottomLine) ||
    "Review the guidance, adjust it to your voice, and choose the next safe action.";

  const facts = statements(result.explicitFacts)
    .concat(statements(result.userProvidedUnverifiedClaims));
  const interpretations = statements(result.boundedInferences);
  const unknowns = asArray(result.unknowns).map(stringValue).filter(Boolean);
  const reviewGates = asArray(result.gates)
    .filter((gate) => gate.status === "review")
    .map((gate) => gate.explanation || gate.recommendedAdjustment || gate.label)
    .filter(Boolean);

  panel.classList.remove("is-error");
  panel.innerHTML = `
    ${resultHeader("Here's the clearest read", humanize(result.mode), "Review before using")}
    <div class="answer">
      <h3>Bottom line</h3>
      ${renderValue(bottomLine)}
    </div>
    <div class="next">
      <h3>What to do next</h3>
      ${renderValue(nextAction)}
    </div>
    <div class="details-grid">
      ${compactCard("What we know", facts, "Only the context you supplied is treated as known.")}
      ${compactCard("What might be true", interpretations, "No extra interpretation was needed.")}
      ${compactCard("Things still unclear", unknowns, "No additional unknowns were identified.")}
      ${compactCard("Things to watch", reviewGates, "No special language or authority warnings were raised.")}
    </div>
    ${rawDetails(result)}
  `;
}

function renderAudit(panel, result) {
  const report = result.report || {};
  const bottomLine =
    pickByKey(report, ["executiveSummary", "summary", "overallAssessment", "recommendation"]) ||
    "The review completed. Open more details for the complete local report.";
  const nextAction =
    pickByKey(report, ["recommendedNextAction", "nextAction", "recommendations", "priorityActions"]) ||
    "Use the report to revise the material, then have a real reader confirm that it works in context.";

  panel.classList.remove("is-error");
  panel.innerHTML = `
    ${resultHeader("Review complete", "Heuristic and synthetic analysis", "Completed")}
    <div class="answer">
      <h3>Bottom line</h3>
      ${renderValue(bottomLine)}
    </div>
    <div class="next">
      <h3>Best next step</h3>
      ${renderValue(nextAction)}
    </div>
    <details>
      <summary>Report location and full result</summary>
      <p><code>${escapeHtml(result.reportPath || "")}</code></p>
      <pre>${escapeHtml(JSON.stringify(result, null, 2))}</pre>
    </details>
  `;
}

function resultHeader(title, subtitle, stateLabel) {
  return `
    <div class="result-top">
      <div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(subtitle)}</p></div>
      <span class="result-state">${escapeHtml(stateLabel)}</span>
    </div>
  `;
}

function compactCard(title, items, emptyText) {
  const cleaned = items.map(stringValue).filter(Boolean).slice(0, 6);
  return `
    <article class="details-card">
      <h3>${escapeHtml(title)}</h3>
      ${cleaned.length
        ? `<ul>${cleaned.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
        : `<p>${escapeHtml(emptyText)}</p>`}
    </article>
  `;
}

function renderValue(value) {
  if (Array.isArray(value)) {
    return `<ul>${value.slice(0, 8).map((item) => `<li>${escapeHtml(stringValue(item))}</li>`).join("")}</ul>`;
  }
  if (value && typeof value === "object") {
    return `<ul>${Object.entries(value).slice(0, 8).map(([key, item]) =>
      `<li><strong>${escapeHtml(humanize(key))}:</strong> ${escapeHtml(stringValue(item))}</li>`
    ).join("")}</ul>`;
  }
  return `<p>${escapeHtml(stringValue(value))}</p>`;
}

function rawDetails(result) {
  return `
    <details>
      <summary>More details</summary>
      <pre>${escapeHtml(JSON.stringify(result, null, 2))}</pre>
    </details>
  `;
}

function renderError(panel, errors) {
  const friendlyErrors = asArray(errors).map((error) => {
    if (error.code === "self_profile_store_unreadable") {
      return {
        message: "Your private Mindfront profile could not be unlocked in this Windows session. Close Mindfront and start it again from your normal desktop account.",
      };
    }
    return error;
  });
  panel.hidden = false;
  panel.classList.add("is-error");
  panel.innerHTML = `
    ${resultHeader("Mindfront paused", "Fix this and try again", "Needs attention")}
    <ul class="error-list">
      ${friendlyErrors.map((error) =>
        `<li>${error.path ? `<strong>${escapeHtml(error.path)}:</strong> ` : ""}${escapeHtml(error.message || String(error))}</li>`
      ).join("")}
    </ul>
  `;
}

function pickByKey(object, keys) {
  for (const key of keys) {
    const match = Object.keys(object || {}).find((candidate) =>
      candidate.toLowerCase() === key.toLowerCase()
    );
    if (match && object[match] !== null && object[match] !== "") return object[match];
  }
  return "";
}

function flattenHelpfulValues(value, output = []) {
  if (output.length >= 20 || value === null || value === undefined) return output;
  if (typeof value === "string" && value.trim()) output.push(value.trim());
  else if (Array.isArray(value)) value.forEach((item) => flattenHelpfulValues(item, output));
  else if (typeof value === "object") Object.values(value).forEach((item) => flattenHelpfulValues(item, output));
  return output;
}

function statements(records) {
  return asArray(records).map((item) =>
    typeof item === "string" ? item : item.statement || item.text || item.summary || ""
  ).filter(Boolean);
}

function asArray(value) { return Array.isArray(value) ? value : []; }

function stringValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(stringValue).filter(Boolean).join("; ");
  if (typeof value === "object") {
    return Object.entries(value).map(([key, item]) => `${humanize(key)}: ${stringValue(item)}`).join("; ");
  }
  return String(value);
}

function humanize(value) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 5200);
}
