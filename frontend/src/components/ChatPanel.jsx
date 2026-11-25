import { ArrowUp, Bot, CalendarDays, Clock3, Database, FileText, Megaphone, Navigation, SquarePen, Ticket, TicketCheck, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../api";
import { Badge, Button, Card, PageHeader, cx } from "./ui";

const EXAMPLES = [
  { icon: Navigation, category: "Plan a trip", text: "How do I go from CIDCO to SGGS Institute?" },
  { icon: Clock3, category: "Next bus", text: "When is the next bus from Railway Station to the Airport?" },
  { icon: CalendarDays, category: "Timetable", text: "Route 7N timings on Sunday" },
  { icon: Ticket, category: "Concessions", text: "What concessions do students get?" },
  { icon: TicketCheck, category: "Passes", text: "How much is a monthly pass?" },
  { icon: Megaphone, category: "Service notices", text: "Is Route 4 diverted this month?" },
];

const PROVIDER_LABEL = { anthropic: "Claude", gemini: "Gemini", openai: "OpenAI", none: "Offline mode" };

let nextId = 1;

// Turn "[S1]" and "[S1, S2]" citations into links so they can be rendered as clickable chips.
const linkCitations = (text) =>
  text.replace(/\[(S\d+(?:\s*,\s*S\d+)*)\]/g, (_, ids) =>
    ids
      .split(/\s*,\s*/)
      .map((id) => `[${id}](#cite-${id})`)
      .join(" "),
  );

const MAX_TURN_CHARS = 4000; // the backend rejects longer history turns

function Avatar() {
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-white shadow-sm">
      <Bot className="h-4 w-4" aria-hidden />
    </span>
  );
}

function SourceDetail({ source }) {
  const location = source.page ? `page ${source.page}` : source.row ? `row ${source.row}` : null;
  return (
    <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold text-slate-900">{source.title}</span>
        <span className="text-xs text-slate-500">
          {source.source}
          {location && ` · ${location}`}
        </span>
        {source.kind === "structured" ? (
          <Badge tone="green">Exact lookup</Badge>
        ) : (
          source.score != null && <Badge>{Math.round(source.score * 100)}% match</Badge>
        )}
      </div>
      <p className="mt-2 max-h-48 overflow-y-auto whitespace-pre-line text-xs leading-relaxed text-slate-600">{source.content}</p>
    </div>
  );
}

function AssistantMessage({ message }) {
  const [shown, setShown] = useState(null);
  const sources = message.sources || [];
  const toggle = (id) => setShown((current) => (current === id ? null : id));

  const components = {
    a: ({ href, children }) =>
      href?.startsWith("#cite-") ? (
        <button
          type="button"
          onClick={() => setShown(href.slice(6))}
          className="mx-0.5 rounded-md bg-blue-50 px-1.5 py-px align-baseline text-[11px] font-semibold text-blue-700 ring-1 ring-inset ring-blue-200 hover:bg-blue-100"
        >
          {children}
        </button>
      ) : (
        <a href={href} target="_blank" rel="noreferrer" className="text-blue-700 underline">
          {children}
        </a>
      ),
  };

  return (
    <div className="flex gap-3">
      <Avatar />
      <div className="min-w-0 max-w-3xl flex-1">
        <div className="mb-1 flex items-center gap-2 text-xs">
          <span className="font-semibold text-slate-800">RoutePilot</span>
          {message.provider && <span className="text-slate-400">{PROVIDER_LABEL[message.provider] || message.provider}</span>}
        </div>
        {message.warning && (
          <div className="mb-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <TriangleAlert className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
            {message.warning}
          </div>
        )}
        <div className={cx("markdown text-[15px] leading-relaxed", message.error ? "text-red-700" : "text-slate-700")}>
          <ReactMarkdown components={components}>{linkCitations(message.content)}</ReactMarkdown>
        </div>
        {sources.length > 0 && (
          <div className="mt-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-xs font-medium text-slate-500">Sources</span>
              {sources.map((s) => {
                const Icon = s.kind === "structured" ? Database : FileText;
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => toggle(s.id)}
                    aria-expanded={shown === s.id}
                    className={cx(
                      "inline-flex max-w-[16rem] items-center gap-1.5 rounded-lg border px-2 py-1 text-xs transition",
                      shown === s.id
                        ? "border-blue-300 bg-blue-50 text-blue-800"
                        : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900",
                    )}
                  >
                    <span className="font-semibold">{s.id}</span>
                    <Icon className="h-3 w-3 shrink-0" aria-hidden />
                    <span className="truncate">{s.kind === "structured" ? "Timetable lookup" : s.title}</span>
                  </button>
                );
              })}
            </div>
            {shown && sources.find((s) => s.id === shown) && <SourceDetail source={sources.find((s) => s.id === shown)} />}
          </div>
        )}
      </div>
    </div>
  );
}

