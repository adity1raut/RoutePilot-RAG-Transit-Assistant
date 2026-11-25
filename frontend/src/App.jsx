import { Clock3, Map as MapIcon, MessageSquareText, Navigation, Ticket } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api";
import ChatPanel from "./components/ChatPanel";
import FaresPanel from "./components/FaresPanel";
import NetworkMap from "./components/NetworkMap";
import RouteFinder from "./components/RouteFinder";
import TimetablePanel from "./components/TimetablePanel";
import { ErrorNote, Logo, cx } from "./components/ui";

const PAGES = [
  { id: "ask", label: "Assistant", short: "Ask", icon: MessageSquareText },
  { id: "route", label: "Route Finder", short: "Routes", icon: Navigation },
  { id: "map", label: "Network Map", short: "Map", icon: MapIcon },
  { id: "timetable", label: "Timetables", short: "Times", icon: Clock3 },
  { id: "fares", label: "Fares", short: "Fares", icon: Ticket },
];

const PROVIDER_LABEL = { anthropic: "Claude", gemini: "Gemini", openai: "OpenAI" };

const pageFromHash = () => {
  const id = window.location.hash.slice(1);
  return PAGES.some((p) => p.id === id) ? id : "ask";
};

function connection(health, error) {
  if (error) return { dot: "bg-red-500", label: "Backend offline" };
  if (!health) return { dot: "bg-slate-400 animate-pulse", label: "Connecting..." };
  if (health.provider === "none") return { dot: "bg-amber-400", label: "Offline answers" };
  return { dot: "bg-emerald-400", label: `${PROVIDER_LABEL[health.provider] || health.provider} connected` };
}

function StatusPanel({ health, error }) {
  const { dot, label } = connection(health, error);
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.04] p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-white">
        <span className={cx("h-2 w-2 rounded-full", dot)} />
        {label}
      </div>
      {health && (
        <>
          <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
            {[
              ["Routes", health.routes],
              ["Stops", health.stops],
              ["Chunks", health.chunks_indexed],
            ].map(([term, value]) => (
              <div key={term} className="rounded-lg bg-white/[0.04] py-1.5">
                <dd className="text-sm font-semibold tabular-nums text-white">{value}</dd>
                <dt className="text-[10px] uppercase tracking-wide text-slate-400">{term}</dt>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs leading-relaxed text-slate-400">
            {health.provider === "none"
              ? "No LLM key set: answers are built directly from the retrieved data."
              : `Answers by ${health.model}, grounded in ${health.chunks_indexed} indexed chunks.`}
          </p>
        </>
      )}
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState(pageFromHash);
  const [health, setHealth] = useState(null);
  const [stops, setStops] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [network, setNetwork] = useState(null);
  const [error, setError] = useState("");
  const [timetableRoute, setTimetableRoute] = useState("");
  const [question, setQuestion] = useState(null);

  useEffect(() => {
    Promise.all([api.health(), api.stops(), api.routes()])
      .then(([h, s, r]) => {
        setHealth(h);
        setStops(s);
        setRoutes(r);
      })
      .catch((err) => setError(`Cannot reach the RoutePilot backend (${err.message}). Start it with: uvicorn app.main:app --reload`));
    // loaded separately so the other pages still work if the map data cannot be fetched
    api.map().then(setNetwork).catch(() => setNetwork({ stops: [], routes: [], failed: true }));

    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // each page gets its own history entry, so the browser Back/Forward buttons move between pages
  const go = (id) => {
    if (window.location.hash !== `#${id}`) window.history.pushState(null, "", `#${id}`);
    setPage(id);
    window.scrollTo({ top: 0 });
  };
  const openTimetable = (routeNo) => {
    setTimetableRoute(routeNo);
    go("timetable");
  };
  const ask = (text) => {
    setQuestion({ text, at: Date.now() });
    go("ask");
  };

  const { dot, label } = connection(health, error);

  return (
    <div className="min-h-screen">
      {/* Sidebar (desktop) */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col bg-ink lg:flex">
        <div className="flex h-16 items-center gap-3 px-5">
          <Logo />
          <div>
            <div className="text-[15px] font-semibold leading-5 text-white">RoutePilot</div>
            <div className="text-xs text-slate-400">Nanded city bus assistant</div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-4" aria-label="Main">
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Menu</p>
          {PAGES.map((p) => {
            const active = page === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => go(p.id)}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition",
                  active ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-white",
                )}
              >
                <p.icon className={cx("h-[18px] w-[18px]", active ? "text-blue-400" : "")} aria-hidden />
                {p.label}
              </button>
            );
          })}
        </nav>
        <div className="space-y-3 p-3">
          <StatusPanel health={health} error={error} />
          <p className="px-2 text-[11px] leading-relaxed text-slate-500">Sample data for an academic project. Not an official timetable.</p>
        </div>
      </aside>

      {/* Top bar (mobile) */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur lg:hidden">
        <div className="flex items-center gap-2.5">
          <Logo className="h-8 w-8" />
          <span className="font-semibold text-slate-900">RoutePilot</span>
        </div>
        <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
          <span className={cx("h-1.5 w-1.5 rounded-full", dot)} />
          {label}
        </span>
      </header>

      <main className="lg:pl-64">
        <div className="mx-auto max-w-7xl px-4 pb-28 pt-6 sm:px-6 lg:px-10 lg:pb-10 lg:pt-8">
          {error && (
            <div className="mb-6">
              <ErrorNote message={error} />
            </div>
          )}
          {/* Pages stay mounted so the chat history and searches survive page switches */}
          <div hidden={page !== "ask"}>
            <ChatPanel question={question} />
          </div>
          <div hidden={page !== "route"}>
            <RouteFinder stops={stops} network={network} />
          </div>
          <div hidden={page !== "map"}>
            <NetworkMap network={network} onOpenTimetable={openTimetable} />
          </div>
          <div hidden={page !== "timetable"}>
            <TimetablePanel routes={routes} routeNo={timetableRoute} onRouteChange={setTimetableRoute} />
          </div>
          <div hidden={page !== "fares"}>
            <FaresPanel stops={stops} routes={routes} onOpenTimetable={openTimetable} onAsk={ask} />
          </div>
        </div>
      </main>

      {/* Bottom navigation (mobile) */}
      <nav
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
        aria-label="Main"
      >
        {PAGES.map((p) => {
          const active = page === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => go(p.id)}
              aria-current={active ? "page" : undefined}
              className={cx("flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium", active ? "text-blue-600" : "text-slate-500")}
            >
              <p.icon className="h-5 w-5" aria-hidden />
              {p.short}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
