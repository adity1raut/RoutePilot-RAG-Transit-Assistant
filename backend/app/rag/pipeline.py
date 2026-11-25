"""Steps 6-9 of the pipeline: query -> similarity search -> retrieved context -> LLM -> answer + sources."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import Settings
from app.rag.llm import describe_llm_error, get_llm
from app.rag.vectorstore import VectorStore
from app.services.transport import StructuredResult, TransportData, detect_day_type

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are RoutePilot, a friendly public transport information assistant.
Answer the passenger's question using ONLY the numbered context sources provided.

Rules:
- Cite the sources you use in square brackets right after the facts they support, e.g. [S1] or [S2][S3].
- For journeys give the route number, direction, where to board and get off, any change of bus, fare and timings.
- Keep answers short and scannable: use bullet points for options and timings, bold the route numbers.
- If the context does not contain the answer, say that you do not have that information and suggest the
  passenger contact the transport helpline. Never invent routes, stops, timings or fares.
- Fares are in Indian Rupees; write them as Rs.
- Current date and time: {now} ({day_type})."""

USER_PROMPT = "Context sources:\n\n{context}\n\nPassenger question: {question}"

# "and on Sunday?", "what about the fare?", "when is the next one?" refer back to the previous question
FOLLOW_UP = re.compile(r"^\s*(and|what about|how about|also|then|same)\b|\b(it|that|there|same|next|return|back|"
                       r"the (fare|fares|bus|buses|route|ticket|timing|timings|schedule))\b", re.I)

MIN_DOC_SCORE = 0.15  # chunks below this relevance are ignored by the no-LLM fallback answer
MIN_SENTENCE_SCORE = 0.4  # sentences must be at least this similar to the question to be quoted


@dataclass
class Source:
    id: str
    kind: str  # "structured" (exact lookup over routes.csv) or "document" (retrieved chunk)
    source: str
    title: str
    content: str
    page: int | None = None
    row: int | None = None
    score: float | None = None

    @property
    def label(self) -> str:
        where = f", page {self.page}" if self.page else f", row {self.row}" if self.row else ""
        return f"{self.title} ({self.source}{where})"


