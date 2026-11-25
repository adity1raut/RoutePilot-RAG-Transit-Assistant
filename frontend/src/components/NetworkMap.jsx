import "leaflet/dist/leaflet.css";
import { Fragment, useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { Clock3, Layers, MapPin, Search } from "lucide-react";
import { Badge, BusTypeTag, Button, Card, Empty, PageHeader, RouteBadge, Spinner, cx, inputClass } from "./ui";

// Line colours match the route badges (checked as a colour-blind safe set). Night lines are also
// dashed, so the bus type never depends on colour alone.
export const LINE_STYLES = {
  Ordinary: { color: "#2563eb" },
  AC: { color: "#0d9488" },
  Night: { color: "#6d28d9", dashArray: "6 8" },
};
const lineStyle = (busType) => LINE_STYLES[busType] || LINE_STYLES.Ordinary;
const MUTED = "#94a3b8";
const INK = "#0f172a";
const NANDED = [19.15, 77.305];

// Standard OpenStreetMap tiles (no API key); index.css mutes their colours so the routes stand out.
const TILES = {
  url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
};

// Fits the view to the given points whenever they change or the map container is resized.
// Panels stay mounted inside hidden tabs, so this also runs when a hidden map becomes visible.
function FitBounds({ points }) {
  const map = useMap();
  const key = JSON.stringify(points);
  useEffect(() => {
    const bounds = JSON.parse(key);
    const observer = new ResizeObserver(() => {
      map.invalidateSize();
      const size = map.getSize();
      if (bounds.length && size.x && size.y) map.fitBounds(bounds, { padding: [28, 28], maxZoom: 15 });
    });
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map, key]);
  return null;
}

function StopPopup({ stop, busTypes, onSelectRoute }) {
  return (
    <div className="min-w-[10rem] text-sm">
      <div className="font-semibold text-slate-900">{stop.name}</div>
      {stop.landmark && <div className="text-xs text-slate-500">{stop.landmark}</div>}
      <div className="mt-2 flex flex-wrap gap-1">
        {stop.routes.map((no) =>
          onSelectRoute ? (
            <button key={no} type="button" onClick={() => onSelectRoute(no)} title={`Show route ${no}`}>
              <RouteBadge routeNo={no} busType={busTypes[no]} />
            </button>
          ) : (
            <RouteBadge key={no} routeNo={no} busType={busTypes[no]} />
          ),
        )}
      </div>
      {stop.approximate && <div className="mt-2 text-[11px] text-slate-400">Approximate position</div>}
    </div>
  );
}

/**
 * Map of the bus network. With no `highlight` every route is drawn in its bus-type colour; otherwise the
 * highlighted paths (a route, or the legs of a journey: {route_no, bus_type, stops}) stand out over a muted network.
 */
export function TransitMap({ network, highlight = [], onSelectRoute, className = "" }) {
  const position = useMemo(() => Object.fromEntries(network.stops.map((s) => [s.name, [s.lat, s.lon]])), [network]);
  const busTypes = useMemo(() => Object.fromEntries(network.routes.map((r) => [r.route_no, r.bus_type])), [network]);
  const path = (stops) => stops.map((name) => position[name]).filter(Boolean);
  const focused = highlight.length > 0;
  const onPath = new Set(highlight.flatMap((h) => h.stops));
  const ends = new Set(highlight.flatMap((h) => [h.stops[0], h.stops.at(-1)]));
  // a single route gets every stop labelled; a journey with changes only its board, change and alight stops
  const labels = highlight.length === 1 ? onPath : ends;
  // put each label on the side away from its neighbours on the path, so labels do not cover each other
  const side = new Map();
  for (const h of highlight) {
    h.stops.forEach((s, i) => {
      const here = position[s];
      const dx = [h.stops[i - 1], h.stops[i + 1]]
        .map((n) => position[n])
        .filter(Boolean)
        .reduce((sum, p) => sum + p[1] - here[1], 0);
      if (here) side.set(s, dx > 0 ? "left" : "right");
    });
  }
  const points = focused ? highlight.flatMap((h) => path(h.stops)) : network.stops.map((s) => [s.lat, s.lon]);

  return (
    <MapContainer center={NANDED} zoom={13} zoomSnap={0.25} scrollWheelZoom={false} className={`isolate ${className}`}>
      <TileLayer {...TILES} />
      <FitBounds points={points} />
      {network.routes.map((r) => (
        <Polyline
          key={r.route_no}
          positions={path(r.stops)}
          pathOptions={
            focused
              ? { color: MUTED, weight: 2, opacity: 0.45, dashArray: lineStyle(r.bus_type).dashArray }
              : { ...lineStyle(r.bus_type), weight: 4, opacity: 0.8 }
          }
          eventHandlers={onSelectRoute ? { click: () => onSelectRoute(r.route_no) } : {}}
        >
          <Tooltip sticky>
            Route {r.route_no} · {r.route_name}
          </Tooltip>
        </Polyline>
      ))}
      {highlight.map((h, i) => (
        <Fragment key={`${h.route_no}-${i}`}>
          <Polyline positions={path(h.stops)} pathOptions={{ color: "#ffffff", weight: 9, opacity: 1 }} interactive={false} />
          <Polyline positions={path(h.stops)} pathOptions={{ ...lineStyle(h.bus_type), weight: 5, opacity: 1 }}>
            <Tooltip sticky>Route {h.route_no}</Tooltip>
          </Polyline>
        </Fragment>
      ))}
      {network.stops.map((s) => {
        const labelled = labels.has(s.name);
        const dimmed = focused && !onPath.has(s.name);
        const radius = ends.has(s.name) ? 7 : onPath.has(s.name) || (!focused && s.routes.length >= 3) ? 6 : 4;
        return (
          <CircleMarker
            key={`${s.name}-${labelled}-${side.get(s.name)}`}
            center={[s.lat, s.lon]}
            radius={radius}
            pathOptions={{ color: dimmed ? MUTED : INK, weight: dimmed ? 1 : 2, fillColor: "#ffffff", fillOpacity: 1 }}
          >
            <Tooltip
              permanent={labelled}
              direction={side.get(s.name) || "right"}
              offset={side.get(s.name) === "left" ? [-8, 0] : [8, 0]}
              className="stop-label"
            >
              {s.name}
            </Tooltip>
            <Popup>
              <StopPopup stop={s} busTypes={busTypes} onSelectRoute={onSelectRoute} />
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}

export function MapLegend({ children }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-100 px-4 py-2.5 text-xs text-slate-600">
      {Object.entries(LINE_STYLES).map(([type, style]) => (
        <span key={type} className="flex items-center gap-1.5">
          <svg width="24" height="6" aria-hidden>
            <line x1="0" y1="3" x2="24" y2="3" stroke={style.color} strokeWidth="3" strokeDasharray={style.dashArray ? "4 3" : undefined} />
          </svg>
          {type}
        </span>
      ))}
      <span className="flex items-center gap-1.5">
        <svg width="12" height="12" aria-hidden>
          <circle cx="6" cy="6" r="4" fill="#ffffff" stroke={INK} strokeWidth="2" />
        </svg>
        Bus stop
      </span>
      {children}
    </div>
  );
}

function RouteStops({ route }) {
  // minutes from the first stop, spread evenly over the journey time
  const offset = (i) => Math.round((route.duration_min * i) / (route.stops.length - 1));
  return (
    <ol className="relative ml-3 mt-3 border-l-2 border-slate-200 pb-1">
      {route.stops.map((s, i) => {
        const end = i === 0 || i === route.stops.length - 1;
        return (
          <li key={s} className="relative flex items-center justify-between gap-3 py-1 pl-4 text-sm">
            <span
              className={cx(
                "absolute -left-[7px] h-3 w-3 rounded-full border-2 border-white",
                end ? "bg-slate-900" : "bg-slate-300",
              )}
            />
            <span className={end ? "font-medium text-slate-900" : "text-slate-600"}>{s}</span>
            <span className="text-xs tabular-nums text-slate-400">+{offset(i)} min</span>
          </li>
        );
      })}
    </ol>
  );
}

export default function NetworkMap({ network, onOpenTimetable }) {
  const [selected, setSelected] = useState("");
  const [query, setQuery] = useState("");

  const header = (
    <PageHeader
      title="Network map"
      description="Every route and stop in the network. Pick a route to follow it, or click any line or stop on the map."
      actions={
        network?.stops.length > 0 && (
          <div className="flex gap-2">
            <Badge>{network.routes.length} routes</Badge>
            <Badge>{network.stops.length} stops</Badge>
          </div>
        )
      }
    />
  );
  if (!network) return (<>{header}<Spinner label="Loading map..." /></>);
  if (!network.stops.length)
    return (
      <>
        {header}
        <Card>
          {network.failed ? (
            <Empty icon={MapPin} title="Map data could not be loaded">Check that the RoutePilot backend is running, then reload the page.</Empty>
          ) : (
            <Empty icon={MapPin} title="No stop locations">Add data/raw/stops.csv to draw the network map.</Empty>
          )}
        </Card>
      </>
    );

  const route = network.routes.find((r) => r.route_no === selected);
  const approximate = network.stops.filter((s) => s.approximate).length;
  const q = query.trim().toLowerCase();
  const visible = network.routes.filter(
    (r) => !q || r.route_no.toLowerCase() === q || r.route_name.toLowerCase().includes(q) || r.stops.some((s) => s.toLowerCase().includes(q)),
  );

  return (
    <div>
      {header}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-card lg:sticky lg:top-8 lg:self-start">
          <TransitMap network={network} highlight={route ? [route] : []} onSelectRoute={setSelected} className="h-[26rem] lg:h-[calc(100dvh-13rem)] lg:min-h-[28rem]" />
          <MapLegend>
            <span className="text-slate-400">
              {approximate} of {network.stops.length} stop positions are approximate · lines join stops in order, not the exact roads
            </span>
          </MapLegend>
        </div>

        <Card padded={false} className="flex flex-col overflow-hidden">
          {route ? (
            <div className="p-5">
              <button type="button" onClick={() => setSelected("")} className="text-sm font-medium text-blue-700 hover:underline">
                ← All routes
              </button>
              <div className="mt-4 flex items-start gap-3">
                <RouteBadge routeNo={route.route_no} busType={route.bus_type} size="lg" />
                <div className="min-w-0">
                  <h2 className="font-semibold leading-snug text-slate-900">{route.route_name}</h2>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <BusTypeTag busType={route.bus_type} />
                    {route.distance_km} km · {route.duration_min} min · ₹{route.fare}
                  </div>
                </div>
              </div>
              <p className="mt-3 flex items-center gap-1.5 text-sm text-slate-600">
                <Clock3 className="h-4 w-4 text-slate-400" aria-hidden />
                Weekdays {route.first_departure}–{route.last_departure}
              </p>
              <RouteStops route={route} />
              {onOpenTimetable && (
                <Button variant="secondary" className="mt-4 w-full" onClick={() => onOpenTimetable(route.route_no)}>
                  <Clock3 className="h-4 w-4" aria-hidden />
                  Open full timetable
                </Button>
              )}
            </div>
          ) : (
            <>
              <div className="border-b border-slate-100 p-4">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Filter by route or stop"
                    aria-label="Filter routes by number, name or stop"
                    className={cx(inputClass, "h-10 pl-10 text-sm")}
                  />
                </div>
              </div>
              <ul className="flex-1 divide-y divide-slate-100 overflow-y-auto lg:max-h-[calc(100dvh-17rem)]">
                {visible.map((r) => (
                  <li key={r.route_no}>
                    <button
                      type="button"
                      onClick={() => setSelected(r.route_no)}
                      className="flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-slate-50"
                    >
                      <RouteBadge routeNo={r.route_no} busType={r.bus_type} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-slate-800">{r.route_name}</span>
                        <span className="mt-0.5 block text-xs text-slate-500">
                          {r.stops.length} stops · {r.distance_km} km · {r.first_departure}–{r.last_departure}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
                {visible.length === 0 && (
                  <li>
                    <Empty icon={Layers} title="No matching routes">Try a route number or a stop name.</Empty>
                  </li>
                )}
              </ul>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
