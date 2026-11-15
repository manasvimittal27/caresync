import { api } from "../api.js";
import { field, h, mount, onSubmit } from "../dom.js";
import { elder, isOwner } from "../state.js";

const PRIORITY_LABELS = { urgent: "Needs attention", high: "Important", medium: "Worth knowing", low: "Good news" };

/** One explained suggestion. "Why am I seeing this?" shows the rule's reasoning. */
export function insightCard(insight) {
  return h(
    "li",
    { class: `card insight insight-${insight.priority}` },
    h(
      "div",
      { class: "row" },
      h("h3", {}, insight.title),
      h("span", { class: `badge badge-prio-${insight.priority}` }, PRIORITY_LABELS[insight.priority]),
    ),
    h("p", {}, insight.message),
    h(
      "details",
      {},
      h("summary", {}, "Why am I seeing this?"),
      h("p", { class: "meta" }, insight.reason),
    ),
    insight.action_href
      ? h("a", { class: "btn btn-secondary", href: insight.action_href }, insight.action_label)
      : null,
  );
}

export function insightList(insights) {
  return insights.length
    ? h("ul", { class: "list" }, insights.map(insightCard))
    : h("p", { class: "empty" }, "Nothing needs attention right now.");
}

export async function renderAssistant(view) {
  const data = await api("/api/assistant");
  const subject = isOwner() ? "your" : `${elder().name.split(" ")[0]}'s`;

  mount(
    view,
    h("h1", {}, "Care assistant"),
    h(
      "p",
      { class: "meta" },
      `Looks at ${subject} medicines, doses, appointments and patterns, and suggests what to do next.`,
    ),
    h("p", { class: "headline", role: "status" }, data.headline),
    h("section", { "aria-labelledby": "suggestions-title" }, h("h2", { id: "suggestions-title" }, "Suggestions"), insightList(data.insights)),
    askSection(data.ai_enabled),
  );
}

function askSection(enabled) {
  if (!enabled) {
    return h(
      "section",
      { class: "card", "aria-labelledby": "ask-title" },
      h("h2", { id: "ask-title" }, "Ask a question"),
      h("p", { class: "meta" }, "Questions in plain language are not turned on for this app yet. The suggestions above always work."),
    );
  }
  const answerBox = h("div", { "aria-live": "polite" });
  const form = onSubmit(
    h(
      "form",
      { "aria-labelledby": "ask-title" },
      h("h2", { id: "ask-title" }, "Ask a question"),
      field(
        "ask-q",
        "Your question",
        h("textarea", { name: "question", required: true, minlength: 3, maxlength: 500 }),
        "e.g. Can I take my medicine with tea? What should I ask the doctor tomorrow?",
      ),
      h("button", { type: "submit", class: "btn-primary" }, "Ask"),
    ),
    async (data) => {
      mount(answerBox, h("p", { class: "meta" }, "Thinking…"));
      try {
        const res = await api("/api/assistant/ask", { method: "POST", body: { question: data.get("question") } });
        mount(
          answerBox,
          h(
            "div",
            { class: "card highlight" },
            h("h3", {}, "Answer"),
            h("p", { class: "answer" }, res.answer),
            h("p", { class: "meta" }, res.disclaimer),
          ),
        );
      } catch (err) {
        mount(answerBox);
        throw err;
      }
    },
  );
  return h("section", { class: "card" }, form, answerBox);
}
