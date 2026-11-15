// DOM helpers. Content is always set as text, never parsed as HTML (XSS-safe).

const PROPS = new Set(["value", "checked", "disabled", "selected"]);

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === false || value === null || value === undefined) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (PROPS.has(key)) el[key] = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function mount(container, ...children) {
  container.replaceChildren();
  append(container, children);
}

let toastTimer;
export function toast(message, { error = false } = {}) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.toggle("error", error);
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), error ? 7000 : 4000);
}

export function confirmAction(message, confirmLabel = "Yes, continue") {
  const dialog = document.getElementById("confirm-dialog");
  document.getElementById("confirm-message").textContent = message;
  document.getElementById("confirm-yes").textContent = confirmLabel;
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
    dialog.returnValue = "cancel";
    dialog.showModal();
  });
}

/** Labelled form field. `input` is an element; hint text is linked via aria-describedby. */
export function field(id, label, input, hint) {
  input.id = id;
  const hintId = hint ? `${id}-hint` : null;
  if (hintId) input.setAttribute("aria-describedby", hintId);
  return h(
    "div",
    { class: "field" },
    h("label", { for: id }, label),
    hint ? h("span", { id: hintId, class: "hint" }, hint) : null,
    input,
  );
}

/**
 * Wire a form: disables the submit button while saving and shows errors in an
 * alert region that receives focus, so screen-reader users hear what went wrong.
 */
export function onSubmit(form, handler) {
  const errorBox = h("div", { class: "form-error", role: "alert", tabindex: "-1", hidden: true });
  form.prepend(errorBox);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    errorBox.hidden = true;
    if (button) button.disabled = true;
    try {
      await handler(new FormData(form));
    } catch (err) {
      errorBox.textContent = err.message || "Something went wrong. Please try again.";
      errorBox.hidden = false;
      errorBox.focus();
    } finally {
      if (button && button.isConnected) button.disabled = false;
    }
  });
  return form;
}

export const splitList = (text) =>
  String(text || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

export const optional = (value) => (value === "" || value === null ? null : value);
