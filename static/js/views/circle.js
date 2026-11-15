import { api } from "../api.js";
import { confirmAction, field, h, mount, onSubmit, toast } from "../dom.js";
import { ROLE_LABELS, elder, isOwner, state } from "../state.js";

export async function renderCircle(view, rerender) {
  const [members, email] = await Promise.all([api("/api/members"), api("/api/notifications/status")]);
  const inviteSlot = h("div", { "aria-live": "polite" });
  const me = state.me.member;

  mount(
    view,
    h("h1", {}, "Care circle"),
    h(
      "p",
      { class: "meta" },
      isOwner()
        ? "These people can see your care information. You decide who is here."
        : `${elder().name} decides who is in this care circle.`,
    ),
    isOwner() ? ownerPanel(rerender) : null,
    isOwner() ? emailPanel(email.email_enabled) : null,
    h(
      "section",
      { "aria-labelledby": "members-title" },
      h("h2", { id: "members-title" }, `People with access (${members.length})`),
      h("ul", { class: "list" }, members.map((m) => memberCard(m, m.id === me.id, rerender))),
    ),
    isOwner() ? inviteSlot : null,
    isOwner() ? addMemberForm(inviteSlot, rerender) : null,
  );
}

function ownerPanel(rerender) {
  const settings = elder().settings || {};
  const toggle = h("input", {
    type: "checkbox",
    id: "require-approval",
    checked: Boolean(settings.require_approval),
    onchange: async (e) => {
      try {
        const updated = await api("/api/profile/settings", {
          method: "PUT",
          body: { require_approval: e.target.checked },
        });
        state.me.elder = updated;
        toast(e.target.checked ? "Caretaker changes now need your approval." : "Approval turned off.");
      } catch (err) {
        e.target.checked = !e.target.checked;
        toast(err.message, { error: true });
      }
    },
  });
  return h(
    "section",
    { class: "card stack", "aria-labelledby": "code-title" },
    h("h2", { id: "code-title" }, "Your Care Code"),
    h(
      "p",
      { "aria-label": `Care Code: ${elder().care_code.split("").join(" ")}` },
      h("span", { class: "code-box" }, elder().care_code),
    ),
    h("p", { class: "meta" }, "People need this code and their own passcode to sign in."),
    h(
      "label",
      { class: "checkbox", for: "require-approval" },
      toggle,
      "Ask me to approve medicine changes made by caretakers",
    ),
  );
}

function emailPanel(enabled) {
  const sendTest = async (e) => {
    e.target.disabled = true;
    try {
      const res = await api("/api/notifications/test", { method: "POST" });
      toast(`Test email sent to ${res.to}. Check your inbox.`);
    } catch (err) {
      toast(err.message, { error: true });
    } finally {
      e.target.disabled = false;
    }
  };
  return h(
    "section",
    { class: "card stack", "aria-labelledby": "email-title" },
    h("h2", { id: "email-title" }, "Email reminders"),
    enabled
      ? h(
          "p",
          {},
          "On. Everyone in the circle is emailed about upcoming doses, missed doses (family and caretakers) " +
            "and appointments (a day before and 2 hours before).",
        )
      : h("p", { class: "meta" }, "Email is not set up for this app yet, so reminders are shown in the app only."),
    enabled ? h("button", { type: "button", class: "btn-secondary", onclick: sendTest }, "Send me a test email") : null,
  );
}

function memberCard(member, isMe, rerender) {
  const remove = async () => {
    const ok = await confirmAction(
      `Remove ${member.name} from your care circle? They will lose access immediately.`,
      "Remove access",
    );
    if (!ok) return;
    try {
      await api(`/api/members/${encodeURIComponent(member.id)}`, { method: "DELETE" });
      toast(`${member.name} no longer has access.`);
      await rerender();
    } catch (err) {
      toast(err.message, { error: true });
    }
  };
  return h(
    "li",
    { class: "card row" },
    h(
      "div",
      {},
      h("h3", {}, member.name, isMe ? " (you)" : ""),
      h("p", { class: "meta" }, member.email),
      h("span", { class: "badge" }, ROLE_LABELS[member.role]),
    ),
    isOwner() && !isMe
      ? h(
          "button",
          { type: "button", class: "btn-ghost", onclick: remove, "aria-label": `Remove ${member.name}` },
          "Remove access",
        )
      : null,
  );
}

function addMemberForm(inviteSlot, rerender) {
  const form = onSubmit(
    h(
      "form",
      { "aria-labelledby": "invite-title", novalidate: true },
      h("h2", { id: "invite-title" }, "Invite someone"),
      h(
        "div",
        { class: "grid-2" },
        field("i-name", "Their name", h("input", { name: "name", required: true, maxlength: 80 })),
        field("i-email", "Their email", h("input", { name: "email", type: "email", required: true })),
      ),
      field(
        "i-role",
        "Their role",
        h(
          "select",
          { name: "role", required: true },
          h("option", { value: "caretaker" }, "Caretaker: can update medicines, appointments and doses"),
          h("option", { value: "family" }, "Family: can view everything and gets missed-dose alerts"),
        ),
      ),
      h("button", { type: "submit", class: "btn-primary" }, "Invite"),
    ),
    async (data) => {
      const result = await api("/api/members", {
        method: "POST",
        body: { name: data.get("name"), email: data.get("email"), role: data.get("role") },
      });
      await rerender();
      // Re-rendering replaced the slot; find the new one and show sign-in details once.
      const slot = document.querySelector("[data-invite-slot]") || inviteSlot;
      showInvite(slot, result);
    },
  );
  inviteSlot.setAttribute("data-invite-slot", "");
  return h("section", { class: "card" }, form);
}

function showInvite(slot, { member, passcode, care_code: careCode, emailed }) {
  mount(
    slot,
    h(
      "section",
      { class: "card highlight stack", tabindex: "-1", "aria-labelledby": "invite-done" },
      h("h2", { id: "invite-done" }, `${member.name} has been added`),
      h(
        "p",
        {},
        emailed
          ? `We've emailed these sign-in details to ${member.email}. The passcode is shown here only once.`
          : "Share these sign-in details privately. The passcode is shown only once.",
      ),
      h(
        "dl",
        {},
        h("dt", {}, "Care Code"),
        h("dd", {}, h("span", { class: "code-box" }, careCode)),
        h("dt", {}, "Email"),
        h("dd", {}, member.email),
        h("dt", {}, "Passcode"),
        h("dd", {}, h("span", { class: "code-box" }, passcode)),
      ),
    ),
  );
  slot.querySelector("section").focus();
}
