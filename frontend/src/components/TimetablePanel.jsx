import { CalendarDays, Clock3, IndianRupee, MapPin, Navigation, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import { api, formatMinutes, todayDayType } from "../api";
import { BusTypeTag, Card, CardHeader, DaySelect, ErrorNote, Field, PageHeader, RouteBadge, Segmented, Select, Spinner, Stat, cx } from "./ui";

const toMinutes = (hhmm) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};
const toHHMM = (minutes) => {
  const m = ((minutes % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};

// Departures as increasing minutes: trips after midnight continue past 24:00 (Night service 7N)
function serviceMinutes(departures) {
  let offset = 0;
  let previous = -1;
  return departures.map((t) => {
    let m = toMinutes(t) + offset;
    if (m < previous) {
      offset += 1440;
      m += 1440;
    }
    previous = m;
    return m;
  });
}

// Index of the next departure, or -1 when the last bus has gone
function nextDeparture(departures, now) {
  const minutes = serviceMinutes(departures);
  let current = now.getHours() * 60 + now.getMinutes();
  // a service that crosses midnight is still "tonight" in the early hours
  if (minutes.length && minutes.at(-1) >= 1440 && current < minutes.at(-1) - 1440) current += 1440;
  return minutes.findIndex((m) => m >= current);
}

// Re-renders every 30 seconds so the "next bus" highlight moves on while the page stays open
function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

// Departures grouped by hour, in timetable order (night services run past midnight)
function byHour(departures) {
  const groups = [];
  departures.forEach((t, i) => {
    const [hour, minute] = t.split(":");
    const last = groups.at(-1);
    if (last && last.hour === hour) last.items.push({ minute, i });
    else groups.push({ hour, items: [{ minute, i }] });
  });
  return groups;
}

export default function TimetablePanel({ routes, routeNo, onRouteChange }) {
  const [dayType, setDayType] = useState(todayDayType());
  const [direction, setDirection] = useState("Up");
  const [table, setTable] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const now = useNow();

  useEffect(() => {
    if (!routeNo && routes.length) onRouteChange(routes[0].route_no);
  }, [routes, routeNo, onRouteChange]);

  useEffect(() => {
    if (!routeNo) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .timetable(routeNo, dayType, direction)
      .then((rows) => !cancelled && setTable(rows[0]))
      .catch((err) => {
        if (cancelled) return;
        setTable(null); // do not leave the previous route's timetable on screen
        setError(err.message);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [routeNo, dayType, direction]);

  const route = routes.find((r) => r.route_no === routeNo);
  const isToday = dayType === todayDayType(now);
  const nextIndex = table && isToday ? nextDeparture(table.departures, now) : -1;
  const offset = (i) => (table ? Math.round((table.duration_min * i) / (table.stops.length - 1)) : 0);

  return (
    <div>
      <PageHeader title="Timetables" description="Every departure for a route, by direction and day, with the time the bus reaches each stop." />
      <Card>
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.1fr)]">
          <Field label="Route" htmlFor="timetable-route">
            <Select
              id="timetable-route"
              value={routeNo}
              onChange={onRouteChange}
              options={routes.map((r) => ({ value: r.route_no, label: `${r.route_no} · ${r.route_name}` }))}
            />
          </Field>
          <Field label="Direction">
            <Segmented
              label="Direction"
              value={direction}
              onChange={setDirection}
              options={
                route
                  ? [
                      { value: "Up", label: `To ${route.destination}` },
                      { value: "Down", label: `To ${route.source}` },
                    ]
                  : ["Up", "Down"]
              }
            />
          </Field>
          <DaySelect value={dayType} onChange={setDayType} />
        </div>
      </Card>

      <div className="mt-6 space-y-4">
        <ErrorNote message={error} />
        {loading && !table && <Spinner label="Loading timetable..." />}
        {table && (
          <div className={cx("space-y-6 transition-opacity", loading && "opacity-60")}>
            <Card>
              <div className="flex flex-wrap items-start gap-4">
                <RouteBadge routeNo={table.route_no} busType={table.bus_type} size="lg" />
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-semibold text-slate-900">
                    {table.source} <span className="text-slate-400">→</span> {table.destination}
                  </h2>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
                    <BusTypeTag busType={table.bus_type} />
                    {table.route_name} · {table.day_type}
                  </div>
                </div>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <Stat icon={Timer} label="Frequency" value={`Every ${table.frequency_min} min`} />
                <Stat icon={Clock3} label="First bus" value={table.first_departure} />
                <Stat icon={Clock3} label="Last bus" value={table.last_departure} />
                <Stat icon={Navigation} label="Journey time" value={formatMinutes(table.duration_min)} />
                <Stat icon={IndianRupee} label="Full fare" value={`₹${table.fare}`} />
              </div>
            </Card>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
              <Card>
                <CardHeader
                  icon={CalendarDays}
                  title={`Departures from ${table.source}`}
                  subtitle={`${table.departures.length} buses · ${table.day_type}`}
                  action={
                    nextIndex >= 0 && (
                      <span className="flex items-center gap-1.5 text-xs text-slate-500">
                        <span className="h-2.5 w-2.5 rounded-sm bg-emerald-600" />
                        Next bus
                      </span>
                    )
                  }
                />
                <div className="mt-4 divide-y divide-slate-100">
                  {byHour(table.departures).map(({ hour, items }, row) => (
                    <div key={`${hour}-${row}`} className="flex items-start gap-4 py-2">
                      <div className="w-10 shrink-0 pt-1 text-right text-sm font-semibold tabular-nums text-slate-900">{hour}</div>
                      <div className="flex flex-wrap gap-1.5">
                        {items.map(({ minute, i }) => (
                          <span
                            key={i}
                            title={`${hour}:${minute}${i === nextIndex ? " · next bus" : ""}`}
                            className={cx(
                              "min-w-[2.5rem] rounded-md px-2 py-1 text-center text-sm tabular-nums",
                              i === nextIndex
                                ? "bg-emerald-600 font-semibold text-white"
                                : nextIndex >= 0 && i < nextIndex
                                  ? "text-slate-400"
                                  : "bg-slate-100 text-slate-700",
                            )}
                          >
                            :{minute}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="lg:self-start">
                <CardHeader
                  icon={MapPin}
                  title={nextIndex >= 0 ? `Next bus, ${table.departures[nextIndex]}` : "Stops"}
                  subtitle={nextIndex >= 0 ? "Estimated time at each stop" : "Minutes from the first stop"}
                />
                <ol className="relative ml-3 mt-4 border-l-2 border-slate-200">
                  {table.stops.map((s, i) => {
                    const end = i === 0 || i === table.stops.length - 1;
                    return (
                      <li key={s} className="relative flex items-center justify-between gap-3 py-1.5 pl-5 text-sm">
                        <span
                          className={cx("absolute -left-[7px] h-3 w-3 rounded-full border-2 border-white", end ? "bg-slate-900" : "bg-slate-300")}
                        />
                        <span className={end ? "font-medium text-slate-900" : "text-slate-600"}>{s}</span>
                        <span className="text-xs tabular-nums text-slate-500">
                          {nextIndex >= 0 ? toHHMM(toMinutes(table.departures[nextIndex]) + offset(i)) : `+${offset(i)} min`}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
