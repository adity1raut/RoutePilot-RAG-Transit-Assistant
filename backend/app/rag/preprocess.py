"""Steps 1-3 of the pipeline: data collection -> text extraction -> cleaning -> chunking."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf
import pandas as pd
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

SUPPORTED = {".pdf", ".csv", ".txt", ".md"}


# ---------------------------------------------------------------- cleaning
def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated across lines
    text = re.sub(r"[^\S\n]+", " ", text)  # collapse spaces/tabs, keep newlines
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_repeated_lines(pages: list[str]) -> list[str]:
    """Remove running headers/footers: lines repeated on most pages, and page numbers."""
    if len(pages) > 1:
        counts = Counter(line.strip() for page in pages for line in set(page.splitlines()) if line.strip())
        repeated = {line for line, n in counts.items() if n >= max(2, len(pages) * 0.6)}
    else:
        repeated = set()
    cleaned = []
    for page in pages:
        lines = [ln for ln in page.splitlines()
                 if ln.strip() not in repeated and not re.fullmatch(r"\s*page \d+( of \d+)?\s*", ln, re.I)]
        cleaned.append("\n".join(lines))
    return cleaned


# ---------------------------------------------------------------- extraction
def _page_text(page: pymupdf.Page) -> str:
    """Page text in reading order: paragraphs re-flowed from text blocks, tables as one line per row."""
    items: list[tuple[float, float, str]] = []
    table_boxes: list[pymupdf.Rect] = []
    for table in page.find_tables().tables:
        rows = [[" ".join((cell or "").split()) for cell in row] for row in table.extract()]
        if len(rows) < 2:
            continue
        header, body = rows[0], rows[1:]
        lines = ["; ".join(f"{h}: {v}" for h, v in zip(header, row) if v) + "." for row in body]
        box = pymupdf.Rect(table.bbox)
        table_boxes.append(box)
        items.append((box.y0, box.x0, "\n".join(lines)))
    for x0, y0, x1, y1, text, _, block_type in page.get_text("blocks"):
        centre = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
        if block_type != 0 or any(box.contains(centre) for box in table_boxes):
            continue
        items.append((y0, x0, " ".join(text.split())))  # re-flow hard-wrapped lines
    return "\n\n".join(text for _, _, text in sorted(items) if text)


def extract_pdf(path: Path) -> list[Document]:
    with pymupdf.open(path) as pdf:
        title = (pdf.metadata or {}).get("title") or path.stem.replace("_", " ").title()
        raw_pages = [_page_text(page) for page in pdf]
    pages = _strip_repeated_lines([clean_text(p) for p in raw_pages])
    return [
        Document(page_content=text, metadata={"source": path.name, "title": title, "page": n, "type": "pdf"})
        for n, text in enumerate(pages, 1) if text.strip()
    ]


def route_row_to_text(row: pd.Series) -> str:
    stops = [s.strip() for s in str(row["stops"]).split("|")]
    return (
        f"Route {row['route_no']} - {row['route_name']} ({row['direction']} direction), "
        f"{row['day_type']} timetable. {row['bus_type']} bus from {row['source']} to {row['destination']}. "
        f"Bus stops in order: {', '.join(stops)}. "
        f"Distance {row['distance_km']} km, journey time {row['duration_min']} minutes, "
        f"full-route fare Rs. {row['fare']}. "
        f"First bus {row['first_departure']}, last bus {row['last_departure']}, "
        f"a bus every {row['frequency_min']} minutes. "
        f"Departure times from {row['source']}: {row['departure_times']}."
    )


def stop_row_to_text(row: pd.Series) -> str:
    text = f"Bus stop {row['stop_name']}"
    if row.get("landmark"):
        text += f" ({row['landmark']})"
    if row.get("area"):
        text += f" in {row['area']}"
    if row.get("routes"):
        text += f" is served by route(s): {', '.join(row['routes'].split())}"
    return text + "."


def fare_chart_to_text(df: pd.DataFrame) -> str:
    lines = ["Stage fare chart (fare depends on the number of stops travelled and the bus type):"]
    for r in df.itertuples():
        lines.append(f"{r.min_stops} to {r.max_stops} stops: Ordinary Rs. {r.ordinary_fare}, "
                     f"AC Rs. {r.ac_fare}, Night Rs. {r.night_fare}.")
    return "\n".join(lines)


def extract_csv(path: Path) -> list[Document]:
    df = pd.read_csv(path, dtype=str).fillna("")
    columns = set(df.columns)
    if {"route_no", "stops", "departure_times"} <= columns:
        return [
            Document(page_content=route_row_to_text(row),
                     metadata={"source": path.name, "title": f"Route {row['route_no']} timetable", "row": i + 2,
                               "type": "timetable", "route_no": row["route_no"], "day_type": row["day_type"],
                               "direction": row["direction"]})
            for i, row in df.iterrows()
        ]
    if {"min_stops", "ordinary_fare"} <= columns:
        return [Document(page_content=fare_chart_to_text(pd.read_csv(path)),
                         metadata={"source": path.name, "title": "Fare chart", "type": "fare_chart"})]
    if {"stop_name", "latitude", "longitude"} <= columns:
        return [
            Document(page_content=stop_row_to_text(row),
                     metadata={"source": path.name, "title": f"Bus stop {row['stop_name']}", "row": i + 2,
                               "type": "stop"})
            for i, row in df.iterrows()
        ]
    # any other CSV: one document per row as "column: value" pairs
    return [
        Document(page_content="; ".join(f"{c}: {v}" for c, v in row.items() if v),
                 metadata={"source": path.name, "title": path.stem, "row": i + 2, "type": "csv"})
        for i, row in df.iterrows()
    ]


def extract_text_file(path: Path) -> list[Document]:
    text = clean_text(path.read_text(encoding="utf-8", errors="ignore"))
    return [Document(page_content=text, metadata={"source": path.name, "title": path.stem, "type": "text"})]


def load_documents(data_dir: Path) -> list[Document]:
    """Data collection + text extraction + cleaning for every supported file under data_dir."""
    docs: list[Document] = []
    for path in sorted(Path(data_dir).rglob("*")):
        suffix = path.suffix.lower()
        if not path.is_file() or suffix not in SUPPORTED:
            continue
        if suffix == ".pdf":
            docs += extract_pdf(path)
        elif suffix == ".csv":
            docs += extract_csv(path)
        else:
            docs += extract_text_file(path)
    return docs


# ---------------------------------------------------------------- chunking
def chunk_documents(docs: list[Document], chunk_size: int = 500, chunk_overlap: int = 80) -> list[Document]:
    """Split long documents into overlapping chunks. Short structured rows are kept whole."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", ". ", " ", ""])
    chunks: list[Document] = []
    for doc in docs:
        if doc.metadata.get("type") in {"timetable", "fare_chart"} and len(doc.page_content) <= chunk_size * 2:
            parts = [doc]
        else:
            parts = splitter.split_documents([doc])
        for n, part in enumerate(parts):
            meta = dict(part.metadata)
            location = meta.get("page") or meta.get("row") or 0
            meta["chunk_id"] = f"{meta['source']}:{location}:{n}"
            chunks.append(Document(page_content=part.page_content, metadata=meta))
    return chunks
