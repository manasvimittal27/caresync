import { api } from "../api.js";
import { field, h, mount, onSubmit, optional, splitList } from "../dom.js";
import { state } from "../state.js";

export function renderWelcome(view, onSignedIn) {
  const createForm = onSubmit(
    h(
      "form",
      { "aria-labelledby": "create-title", novalidate: true },
      field("c-name", "Your full name", h("input", { name: "elder_name", required: true, autocomplete: "name", maxlength: 80 })),
      field("c-email", "Your email", h("input", { name: "email", type: "email", required: true, autocomplete: "email" }), "Reminders are sent here."),
      field(
        "c-pass",
        "Choose a passcode",
        h("input", { name: "passcode", type: "password", required: true, minlength: 6, autocomplete: "new-password" }),
        "At least 6 characters. You will use it to sign in.",
      ),
      field("c-dob", "Date of birth (optional)", h("input", { name: "date_of_birth", type: "date" })),
      field("c-allergies", "Allergies (optional)", h("input", { name: "allergies" }), "Separate with commas, e.g. Penicillin, Peanuts"),
      field("c-conditions", "Health conditions (optional)", h("input", { name: "conditions" }), "Separate with commas, e.g. Diabetes, High blood pressure"),
      h("button", { type: "submit", class: "btn-primary btn-big" }, "Create my care profile"),
    ),
    async (data) => {
      const result = await api("/api/profiles", {
        method: "POST",
        body: {
          elder_name: data.get("elder_name"),
          email: data.get("email"),
          passcode: data.get("passcode"),
          date_of_birth: optional(data.get("date_of_birth")),
          allergies: splitList(data.get("allergies")),
          conditions: splitList(data.get("conditions")),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata",
        },
      });
      state.me = result;
      renderCareCode(view, result.elder.care_code, onSignedIn);
    },
  );

  const signInForm = onSubmit(
    h(
      "form",
      { "aria-labelledby": "signin-title", novalidate: true },
      field(
        "s-code",
        "Care Code",
        h("input", { name: "care_code", required: true, minlength: 6, maxlength: 6, autocomplete: "off", autocapitalize: "characters", spellcheck: "false" }),
        "The 6-character code for the care profile.",
      ),
      field("s-email", "Your email", h("input", { name: "email", type: "email", required: true, autocomplete: "email" })),
      field("s-pass", "Your passcode", h("input", { name: "passcode", type: "password", required: true, autocomplete: "current-password" })),
      h("button", { type: "submit", class: "btn-primary btn-big" }, "Sign in"),
    ),
    async (data) => {
      state.me = await api("/api/session", {
        method: "POST",
        body: { care_code: data.get("care_code"), email: data.get("email"), passcode: data.get("passcode") },
      });
      onSignedIn();
    },
  );

  mount(
    view,
    h(
      "section",
      { class: "hero" },
      h("h1", {}, "Care that keeps everyone in sync"),
      h(
        "p",
        {},
        "One shared place for medicines, doses and doctor visits. You stay in charge; your family and caretakers stay informed.",
      ),
    ),
    h(
      "div",
      { class: "welcome-grid" },
      h("section", { class: "card" }, h("h2", { id: "signin-title" }, "Sign in"), signInForm),
      h(
        "section",
        { class: "card" },
        h("h2", { id: "create-title" }, "New here? Create a care profile"),
        h("p", { class: "meta" }, "For the person receiving care. You can invite family and caretakers next."),
        createForm,
      ),
    ),
  );
}

function renderCareCode(view, code, onDone) {
  mount(
    view,
    h(
      "section",
      { class: "card highlight stack" },
      h("h1", {}, "Your care profile is ready"),
      h("p", {}, "This is your Care Code. Keep it safe and share it only with people you trust."),
      h("p", { "aria-label": `Care Code: ${code.split("").join(" ")}` }, h("span", { class: "code-box" }, code)),
      h(
        "p",
        { class: "meta" },
        "To invite someone, go to Care circle. Each person gets their own passcode, and you can remove anyone at any time.",
      ),
      h("button", { type: "button", class: "btn-primary btn-big", onclick: onDone }, "Go to my day"),
    ),
  );
}
