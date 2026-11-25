# RoutePilot: Public Transport Information Assistant (RAG)

RoutePilot answers natural-language questions about public transport (routes, bus stops, timetables, fares and services) using **Retrieval-Augmented Generation**. Every answer cites the documents or data rows it was generated from.

Mini-project by the RoutePilot group: Atharva Vilas Karegaonkar (2023BCS054), Aditya Waman Raut (2023BCS015), Nagnath Vishwanath Avhad (2023BCS019), Chandrashekhar Patil (2023BCS085) and Amit Shubhkaran Varma (2023BCS126).

## Features (from the SRS)

| SRS feature | Where it is implemented |
|---|---|
| 1. Transport Q&A | **Assistant** page → `POST /api/chat` → [`app/rag/pipeline.py`](backend/app/rag/pipeline.py) |
| 2. Route Information | **Route Finder** page → `GET /api/journeys` (direct and one-change journeys, each shown on a map) |
| Network map | **Network Map** page → `GET /api/map`: every route and stop on an OpenStreetMap map; click a route or stop to focus it |
| 3. Timetable Search | **Timetables** page → `GET /api/routes/{route}/timetable` |
| 4. Fare Information | **Fares** page → `GET /api/fares`, `GET /api/fare-chart` |
| 5. Source Citation | Every chat answer has `[S1]`-style citations and a list of sources with file, page/row and relevance score |

## Technology stack

| Layer | Used |
|---|---|
| Frontend | React 18, Tailwind CSS, Vite, Leaflet (`react-leaflet`) with OpenStreetMap tiles, Lucide icons |
| Backend | Python 3.11, FastAPI |
| RAG | LangChain (`langchain-core`, text splitters, Chroma and HuggingFace integrations) |
| Data processing | Pandas, PyMuPDF |
| Embeddings | Sentence Transformers (`all-MiniLM-L6-v2`) |
| Vector database | ChromaDB (persistent, cosine similarity) |
| LLM | **Claude** (Claude Opus 5.5 through the official Anthropic SDK), with Google Gemini or OpenAI as alternatives. The provider is selected automatically from the API key in `.env` |

MongoDB (optional in the SRS) is not used. Chat history is kept in the browser and sent with each request.

## How it works

```
Transport data (CSV + PDFs)
   → Text extraction (Pandas for CSV rows, PyMuPDF for PDF text and tables)
   → Cleaning (Unicode normalisation, re-flowing wrapped lines, removing running headers and page numbers)
   → Chunking (RecursiveCharacterTextSplitter, 500 chars, 80 overlap; one chunk per timetable row)
   → Embeddings (Sentence Transformers)
   → ChromaDB

User query
   → Query embedding → similarity search in ChromaDB (top-k chunks)
   + exact lookup over routes.csv (stops, route numbers and day type detected in the question)
   → Retrieved context [S1..Sn] + question → LangChain prompt → LLM (Claude, or Gemini/OpenAI)
   → Answer with source citations
```

This is the algorithm from the SRS, plus one addition: a **structured lookup** ([`app/services/transport.py`](backend/app/services/transport.py)). Semantic search is good at "what concessions do students get?" but unreliable for exact questions like "which bus goes from CIDCO to SGGS Institute and when is the next one?". So the question is also parsed for stop names (it tolerates typos and aliases such as "bus stand" or "sggs"), route numbers and day type. The exact route, timetable and fare facts go into the LLM context as source `[S1]`. The LLM is told to answer only from the context and to cite it.

**The LLM.** With `ANTHROPIC_API_KEY` set, answers come from Claude Opus 5.5 via the official `anthropic` SDK ([`app/rag/llm.py`](backend/app/rag/llm.py)). `ANTHROPIC_EFFORT` (default `medium`) controls how much it thinks before answering. If Claude's safety filter declines a request, Anthropic's server-side fallback retries it on another model.

**No API key? It still works.** Without an LLM key, RoutePilot runs in *offline mode*. It returns the exact lookup results plus the sentences from the retrieved documents that are most similar to the question (ranked with the same embedding model), with citations. If an LLM call fails (network, quota), the answer falls back to the same mode and the UI shows a warning.

## Project structure

```
RoutePilot/
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI app and REST endpoints (also serves the built frontend)
│   │   ├── config.py             Settings loaded from .env
│   │   ├── schemas.py            Request/response models
│   │   ├── services/transport.py Stop matching, route finder (direct + 1 change), timetables, fares
│   │   └── rag/
│   │       ├── preprocess.py     Data collection, extraction, cleaning, chunking
│   │       ├── vectorstore.py    Embeddings, ChromaDB storage and similarity search
│   │       ├── llm.py            Claude (Anthropic SDK), Gemini or OpenAI; friendly error messages
│   │       └── pipeline.py       Retrieval, prompt, generation, citations, offline fallback
│   ├── data/raw/                 Transport data: routes.csv, stops.csv, fare_chart.csv, docs/*.pdf
│   ├── data/chroma/              Vector database (generated, not committed)
│   ├── scripts/
│   │   ├── generate_sample_data.py  Creates the sample dataset and PDFs
│   │   └── ingest.py                Runs the ingestion pipeline
│   ├── tests/                    pytest suite (38 tests)
│   ├── requirements.txt
│   └── .env.example
├── frontend/                     React + Tailwind UI (Assistant, Route Finder, Network Map, Timetables, Fares)
└── run.sh                        One-command start
```

