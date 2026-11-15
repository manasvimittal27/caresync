// CareSync front end: a small hash-routed app with no build step.

import { api, ApiError } from "./js/api.js";
import { h, mount, toast } from "./js/dom.js";
import { ROLE_LABELS, state } from "./js/state.js";
import { renderActivity } from "./js/views/activity.js";
import { renderAppointments } from "./js/views/appointments.js";
import { renderAssistant } from "./js/views/assistant.js";
import { renderCircle } from "./js/views/circle.js";
import { renderMedicines } from "./js/views/medicines.js";
import { renderToday } from "./js/views/today.js";
import { renderWelcome } from "./js/views/welcome.js";

const ROUTES = {
  today: { title: "Today", render: renderToday },
  assistant: { title: "Care assistant", render: renderAssistant },
  medicines: { title: "Medicines", render: renderMedicines },
  appointments: { title: "Appointments", render: renderAppointments },
  circle: { title: "Care circle", render: renderCircle },
  activity: { title: "Activity", render: renderActivity },
};

const view = document.getElementById("view");
let lastRoute = null;

function currentRoute() {
  const name = location.hash.replace(/^#\/?/, "");
  return ROUTES[name] ? name : "today";
}

function updateChrome() {
  const signedIn = Boolean(state.me);
  document.getElementById("app-nav").hidden = !signedIn;
  document.getElementById("user-box").hidden = !signedIn;
  if (!signedIn) return;
  document.getElementById("user-name").textContent = state.me.member.name;
  document.getElementById("user-role").textContent = ROLE_LABELS[state.me.member.role];
  const route = currentRoute();
  for (const link of document.querySelectorAll("#app-nav a")) {
    if (link.dataset.route === route) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

async function loadSession() {
  const session = await api("/api/session");
  state.me = session.signed_in ? { elder: session.elder, member: session.member } : null;
}

/** Render the current screen. Moves focus to the new heading when the screen changes. */
async function render() {
  view.setAttribute("aria-busy", "true");
  try {
    if (state.me === null) await loadSession();
    updateChrome();
    if (!state.me) {
      document.title = "CareSync: sign in";
      renderWelcome(view, onSignedIn);
      lastRoute = "welcome";
    } else {
      const route = currentRoute();
      document.title = `${ROUTES[route].title} · CareSync`;
      await ROUTES[route].render(view, render);
      if (lastRoute !== route) {
        const heading = view.querySelector("h1");
        if (heading) {
          heading.tabIndex = -1;
          heading.focus();
        }
      }
      lastRoute = route;
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      state.me = null;
      return render();
    }
    mount(
      view,
      h("h1", {}, "Something went wrong"),
      h("p", { class: "form-error", role: "alert" }, err.message || "Please try again."),
      h("button", { type: "button", class: "btn-primary", onclick: () => render() }, "Try again"),
    );
  } finally {
    view.setAttribute("aria-busy", "false");
  }
}

function onSignedIn() {
  lastRoute = null;
  if (location.hash !== "#/today") location.hash = "#/today";
  else render();
}

async function signOut() {
  try {
    await api("/api/session/logout", { method: "POST" });
  } finally {
    state.me = null;
    lastRoute = null;
    window.speechSynthesis?.cancel();
    toast("You have signed out.");
    await render();
  }
}

// ---- Text size preference (kept in this browser only) ----
function applyTextSize(size) {
  document.documentElement.dataset.textSize = size;
  for (const btn of document.querySelectorAll("[data-text-size]")) {
    btn.setAttribute("aria-pressed", String(btn.dataset.textSize === size));
  }
  try {
    localStorage.setItem("caresync-text-size", size);
  } catch {
    /* Storage can be unavailable (private mode); the setting still applies now. */
  }
}

function initTextSize() {
  let saved = "normal";
  try {
    saved = localStorage.getItem("caresync-text-size") || "normal";
  } catch {
    /* ignore */
  }
  applyTextSize(saved);
  for (const btn of document.querySelectorAll("[data-text-size]")) {
    btn.addEventListener("click", () => applyTextSize(btn.dataset.textSize));
  }
}

initTextSize();
document.getElementById("sign-out").addEventListener("click", signOut);
window.addEventListener("hashchange", render);
render();