class RAGPipeline:
    def __init__(self, settings: Settings, transport: TransportData, store: VectorStore):
        self.settings = settings
        self.transport = transport
        self.store = store
        self.llm = get_llm(settings)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("history"),
            ("human", USER_PROMPT),
        ])
        self.chain = (self.prompt | self.llm | StrOutputParser()) if self.llm else None

    @property
    def provider(self) -> str:
        return self.settings.resolved_provider if self.llm else "none"

    # ---------------------------------------------------------------- retrieval
    def retrieve(self, question: str, history: list[dict], k: int, now: datetime) -> tuple[StructuredResult, list[Source]]:
        structured = self.transport.analyse(question, now)
        search_query = question
        # Follow-up questions ("and on Sunday?") inherit stops/route from the previous user question.
        previous = next((h["content"] for h in reversed(history) if h["role"] == "user"), None)
        is_follow_up = bool(FOLLOW_UP.search(question) or detect_day_type(question))
        if previous and is_follow_up and not structured.stops and not structured.route_no:
            combined = f"{previous} {question}"
            candidate = self.transport.analyse(combined, now)
            if candidate.found:
                structured, search_query = candidate, combined

        sources: list[Source] = []
        if structured.found:
            sources.append(Source(id="S1", kind="structured", source="routes.csv",
                                  title="Route, timetable and fare lookup", content=structured.facts))
        for doc, score in self.store.search(search_query, k):
            meta = doc.metadata
            sources.append(Source(
                id=f"S{len(sources) + 1}", kind="document", source=meta.get("source", "unknown"),
                title=meta.get("title", meta.get("source", "Document")), content=doc.page_content,
                page=meta.get("page"), row=meta.get("row"), score=round(float(score), 3),
            ))
        return structured, sources

    # ---------------------------------------------------------------- generation
    def answer(self, question: str, history: list[dict] | None = None, top_k: int | None = None,
               now: datetime | None = None) -> dict:
        now = now or datetime.now()
        history = (history or [])[-6:]
        structured, sources = self.retrieve(question, history, top_k or self.settings.top_k, now)

        warning = None
        provider = self.provider
        if self.chain:
            context = "\n\n".join(f"[{s.id}] {s.label}\n{s.content}" for s in sources) or "(no relevant information found)"
            try:
                answer = self.chain.invoke({
                    "context": context,
                    "question": question,
                    "history": [(h["role"] if h["role"] == "user" else "ai", h["content"]) for h in history],
                    "now": now.strftime("%A %d %B %Y, %H:%M"),
                    "day_type": structured.day_type,
                })
            except Exception as exc:  # network error, quota, invalid key...
                log.exception("LLM call failed, falling back to extractive answer")
                warning = f"{describe_llm_error(provider, exc)} Showing the retrieved information instead."
                answer, provider = self.extractive_answer(question, structured, sources), "none"
        else:
            answer = self.extractive_answer(question, structured, sources)

        return {
            "answer": answer.strip(),
            "sources": [asdict(s) for s in sources],
            "intent": structured.intent,
            "day_type": structured.day_type,
            "stops": structured.stops,
            "route_no": structured.route_no,
            "provider": provider,
            "warning": warning,
            "data": structured.data,
        }

    def extractive_answer(self, question: str, structured: StructuredResult, sources: list[Source]) -> str:
        """Answer without an LLM: exact lookup results plus the most relevant sentences from the documents."""
        parts: list[str] = []
        if structured.found:
            parts.append(self._format_structured(structured))

        docs = [s for s in sources if s.kind == "document" and (s.score or 0) >= MIN_DOC_SCORE]
        if structured.found:
            # timetable rows are already covered by the exact lookup; keep policy/guide text only
            docs = [s for s in docs if s.source != "routes.csv" and (s.score or 0) >= MIN_DOC_SCORE + 0.1]
        sentences = self._best_sentences(question, docs, limit=2 if structured.found else 3)
        if sentences:
            title = "From the transport documents:" if structured.found else ""
            parts.append((title + "\n" if title else "") + "\n".join(f"- {text} [{sid}]" for sid, text in sentences))

        if not parts:
            return ("I could not find information about that in the transport data. Please rephrase your "
                    "question with stop names or a route number, or contact the transport helpline.")
        return "\n\n".join(parts)

    @staticmethod
    def _format_structured(structured: StructuredResult) -> str:
        data = structured.data
        if journeys := data.get("journeys"):
            first, last = journeys[0]["legs"][0]["board"], journeys[0]["legs"][-1]["alight"]
            lines = [f"**{first} to {last}** ({structured.day_type} timetable) [S1]:"]
            for n, j in enumerate(journeys, 1):
                legs = " then ".join(
                    f"**Route {leg['route_no']}** ({leg['bus_type']}) {leg['board']} to {leg['alight']}" for leg in j["legs"])
                lines.append(f"{n}. {legs}: {j['travel_min']} min, fare Rs. {j['fare']}")
                deps = j["legs"][0]["departures"]
                timing = (f"next buses {', '.join(j['next_departures'])}" if j["next_departures"]
                          else f"first bus {deps[0]}, last bus {deps[-1]}")
                lines.append(f"   - {timing}")
            return "\n".join(lines)
        if table := data.get("timetable"):
            lines = []
            for t in table:
                lines.append(f"**Route {t['route_no']}** {t['source']} to {t['destination']} ({t['day_type']}, "
                             f"{t['bus_type']}): every {t['frequency_min']} min, {t['first_departure']} to "
                             f"{t['last_departure']}, fare Rs. {t['fare']} [S1]")
            return "\n".join(f"- {line}" for line in lines)
        return "\n".join(f"- {line}" for line in structured.facts.splitlines()) + " [S1]"

    def _best_sentences(self, question: str, docs: list[Source], limit: int) -> list[tuple[str, str]]:
        candidates = []
        for doc in docs:
            for sentence in re.split(r"(?<=[.!?])\s+|\n", doc.content):
                sentence = sentence.strip()
                if len(sentence.split()) >= 5 and sentence[-1] in ".!?":  # skip headings and fragments
                    candidates.append((doc.id, sentence))
        if not candidates:
            return []
        embed = self.store.embeddings
        q = np.array(embed.embed_query(question))
        scores = np.array(embed.embed_documents([text for _, text in candidates])) @ q
        best = [i for i in np.argsort(scores)[::-1][:limit] if scores[i] >= MIN_SENTENCE_SCORE]
        return [candidates[i] for i in sorted(best)]