function Typing() {
  return (
    <div className="flex items-center gap-3" role="status">
      <Avatar />
      <div className="flex items-center gap-3 rounded-2xl bg-slate-100 px-4 py-3">
        <span className="flex gap-1" aria-hidden>
          {[0, 150, 300].map((delay) => (
            <span key={delay} className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${delay}ms` }} />
          ))}
        </span>
        <span className="text-sm text-slate-500">Searching timetables and documents</span>
      </div>
    </div>
  );
}

export default function ChatPanel({ question }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: messages.length ? el.scrollHeight : 0, behavior: "smooth" });
  }, [messages, loading]);

  // questions sent from other pages ("Ask the assistant" buttons); while an answer is still
  // loading the question is put in the input box instead of being dropped
  useEffect(() => {
    if (!question) return;
    if (loading) setInput(question.text);
    else send(question.text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question]);

  async function send(text) {
    const q = text.trim();
    if (!q || loading) return;
    const history = messages
      .filter((m) => !m.error)
      .slice(-6)
      .map(({ role, content }) => ({ role, content: content.slice(0, MAX_TURN_CHARS) }));
    setMessages((m) => [...m, { id: `m${nextId++}`, role: "user", content: q }]);
    setInput("");
    setLoading(true);
    try {
      const res = await api.chat(q, history);
      setMessages((m) => [
        ...m,
        { id: `m${nextId++}`, role: "assistant", content: res.answer, sources: res.sources, provider: res.provider, warning: res.warning },
      ]);
    } catch (err) {
      setMessages((m) => [...m, { id: `m${nextId++}`, role: "assistant", content: `Sorry, something went wrong: ${err.message}`, error: true }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-[calc(100dvh-12rem)] min-h-[32rem] flex-col lg:h-[calc(100dvh-4.5rem)]">
      <PageHeader
        title="Ask RoutePilot"
        description="Questions about routes, timings, fares and service notices, answered from the transport data with cited sources."
        actions={
          messages.length > 0 && (
            <Button variant="secondary" size="sm" onClick={() => setMessages([])} disabled={loading}>
              <SquarePen className="h-4 w-4" aria-hidden />
              New chat
            </Button>
          )
        }
      />
      <Card padded={false} className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8">
          {messages.length === 0 ? (
            <div className="mx-auto flex max-w-3xl flex-col items-center py-4 text-center">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-blue-700 text-white shadow-lg shadow-blue-600/20">
                <Bot className="h-7 w-7" aria-hidden />
              </span>
              <h2 className="mt-5 text-xl font-semibold text-slate-900">Where would you like to go?</h2>
              <p className="mt-2 max-w-lg text-sm text-slate-500">
                Ask in your own words. Every answer cites the timetable rows and documents it was built from.
              </p>
              <div className="mt-8 grid w-full gap-3 text-left sm:grid-cols-2 xl:grid-cols-3">
                {EXAMPLES.map(({ icon: Icon, category, text }) => (
                  <button
                    key={text}
                    type="button"
                    onClick={() => send(text)}
                    className="group flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-lift"
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition group-hover:bg-blue-50 group-hover:text-blue-600">
                      <Icon className="h-[18px] w-[18px]" aria-hidden />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">{category}</span>
                      <span className="mt-0.5 block text-sm font-medium text-slate-800">{text}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-6">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-2xl rounded-br-md bg-blue-600 px-4 py-2.5 text-[15px] text-white shadow-sm">{m.content}</div>
                  </div>
                ) : (
                  <AssistantMessage key={m.id} message={m} />
                ),
              )}
              {loading && <Typing />}
            </div>
          )}
        </div>
        <div className="border-t border-slate-200 bg-slate-50/70 px-4 py-3 sm:px-8 sm:py-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="relative mx-auto max-w-3xl"
          >
            <label htmlFor="chat-input" className="sr-only">
              Your question
            </label>
            <input
              id="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={500}
              autoComplete="off"
              placeholder="Ask about a route, a bus time or a fare..."
              className="h-12 w-full rounded-xl border border-slate-300 bg-white pl-4 pr-14 text-[15px] text-slate-900 shadow-sm transition placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-500/15"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              aria-label="Send question"
              className="absolute right-1.5 top-1.5 flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white transition hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-400"
            >
              <ArrowUp className="h-4 w-4" aria-hidden />
            </button>
          </form>
          <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-slate-400">
            Answers use sample transport data. Check official notices before you travel.
          </p>
        </div>
      </Card>
    </div>
  );
}
