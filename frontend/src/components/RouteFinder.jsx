import { ArrowLeftRight, ArrowRight, ChevronRight, CircleDot, Clock3, MapPin, Navigation, Repeat, Search } from "lucide-react";
import { Fragment, useRef, useState } from "react";
import { api, formatMinutes, todayDayType } from "../api";
import { LINE_STYLES, MapLegend, TransitMap } from "./NetworkMap";
import { Badge, Button, Card, CardHeader, DaySelect, Empty, ErrorNote, PageHeader, RouteBadge, Spinner, StopSelect, cx } from "./ui";

const POPULAR = [
  ["CIDCO", "SGGS Institute"],
  ["Railway Station", "Airport"],
  ["Vazirabad", "Airport"],
  ["Itwara Market", "SRTM University"],
  ["Central Bus Stand", "Degloor Naka"],
];

const stopCount = (n) => `${n} stop${n === 1 ? "" : "s"}`;

function OptionCard({ journey, index, selected, onSelect }) {
  const first = journey.legs[0];
  const stops = journey.legs.reduce((sum, leg) => sum + leg.stops_travelled, 0);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cx(
        "w-full rounded-2xl border bg-white p-4 text-left shadow-card transition",
        selected ? "border-blue-500 ring-4 ring-blue-500/10" : "border-slate-200/80 hover:border-slate-300 hover:shadow-lift",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl font-semibold tabular-nums text-slate-900">{formatMinutes(journey.travel_min)}</span>
            {index === 0 && <Badge tone="green">Best option</Badge>}
          </div>
          <div className="mt-0.5 text-sm text-slate-500">
            {journey.transfers ? `${journey.transfers} change` : "Direct"} · {stopCount(stops)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xl font-semibold tabular-nums text-slate-900">₹{journey.fare}</div>
          <div className="text-xs text-slate-500">full fare</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-sm text-slate-600">
        {journey.legs.map((leg, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-slate-400" aria-hidden />}
            <RouteBadge routeNo={leg.route_no} busType={leg.bus_type} size="sm" />
          </span>
        ))}
        {journey.transfers > 0 && <span className="ml-1 truncate text-xs text-slate-500">change at {journey.legs[1].board}</span>}
      </div>
      <div className="mt-3 flex items-center gap-1.5 border-t border-slate-100 pt-3 text-xs text-slate-500">
        <Clock3 className="h-3.5 w-3.5" aria-hidden />
        {journey.next_departures.length > 0 ? (
          <span>
            Next from {first.board}: <span className="font-semibold tabular-nums text-slate-800">{journey.next_departures.join(" · ")}</span>
          </span>
        ) : (
          <span>
            First bus <span className="font-semibold tabular-nums text-slate-800">{first.departures[0]}</span>, last{" "}
            <span className="font-semibold tabular-nums text-slate-800">{first.departures.at(-1)}</span>
          </span>
        )}
      </div>
    </button>
  );
}

function StopRow({ icon: Icon, tone, title, children }) {
  return (
    <li className="relative flex gap-3 pb-1">
      <span className={cx("relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ring-4 ring-white", tone)}>
        <Icon className="h-3.5 w-3.5" aria-hidden />
      </span>
      <div className="min-w-0 pt-0.5">
        <div className="font-semibold text-slate-900">{title}</div>
        {children && <div className="text-sm text-slate-500">{children}</div>}
      </div>
    </li>
  );
}

function RideRow({ leg }) {
  const style = LINE_STYLES[leg.bus_type] || LINE_STYLES.Ordinary;
  const between = leg.stops.slice(1, -1);
  return (
    <li className="flex gap-3">
      <span className="flex w-7 shrink-0 justify-center">
        <span
          className={style.dashArray ? "w-0 border-l-4 border-dashed" : "w-1 rounded-full"}
          style={style.dashArray ? { borderColor: style.color } : { background: style.color }}
        />
      </span>
      <div className="min-w-0 flex-1 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <RouteBadge routeNo={leg.route_no} busType={leg.bus_type} />
          <span className="text-sm font-medium text-slate-800">{leg.route_name}</span>
        </div>
        <div className="mt-1 text-sm text-slate-500">
          {leg.direction} direction · {stopCount(leg.stops_travelled)} · ~{leg.travel_min} min · ₹{leg.fare}
        </div>
        <div className="mt-1 text-xs text-slate-500">
          Buses from {leg.board}: first <span className="font-medium tabular-nums text-slate-700">{leg.departures[0]}</span>, last{" "}
          <span className="font-medium tabular-nums text-slate-700">{leg.departures.at(-1)}</span>
        </div>
        {between.length > 0 && (
          <details className="group mt-2">
            <summary className="cursor-pointer list-none text-xs font-medium text-blue-700 hover:underline">
              <span className="group-open:hidden">Show {stopCount(between.length)} in between</span>
              <span className="hidden group-open:inline">Hide stops in between</span>
            </summary>
            <ol className="mt-2 space-y-1 text-sm text-slate-600">
              {between.map((s) => (
                <li key={s} className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
                  {s}
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
    </li>
  );
}

function JourneyDetail({ journey, index, dayType }) {
  const last = journey.legs.at(-1);
  return (
    <Card>
      <CardHeader
        icon={Navigation}
        title={`Option ${index + 1}: step by step`}
        subtitle={`${dayType} timetable · ${formatMinutes(journey.travel_min)} · ₹${journey.fare}`}
      />
      <ol className="mt-5">
        {journey.legs.map((leg, i) => (
          <Fragment key={i}>
            {i === 0 ? (
              <StopRow icon={CircleDot} tone="bg-blue-600 text-white" title={leg.board}>
                Board Route {leg.route_no}
                {journey.next_departures.length > 0 && ` · next at ${journey.next_departures[0]}`}
              </StopRow>
            ) : (
              <StopRow icon={Repeat} tone="bg-amber-100 text-amber-700" title={`Change at ${leg.board}`}>
                Get off Route {journey.legs[i - 1].route_no}, board Route {leg.route_no}
              </StopRow>
            )}
            <RideRow leg={leg} />
          </Fragment>
        ))}
        <StopRow icon={MapPin} tone="bg-slate-900 text-white" title={last.alight}>
          Arrive after about {formatMinutes(journey.travel_min)} on the bus
        </StopRow>
      </ol>
    </Card>
  );
}

export default function RouteFinder({ stops, network }) {
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [dayType, setDayType] = useState(todayDayType());
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  // the newest search wins: a slower earlier response must not replace a newer one
  async function search(from = source, to = destination, day = dayType) {
    const id = ++latest.current;
    setSource(from);
    setDestination(to);
    setError("");
    setLoading(true);
    try {
      const found = await api.journeys(from, to, day);
      if (id !== latest.current) return;
      setSelected(0);
      setResult(found);
    } catch (err) {
      if (id !== latest.current) return;
      setResult(null);
      setError(err.message);
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }

  // keep shown results in step with the chosen day
  function changeDay(day) {
    setDayType(day);
    if (result && source && destination && source !== destination) search(source, destination, day);
  }

  const hasMap = network?.stops.length > 0;
  const journey = result?.journeys[selected];

  return (
    <div>
      <PageHeader title="Route finder" description="Direct buses and one-change journeys between any two stops, with fares and the next departures." />
      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            search();
          }}
          className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_minmax(0,21rem)_auto] lg:items-end"
        >
          <StopSelect label="From" icon={CircleDot} value={source} onChange={setSource} stops={stops} placeholder="Starting stop" />
          <button
            type="button"
            onClick={() => {
              setSource(destination);
              setDestination(source);
            }}
            className="flex h-11 w-11 items-center justify-center self-end justify-self-center rounded-full border border-slate-300 bg-white text-slate-500 shadow-sm transition hover:bg-slate-50 hover:text-slate-900"
            title="Swap"
            aria-label="Swap starting stop and destination"
          >
            <ArrowLeftRight className="h-4 w-4 rotate-90 lg:rotate-0" aria-hidden />
          </button>
          <StopSelect label="To" icon={MapPin} value={destination} onChange={setDestination} stops={stops} placeholder="Destination" />
          <DaySelect value={dayType} onChange={changeDay} />
          <Button type="submit" disabled={!source || !destination || source === destination || loading}>
            <Search className="h-4 w-4" aria-hidden />
            Find routes
          </Button>
        </form>
        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
          <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Popular</span>
          {POPULAR.map(([from, to]) => (
            <button
              key={`${from}-${to}`}
              type="button"
              onClick={() => search(from, to)}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600 transition hover:border-blue-300 hover:text-blue-700"
            >
              {from}
              <ArrowRight className="h-3.5 w-3.5 text-slate-400" aria-hidden />
              {to}
            </button>
          ))}
        </div>
      </Card>

      <div className="mt-6 space-y-4">
        <ErrorNote message={error} />
        {loading && <Spinner label="Finding routes..." />}
        {!result && !loading && !error && (
          <Card>
            <Empty icon={Navigation} title="Plan a journey">
              Choose where you start and where you are going, or pick one of the popular trips above.
            </Empty>
          </Card>
        )}
        {result && !loading && (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-semibold text-slate-900">
                {result.source} <span className="text-slate-400">→</span> {result.destination}
              </h2>
              <span className="text-sm text-slate-500">
                {result.journeys.length} option{result.journeys.length === 1 ? "" : "s"} · {result.day_type} timetable
              </span>
            </div>
            {result.journeys.length === 0 ? (
              <Card>
                <Empty title="No connection found">No direct or one-change bus service connects these stops on this day.</Empty>
              </Card>
            ) : (
              <div className="grid gap-6 lg:grid-cols-[minmax(0,23rem)_minmax(0,1fr)]">
                <div className="space-y-3">
                  {result.journeys.map((j, i) => (
                    <OptionCard key={i} journey={j} index={i} selected={i === selected} onSelect={() => setSelected(i)} />
                  ))}
                </div>
                <div className="space-y-4">
                  {hasMap && (
                    <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-card">
                      <TransitMap network={network} highlight={journey.legs} className="h-72 md:h-[22rem]" />
                      <MapLegend />
                    </div>
                  )}
                  <JourneyDetail journey={journey} index={selected} dayType={result.day_type} />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
