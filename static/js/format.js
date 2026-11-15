// Date and time formatting, always in the elder's own timezone.

export function formatTime(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  const suffix = h < 12 ? "AM" : "PM";
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${suffix}`;
}

export function formatDateTime(isoUtc, timeZone) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone,
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(isoUtc));
}

export function formatShortDateTime(isoUtc, timeZone) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone,
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(isoUtc));
}

export function formatDate(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "long", year: "numeric" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

export function longToday(timeZone) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone,
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());
}

function parts(date, timeZone) {
  const out = {};
  for (const p of new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date)) {
    out[p.type] = p.value;
  }
  return out;
}

/** "YYYY-MM-DD" for today in the given timezone. */
export function todayIn(timeZone) {
  const p = parts(new Date(), timeZone);
  return `${p.year}-${p.month}-${p.day}`;
}

/** Value for <input type="datetime-local"> showing a UTC instant in the elder's timezone. */
export function toLocalInput(isoUtc, timeZone) {
  const p = parts(new Date(isoUtc), timeZone);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

export function partOfDay(timeZone) {
  const hour = Number(parts(new Date(), timeZone).hour);
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  return "evening";
}
