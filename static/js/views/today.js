import { api } from "../api.js";
import { h, mount, toast } from "../dom.js";
import { formatDateTime, formatTime, longToday, partOfDay } from "../format.js";
import { canEdit, elder, isOwner } from "../state.js";
import { insightList } from "./assistant.js";

const STATUS_LABELS = {
  upcoming: "Coming up",
  due: "Due now",
  overdue: "Not taken yet",
  taken: "Taken",
  skipped: "Skipped",
  missed: "Missed",
};

export async function renderToday(view, rerender) {
  const tz = elder().timezone;
  const [today, adherence, appointments, insights] = await Promise.all([
    api("/api/doses/today"),
    api("/api/adherence?days=7"),
    api("/api/appointments"),
    api("/api/assistant"),
  ]);
  const title = isOwner()
    ? `Good ${partOfDay(tz)}, ${elder().name.split(" ")[0]}`
    : `${elder().name}'s day`;

  const remaining = today.doses.filter((d) => !["taken", "skipped"].includes(d.status));

  mount(
    view,
    h("h1", {}, title),
    h("p", { class: "meta" }, longToday(tz)),
    assistantPanel(insights),
    adherenceCard(adherence),
    h(
      "section",
      { "aria-labelledby": "doses-title" },
      h(
        "div",
        { class: "row" },
        h("h2", { id: "doses-title" }, "Today's medicines"),
        readAloudButton(remaining),
      ),
      today.doses.length
        ? h("ul", { class: "list" }, today.doses.map((dose) => doseCard(dose, rerender)))
        : h(
            "p",
            { class: "empty" },
            "No medicines scheduled today. ",
            canEdit() ? h("a", { href: "#/medicines" }, "Add a medicine") : null,
          ),
    ),
    nextAppointment(appointments[0], tz),
  );
}

function assistantPanel(data) {
  const top = data.insights.slice(0, 3);
  return h(
    "section",
    { class: "card assistant-panel", "aria-labelledby": "assistant-title" },
    h("h2", { id: "assistant-title" }, "Your care assistant"),
    h("p", { class: "headline", role: "status" }, data.headline),
    insightList(top),
    data.insights.length > top.length
      ? h("a", { href: "#/assistant" }, `See all ${data.insights.length} suggestions`)
      : h("a", { href: "#/assistant" }, "Open the care assistant"),
  );
}

function adherenceCard(adherence) {
  const pct = adherence.percent;
  return h(
    "section",
    { class: "card", "aria-labelledby": "adherence-title" },
    h("h2", { id: "adherence-title" }, "Last 7 days"),
    pct === null
      ? h("p", { class: "empty" }, "No doses were due yet this week.")
      : h(
          "div",
          { class: "stat" },
          h("span", { class: "stat-number" }, `${Math.round(pct)}%`),
          h(
            "div",
            { class: "field" },
            h("meter", {
              min: 0,
              max: 100,
              low: 60,
              high: 85,
              optimum: 100,
              value: pct,
              "aria-label": `Doses taken in the last 7 days: ${Math.round(pct)} percent`,
            }),
            h("span", { class: "meta" }, `${adherence.taken} of ${adherence.scheduled} doses taken on time`),
          ),
        ),
  );
}

function doseCard(dose, rerender) {
  const log = async (status) => {
    try {
      await api("/api/doses", {
        method: "POST",
        body: { medication_id: dose.medication_id, time: dose.time, status },
      });
      toast(status === "taken" ? `Well done! ${dose.name} marked as taken.` : `${dose.name} marked as skipped.`);
      await rerender();
    } catch (err) {
      toast(err.message, { error: true });
    }
  };

  const done = dose.status === "taken" || dose.status === "skipped";
  return h(
    "li",
    { class: `card dose is-${dose.status}` },
    h("span", { class: "dose-time" }, formatTime(dose.time)),
    h(
      "div",
      {},
      h("h3", {}, `${dose.name} · ${dose.dosage}`),
      dose.instructions ? h("p", { class: "meta" }, dose.instructions) : null,
      h(
        "p",
        {},
        h("span", { class: `badge badge-${dose.status}` }, STATUS_LABELS[dose.status] || dose.status),
        dose.logged_by ? h("span", { class: "meta" }, ` by ${dose.logged_by}`) : null,
      ),
    ),
    canEdit() && !done
      ? h(
          "div",
          { class: "actions" },
          h(
            "button",
            {
              type: "button",
              class: "btn-success btn-big",
              onclick: () => log("taken"),
              "aria-label": `I took ${dose.name} at ${formatTime(dose.time)}`,
            },
            "✓ I took it",
          ),
          h(
            "button",
            {
              type: "button",
              class: "btn-secondary",
              onclick: () => log("skipped"),
              "aria-label": `Skip ${dose.name} at ${formatTime(dose.time)}`,
            },
            "Skip",
          ),
        )
      : null,
  );
}

function readAloudButton(remaining) {
  if (!("speechSynthesis" in window)) return null;
  const speak = () => {
    window.speechSynthesis.cancel();
    const text = remaining.length
      ? `You have ${remaining.length} medicine${remaining.length > 1 ? "s" : ""} left today. ` +
        remaining.map((d) => `${d.name}, ${d.dosage}, at ${formatTime(d.time)}.`).join(" ")
      : "All of today's medicines are done. Well done!";
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
  };
  return h("button", { type: "button", class: "btn-secondary", onclick: speak }, "🔊 Read aloud");
}

function nextAppointment(appt, tz) {
  return h(
    "section",
    { class: "card", "aria-labelledby": "next-appt-title" },
    h("h2", { id: "next-appt-title" }, "Next appointment"),
    appt
      ? h(
          "div",
          {},
          h("p", {}, h("strong", {}, formatDateTime(appt.starts_at, tz))),
          h("p", {}, `${appt.doctor}${appt.specialty ? ` (${appt.specialty})` : ""}`),
          appt.location ? h("p", { class: "meta" }, appt.location) : null,
        )
      : h("p", { class: "empty" }, "No upcoming appointments."),
    h("a", { href: "#/appointments" }, "See all appointments"),
  );
}
