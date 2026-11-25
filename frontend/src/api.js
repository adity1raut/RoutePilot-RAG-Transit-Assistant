// Thin client for the RoutePilot FastAPI backend.
const BASE = import.meta.env.VITE_API_URL || "";

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return res.json();
}

const qs = (params) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== "")).toString();

export const api = {
  health: () => request("/api/health"),
  stops: () => request("/api/stops"),
  routes: () => request("/api/routes"),
  map: () => request("/api/map"),
  fareChart: () => request("/api/fare-chart"),
  timetable: (routeNo, dayType, direction) =>
    request(`/api/routes/${encodeURIComponent(routeNo)}/timetable?${qs({ day_type: dayType, direction })}`),
  journeys: (source, destination, dayType) =>
    request(`/api/journeys?${qs({ source, destination, day_type: dayType })}`),
  fares: (source, destination) => request(`/api/fares?${qs({ source, destination })}`),
  chat: (question, history) =>
    request("/api/chat", { method: "POST", body: JSON.stringify({ question, history }) }),
};

export const DAY_TYPES = ["Weekday", "Saturday", "Sunday/Holiday"];

export function todayDayType(date = new Date()) {
  return { 6: "Saturday", 0: "Sunday/Holiday" }[date.getDay()] || "Weekday";
}

export function formatMinutes(minutes) {
  if (minutes < 60) return `${minutes} min`;
  const m = minutes % 60;
  return `${Math.floor(minutes / 60)} h${m ? ` ${m} min` : ""}`;
}
