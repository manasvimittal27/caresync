// Thin JSON client for the CareSync API. Sessions travel in an httpOnly cookie.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const FIELD_LABELS = {
  elder_name: "Name",
  email: "Email",
  passcode: "Passcode",
  new_passcode: "New passcode",
  care_code: "Care Code",
  date_of_birth: "Date of birth",
  times: "Dose times",
  start_date: "Start date",
  end_date: "End date",
  starts_at: "Date and time",
  duration_minutes: "Duration",
  name: "Name",
  dosage: "Dose",
  doctor: "Doctor's name",
  role: "Role",
};

// Turn validation messages into plain language.
function friendly(msg) {
  if (/at least 1 character|Field required/i.test(msg)) return "is required";
  const min = msg.match(/at least (\d+) characters?/i);
  if (min) return `must be at least ${min[1]} characters`;
  if (/valid date|date format/i.test(msg)) return "needs a valid date";
  if (/at least 1 item/i.test(msg)) return "needs at least one time";
  return msg.charAt(0).toLowerCase() + msg.slice(1);
}

function describe(data) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((err) => {
        const field = Array.isArray(err.loc) ? err.loc[err.loc.length - 1] : null;
        const raw = String(err.msg || "is not valid").replace(/^Value error, /, "");
        const label = FIELD_LABELS[field] || (typeof field === "string" && field !== "body" ? field : "");
        return label ? `${label} ${friendly(raw)}` : raw;
      })
      .join(". ");
  }
  return "Something went wrong. Please try again.";
}

export async function api(path, { method = "GET", body } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach CareSync. Please check your internet connection.");
  }
  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) throw new ApiError(res.status, describe(data));
  return data;
}
