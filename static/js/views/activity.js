import { api } from "../api.js";
import { h, mount } from "../dom.js";
import { formatShortDateTime } from "../format.js";
import { ROLE_LABELS, elder } from "../state.js";

export async function renderActivity(view) {
  const entries = await api("/api/activity?limit=100");
  const tz = elder().timezone;
  mount(
    view,
    h("h1", {}, "Activity"),
    h("p", { class: "meta" }, "Every change is recorded here, so everyone can see who did what."),
    entries.length
      ? h(
          "ol",
          { class: "list" },
          entries.map((e) =>
            h(
              "li",
              { class: "activity-item" },
              h("p", {}, h("strong", {}, e.summary)),
              h(
                "p",
                { class: "meta" },
                `${e.actor_name} (${ROLE_LABELS[e.actor_role] || "System"}) · `,
                h("time", { datetime: e.at }, formatShortDateTime(e.at, tz)),
              ),
            ),
          ),
        )
      : h("p", { class: "empty" }, "Nothing has happened yet."),
  );
}
