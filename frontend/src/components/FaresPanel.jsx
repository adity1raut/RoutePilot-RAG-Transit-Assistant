import { ChevronRight, CircleDot, Clock3, GraduationCap, Layers, MapPin, MessageSquareText, Search, Table2, Ticket, TicketCheck, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { LINE_STYLES } from "./NetworkMap";
import { Badge, BusTypeTag, Button, Card, CardHeader, Empty, ErrorNote, PageHeader, RouteBadge, Spinner, StopSelect } from "./ui";

const QUESTIONS = [
  { icon: GraduationCap, label: "Student concessions", question: "What concessions do students get?" },
  { icon: UserRound, label: "Senior citizens", question: "What concession do senior citizens get?" },
  { icon: TicketCheck, label: "Monthly passes", question: "How much is a monthly pass?" },
];

function Swatch({ busType }) {
  const style = LINE_STYLES[busType];
  return (
    <svg width="16" height="6" className="mr-1.5 inline-block" aria-hidden>
      <line x1="0" y1="3" x2="16" y2="3" stroke={style.color} strokeWidth="3" strokeDasharray={style.dashArray ? "3 2" : undefined} />
    </svg>
  );
}

export default function FaresPanel({ stops, routes, onOpenTimetable, onAsk }) {
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [result, setResult] = useState(null);
  const [chart, setChart] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.fareChart().then(setChart).catch(() => setChart([]));
  }, []);

  async function check(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      setResult(await api.fares(source, destination));
    } catch (err) {
      setResult(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const lowest = result?.options.length ? Math.min(...result.options.map((o) => o.fare)) : null;

  return (
    <div>
      <PageHeader title="Fares" description="Fares depend on the number of stops travelled and the type of bus. Check a trip, or browse the fare chart and all routes." />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Card className="lg:self-start">
          <CardHeader icon={Ticket} title="Fare between two stops" subtitle="Single-journey adult fares for every way to make the trip." />
          <form onSubmit={check} className="mt-5 grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
            <StopSelect label="From" icon={CircleDot} value={source} onChange={setSource} stops={stops} placeholder="Starting stop" />
            <StopSelect label="To" icon={MapPin} value={destination} onChange={setDestination} stops={stops} placeholder="Destination" />
            <Button type="submit" disabled={!source || !destination || source === destination || loading}>
              <Search className="h-4 w-4" aria-hidden />
              Check fare
            </Button>
          </form>
          <div className="mt-5 space-y-3">
            <ErrorNote message={error} />
            {loading && <Spinner label="Calculating fare..." />}
            {result && !loading && (
              <div className="rounded-xl border border-slate-200">
                <div className="border-b border-slate-100 bg-slate-50/70 px-4 py-2.5 text-sm font-medium text-slate-700">
                  {result.source} <span className="text-slate-400">→</span> {result.destination}
                </div>
                {result.options.length === 0 ? (
                  <Empty title="No connection">No direct or one-change bus connects these stops.</Empty>
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {result.options.map((o, i) => (
                      <li key={i} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-1.5">
                            {o.routes.map((r, j) => (
                              <span key={j} className="flex items-center gap-1.5">
                                {j > 0 && <ChevronRight className="h-3.5 w-3.5 text-slate-400" aria-hidden />}
                                <RouteBadge routeNo={r} busType={o.bus_types[j]} />
                              </span>
                            ))}
                            {o.fare === lowest && <Badge tone="green">Lowest fare</Badge>}
                          </div>
                          <div className="mt-1 text-xs text-slate-500">
                            {o.via.length > 0 ? `Change at ${o.via.join(", ")} · ` : "Direct · "}
                            {o.stops_travelled} stops
                          </div>
                        </div>
                        <span className="text-xl font-semibold tabular-nums text-slate-900">₹{o.fare}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader icon={MessageSquareText} title="Discounts and passes" />
            <p className="mt-3 text-sm text-slate-500">
              Students, senior citizens, children and passengers with disabilities may pay less, and monthly passes are available. Ask the
              assistant for the exact rules.
            </p>
            <div className="mt-4 space-y-2">
              {QUESTIONS.map(({ icon: Icon, label, question }) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => onAsk(question)}
                  className="flex w-full items-center gap-3 rounded-xl border border-slate-200 px-3 py-2.5 text-left text-sm font-medium text-slate-700 transition hover:border-blue-300 hover:bg-blue-50/40 hover:text-blue-800"
                >
                  <Icon className="h-4 w-4 text-slate-400" aria-hidden />
                  <span className="flex-1">{label}</span>
                  <ChevronRight className="h-4 w-4 text-slate-400" aria-hidden />
                </button>
              ))}
            </div>
          </Card>
          <Card>
            <CardHeader icon={Table2} title="Stage fare chart" subtitle="Fare by stops travelled (₹)" />
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-2 font-semibold">Stops</th>
                  {["Ordinary", "AC", "Night"].map((type) => (
                    <th key={type} className="py-2 pl-2 text-right font-semibold">
                      <Swatch busType={type} />
                      {type}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 tabular-nums text-slate-800">
                {chart.map((r) => (
                  <tr key={r.min_stops}>
                    <td className="py-2 pr-2 text-slate-600">
                      {r.min_stops}–{r.max_stops}
                    </td>
                    <td className="py-2 pl-2 text-right">₹{r.ordinary_fare}</td>
                    <td className="py-2 pl-2 text-right">₹{r.ac_fare}</td>
                    <td className="py-2 pl-2 text-right">₹{r.night_fare}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </div>

      <div className="mt-6">
        <Card padded={false} className="overflow-hidden">
          <div className="p-5 pb-4">
            <CardHeader icon={Layers} title="All routes" subtitle={`${routes.length} routes · full-route fares and weekday service hours`} />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-sm">
              <thead className="border-y border-slate-200 bg-slate-50/70 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="py-2.5 pl-5 pr-3 font-semibold">Route</th>
                  <th className="px-3 py-2.5 font-semibold">Type</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Stops</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Distance</th>
                  <th className="px-3 py-2.5 font-semibold">Hours</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Fare</th>
                  <th className="py-2.5 pl-3 pr-5" aria-label="Timetable" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {routes.map((r) => (
                  <tr key={r.route_no} className="hover:bg-slate-50/60">
                    <td className="py-3 pl-5 pr-3">
                      <div className="flex items-center gap-3">
                        <RouteBadge routeNo={r.route_no} busType={r.bus_type} />
                        <span className="min-w-[14rem] font-medium text-slate-800">{r.route_name}</span>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <BusTypeTag busType={r.bus_type} />
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">{r.stops.length}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{r.distance_km} km</td>
                    <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                      {r.first_departure}–{r.last_departure}
                    </td>
                    <td className="px-3 py-3 text-right font-semibold tabular-nums text-slate-900">₹{r.fare}</td>
                    <td className="py-3 pl-3 pr-5 text-right">
                      <Button variant="ghost" size="sm" onClick={() => onOpenTimetable(r.route_no)} aria-label={`Timetable for route ${r.route_no}`}>
                        <Clock3 className="h-4 w-4" aria-hidden />
                        Timetable
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
