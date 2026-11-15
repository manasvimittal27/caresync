import { api } from "../api.js";
import { confirmAction, field, h, mount, onSubmit, toast } from "../dom.js";
import { formatDateTime, toLocalInput } from "../format.js";
import { canEdit, elder } from "../state.js";

let showPast = false;

export async function renderAppointments(view, rerender) {
  const tz = elder().timezone;
  const appts = await api(`/api/appointments${showPast ? "?include_past=true" : ""}`);
  const formSlot = h("div");

  const openForm = (appt = null) => {
    mount(formSlot, appointmentForm(appt, tz, rerender, () => mount(formSlot)));
    formSlot.querySelector("input")?.focus();
  };

  mount(
    view,
    h(
      "div",
      { class: "row" },
      h("h1", {}, "Appointments"),
      canEdit()
        ? h("button", { type: "button", class: "btn-primary", onclick: () => openForm() }, "+ Add an appointment")
        : null,
    ),
    h(
      "label",
      { class: "checkbox" },
      h("input", {
        type: "checkbox",
        checked: showPast,
        onchange: async (e) => {
          showPast = e.target.checked;
          await rerender();
        },
      }),
      "Show past appointments",
    ),
    formSlot,
    appts.length
      ? h("ul", { class: "list" }, appts.map((a) => appointmentCard(a, tz, openForm, rerender)))
      : h("p", { class: "empty" }, showPast ? "No appointments yet." : "No upcoming appointments."),
  );
}

function appointmentCard(appt, tz, openForm, rerender) {
  const remove = async () => {
    if (!(await confirmAction(`Cancel the appointment with ${appt.doctor}?`, "Remove appointment"))) return;
    try {
      await api(`/api/appointments/${encodeURIComponent(appt.id)}`, { method: "DELETE" });
      toast("Appointment removed.");
      await rerender();
    } catch (err) {
      toast(err.message, { error: true });
    }
  };

  return h(
    "li",
    { class: "card" },
    h("h2", {}, formatDateTime(appt.starts_at, tz)),
    h("p", {}, h("strong", {}, appt.doctor), appt.specialty ? ` · ${appt.specialty}` : "", ` · ${appt.duration_minutes} minutes`),
    appt.location ? h("p", {}, `📍 ${appt.location}`) : null,
    appt.notes ? h("p", { class: "meta" }, appt.notes) : null,
    h(
      "div",
      { class: "actions" },
      h(
        "a",
        {
          class: "btn btn-secondary",
          href: appt.google_calendar_url,
          target: "_blank",
          rel: "noopener noreferrer",
          "aria-label": `Add appointment with ${appt.doctor} to Google Calendar (opens in a new tab)`,
        },
        "📅 Add to Google Calendar",
      ),
      canEdit()
        ? h("button", { type: "button", class: "btn-secondary", onclick: () => openForm(appt), "aria-label": `Edit appointment with ${appt.doctor}` }, "Edit")
        : null,
      canEdit()
        ? h("button", { type: "button", class: "btn-ghost", onclick: remove, "aria-label": `Remove appointment with ${appt.doctor}` }, "Remove")
        : null,
    ),
  );
}

function appointmentForm(appt, tz, rerender, close) {
  const editing = Boolean(appt);
  const form = onSubmit(
    h(
      "form",
      { "aria-labelledby": "appt-form-title", novalidate: true },
      h("h2", { id: "appt-form-title" }, editing ? "Edit appointment" : "Add an appointment"),
      h(
        "div",
        { class: "grid-2" },
        field("a-doctor", "Doctor's name", h("input", { name: "doctor", required: true, maxlength: 80, value: appt?.doctor || "" })),
        field("a-spec", "Speciality (optional)", h("input", { name: "specialty", maxlength: 60, value: appt?.specialty || "" }), "e.g. Cardiology"),
      ),
      h(
        "div",
        { class: "grid-2" },
        field(
          "a-when",
          "Date and time",
          h("input", { name: "starts_at", type: "datetime-local", required: true, value: appt ? toLocalInput(appt.starts_at, tz) : "" }),
        ),
        field(
          "a-dur",
          "Duration (minutes)",
          h("input", { name: "duration_minutes", type: "number", min: 5, max: 480, step: 5, required: true, value: String(appt?.duration_minutes || 30) }),
        ),
      ),
      field("a-loc", "Location (optional)", h("input", { name: "location", maxlength: 200, value: appt?.location || "" })),
      field("a-notes", "Notes (optional)", h("textarea", { name: "notes", maxlength: 500 }, appt?.notes || ""), "e.g. Bring blood test reports"),
      h(
        "div",
        { class: "actions" },
        h("button", { type: "submit", class: "btn-primary" }, editing ? "Save changes" : "Add appointment"),
        h("button", { type: "button", class: "btn-secondary", onclick: close }, "Cancel"),
      ),
    ),
    async (data) => {
      const body = {
        doctor: data.get("doctor"),
        specialty: data.get("specialty") || "",
        starts_at: data.get("starts_at"),
        duration_minutes: Number(data.get("duration_minutes")),
        location: data.get("location") || "",
        notes: data.get("notes") || "",
      };
      await api(editing ? `/api/appointments/${encodeURIComponent(appt.id)}` : "/api/appointments", {
        method: editing ? "PUT" : "POST",
        body,
      });
      toast("Appointment saved.");
      await rerender();
    },
  );
  return h("section", { class: "card highlight" }, form);
}
