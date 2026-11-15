// Signed-in session state shared by all views.

export const state = { me: null };

export const ROLE_LABELS = { elder: "Profile owner", caretaker: "Caretaker", family: "Family" };

export const role = () => state.me?.member.role;
export const isOwner = () => role() === "elder";
export const canEdit = () => role() === "elder" || role() === "caretaker";
export const elder = () => state.me.elder;
