import { api } from "../api.js";
import { confirmAction, field, h, mount, onSubmit, optional, toast } from "../dom.js";
import { formatDate, formatTime, todayIn } from "../format.js";
import { canEdit, elder, isOwner } from "../state.js";

const STATUS_LABELS = { active: "Active", pending: "Awaiting approval", paused: "Paused" };

export async function renderMedicines(view, rerender) {
  const meds = await api("/api/medications");
  const formSlot = h("div");
  const needsApproval = !isOwner() && elder().settings?.require_approval;

  const openForm = (med = null) => {
    mount(formSlot, medicineForm(med, rerender, () => mount(formSlot)));
    formSlot.querySelector("input")?.focus();
  };

  mount(
    view,
    h(
      "div",
      { class: "row" },
      h("h1", {}, "Medicines"),
      canEdit()
        ? h("button", { type: "button", class: "btn-primary", onclick: () => openForm() }, "+ Add a medicine")
        : null,
    ),
    needsApproval
      ? h("p", { class: "notice" }, `Changes you make will wait for ${elder().name} to approve them.`)
      : null,
    formSlot,
    meds.length
      ? h("ul", { class: "list" }, meds.map((m) => medicineCard(m, openForm, rerender)))
      : h("p", { class: "empty" }, "No medicines added yet."),
  );
}

function medicineCard(med, openForm, rerender) {
  const approve = async () => {
    try {
      await api(`/api/medications/${encodeURIComponent(med.id)}/approve`, { method: "POST" });
      toast(`${med.name} approved.`);
      await rerender();
    } catch (err) {
      toast(err.message, { error: true });
    }
  };
  const remove = async () => {
    if (!(await confirmAction(`Remove ${med.name}? Its reminders will stop.`, "Remove medicine"))) return;
    try {
      await api(`/api/medications/${encodeURIComponent(med.id)}`, { method: "DELETE" });
      toast(`${med.name} removed.`);
      await rerender();
    } catch (err) {
      toast(err.message, { error: true });
    }
  };

  return h(
    "li",
    { class: "card" },
    h(
      "div",
      { class: "row" },
      h("h2", {}, `${med.name} · ${med.dosage}`),
      h("span", { class: `badge badge-${med.status}` }, STATUS_LABELS[med.status] || med.status),
    ),
    h("p", {}, h("strong", {}, "Times: "), med.times.map(formatTime).join(", ")),
    med.instructions ? h("p", {}, med.instructions) : null,
    h(
      "p",
      { class: "meta" },
      `From ${formatDate(med.start_date)}`,
      med.end_date ? ` until ${formatDate(med.end_date)}` : "",
      med.created_by ? ` · Added by ${med.created_by}` : "",
    ),
    h(
      "div",
      { class: "actions" },
      isOwner() && med.status === "pending"
        ? h("button", { type: "button", class: "btn-success", onclick: approve }, "Approve")
        : null,
      canEdit()
        ? h(
            "button",
            { type: "button", class: "btn-secondary", onclick: () => openForm(med), "aria-label": `Edit ${med.name}` },
            "Edit",
          )
        : null,
      canEdit()
        ? h(
            "button",
            { type: "button", class: "btn-ghost", onclick: remove, "aria-label": `Remove ${med.name}` },
            "Remove",
          )
        : null,
    ),
  );
}

function timeRow(value = "") {
  const row = h(
    "div",
    { class: "time-row" },
    h("input", { type: "time", name: "times", value, required: true, "aria-label": "Dose time" }),
  );
  row.append(
    h(
      "button",
      { type: "button", class: "btn-ghost", onclick: () => row.remove(), "aria-label": "Remove this time" },
      "Remove",
    ),
  );
  return row;
}

function medicineForm(med, rerender, close) {
  const editing = Boolean(med);
  const times = h("div", { class: "times-list" }, (med?.times || ["08:00"]).map((t) => timeRow(t)));

  const form = onSubmit(
    h(
      "form",
      { "aria-labelledby": "med-form-title", novalidate: true },
      h("h2", { id: "med-form-title" }, editing ? `Edit ${med.name}` : "Add a medicine"),
      h(
        "div",
        { class: "grid-2" },
        field("m-name", "Medicine name", h("input", { name: "name", required: true, maxlength: 100, value: med?.name || "" })),
        field("m-dosage", "Dose", h("input", { name: "dosage", required: true, maxlength: 60, value: med?.dosage || "" }), "e.g. 500 mg or 1 tablet"),
      ),
      field(
        "m-instr",
        "Instructions (optional)",
        h("textarea", { name: "instructions", maxlength: 300 }, med?.instructions || ""),
        "e.g. After breakfast, with water",
      ),
      h(
        "fieldset",
        {},
        h("legend", {}, "Times to take it each day"),
        times,
        h(
          "button",
          { type: "button", class: "btn-ghost", onclick: () => times.append(timeRow()) },
          "+ Add another time",
        ),
      ),
      h(
        "div",
        { class: "grid-2" },
        field("m-start", "Start date", h("input", { name: "start_date", type: "date", required: true, value: med?.start_date || todayIn(elder().timezone) })),
        field("m-end", "End date (optional)", h("input", { name: "end_date", type: "date", value: med?.end_date || "" }), "Leave empty if ongoing"),
      ),
      editing
        ? h(
            "label",
            { class: "checkbox" },
            h("input", { type: "checkbox", name: "paused", checked: med.status === "paused" }),
            "Pause this medicine (no reminders)",
          )
        : null,
      h(
        "div",
        { class: "actions" },
        h("button", { type: "submit", class: "btn-primary" }, editing ? "Save changes" : "Add medicine"),
        h("button", { type: "button", class: "btn-secondary", onclick: close }, "Cancel"),
      ),
    ),
    async (data) => {
      const body = {
        name: data.get("name"),
        dosage: data.get("dosage"),
        instructions: data.get("instructions") || "",
        times: data.getAll("times").filter(Boolean),
        start_date: data.get("start_date"),
        end_date: optional(data.get("end_date")),
      };
      if (editing) body.paused = data.get("paused") === "on";
      const saved = await api(editing ? `/api/medications/${encodeURIComponent(med.id)}` : "/api/medications", {
        method: editing ? "PUT" : "POST",
        body,
      });
      toast(saved.status === "pending" ? "Saved. Waiting for approval." : `${saved.name} saved.`);
      await rerender();
    },
  );
  return h("section", { class: "card highlight" }, form);
}