## Setup

Requirements: Python 3.10 or newer, Node.js 18 or newer.

```bash
# 1. Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU-only torch, much smaller download
pip install -r requirements.txt

cp .env.example .env        # then put your ANTHROPIC_API_KEY (or a Gemini/OpenAI key) in .env
python -m scripts.ingest    # builds the ChromaDB index (also done automatically on first start)

# 2. Frontend
cd ../frontend
npm install
npm run build
```

Get a Claude API key at https://platform.claude.com (it starts with `sk-ant-`). Gemini (https://aistudio.google.com/apikey) and OpenAI keys also work, and so does any OpenAI-compatible API (for example Groq's free tier) through `OPENAI_BASE_URL`. With `LLM_PROVIDER=auto`, Claude is used if its key is set, then Gemini, then OpenAI. Never commit `.env`; it is already in `.gitignore`.

## Running

**One command** (serves the API and the built UI together on http://localhost:8000):

```bash
./run.sh
```

**Development mode** (frontend hot reload on http://localhost:5173, with `/api` proxied to the backend):

```bash
# terminal 1
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
# terminal 2
cd frontend && npm run dev
```

Interactive API docs (Swagger UI): http://localhost:8000/docs

## Example questions

- How do I go from CIDCO to SGGS Institute?
- When is the next bus from Railway Station to the Airport?
- Which bus goes from Vazirabad to the Airport on Sunday? *(needs a change of bus)*
- Route 7N timings on Sunday
- What is the fare from Railway Station to Shivaji Nagar for a senior citizen?
- What concessions do students get? / How much is a monthly pass?
- Is Route 4 diverted this month? *(answered from the service notices PDF)*
- Where is the lost and found office?
- Which buses stop at Kautha? / Bus from Railway Station to Waghala
- Follow-ups work: ask "bus from Railway Station to Airport", then "and on Sunday?"

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Status, LLM provider and model, number of indexed chunks |
| POST | `/api/chat` | `{"question": "...", "history": [...]}` → answer, sources, detected intent/stops/day type |
| GET | `/api/stops` | All bus stops |
| GET | `/api/routes` | Route summaries |
| GET | `/api/map` | Stops with coordinates and landmarks, plus every route's stop sequence (for the map) |
| GET | `/api/routes/{route_no}/timetable?day_type=&direction=` | Timetable (`Weekday`, `Saturday`, `Sunday/Holiday`; `Up`/`Down`) |
| GET | `/api/journeys?source=&destination=&day_type=` | Direct or one-change journeys with fares and next departures |
| GET | `/api/fares?source=&destination=` | Fare options between two stops |
| GET | `/api/fare-chart` | Stage fare chart |
| POST | `/api/ingest` | Re-run the ingestion pipeline after changing `data/raw` |

## Dataset

The SRS calls for structured transport data (route number, source, destination, bus stops, timings, fare, day type) plus transport PDF documents. **The included dataset is synthetic sample data made for this demo.** It is not an official timetable. It uses stop names around Nanded, and `scripts/generate_sample_data.py` generates it:

- `routes.csv`: 13 routes × 2 directions × 3 day types = 78 timetable rows, covering the old city, the north (Taroda Naka, Malegaon Road, Sangvi, Airport), the west (Wadi Bk) and the south bank of the Godavari (Kautha, CIDCO, Hadco, Waghala, Vishnupuri, SGGS, SRTM University). Includes two AC routes (Airport Express, University Express) and a Night service that runs past midnight
- `stops.csv`: the 30 stops with latitude/longitude, a landmark and the routes serving them. 15 positions come from OpenStreetMap; the others are approximate (OpenStreetMap has no point for those localities) and are flagged as such in the file and on the map. The map joins stops with straight lines in route order; it does not follow the exact roads
- `fare_chart.csv`: stage fares by number of stops travelled and bus type
- `docs/fare_policy_and_concessions.pdf`, `docs/passenger_guide.pdf`, `docs/service_notices_oct_2026.pdf`

**To use real data:** replace or add files in `backend/data/raw/` and run `python -m scripts.ingest` (or `POST /api/ingest`). Any PDF, TXT or MD file is indexed. Other CSV files are indexed row by row. The route finder needs a `routes.csv` with the same columns as the sample. The map needs a `stops.csv` with `stop_name`, `latitude` and `longitude` columns (`landmark`, `position` and `routes` are optional); without it the other tabs still work.

## Tests

```bash
cd backend && source .venv/bin/activate && pytest
```

The tests cover stop matching (including typos and aliases), the route finder (direct, return direction, one change, night services after midnight), the map data (every stop has a position inside Nanded), fares, PDF table extraction, chunking, every API endpoint, follow-up questions, the LLM path, and the Claude request format, refusal handling and error messages. The tests use fake LLM clients, so they need no API key and make no network calls.
