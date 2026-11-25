from app.config import get_settings
from app.rag.preprocess import chunk_documents, clean_text, extract_csv, extract_pdf


def test_clean_text():
    assert clean_text("Bus  time-\ntable\n\n\n\nnext\x00 line") == "Bus timetable\n\nnext line"


def test_extract_routes_csv():
    docs = extract_csv(get_settings().data_dir / "routes.csv")
    assert len(docs) == 78  # 13 routes x 2 directions x 3 day types
    first = docs[0]
    assert first.metadata["route_no"] == "1" and first.metadata["type"] == "timetable"
    assert "Railway Station" in first.page_content and "Rs. 25" in first.page_content


def test_extract_stops_csv():
    docs = extract_csv(get_settings().data_dir / "stops.csv")
    kautha = next(d for d in docs if d.metadata["title"] == "Bus stop Kautha")
    assert kautha.metadata["type"] == "stop"
    assert kautha.page_content == ("Bus stop Kautha (Kautha, south end of the Godavari bridge) "
                                   "is served by route(s): 2, 7N, 13.")


def test_extract_pdf_tables_and_headers():
    pages = extract_pdf(get_settings().data_dir / "docs" / "fare_policy_and_concessions.pdf")
    text = "\n".join(p.page_content for p in pages)
    assert "Stops travelled: 3 - 4; Ordinary (Rs.): 15; AC (Rs.): 25; Night (Rs.): 20." in text
    assert "SAMPLE DATA" not in text  # repeated running header removed
    assert all(p.metadata["page"] >= 1 for p in pages)


def test_chunking_keeps_rows_and_splits_pdfs():
    settings = get_settings()
    rows = extract_csv(settings.data_dir / "routes.csv")
    pdf = extract_pdf(settings.data_dir / "docs" / "passenger_guide.pdf")
    chunks = chunk_documents(rows + pdf, chunk_size=500, chunk_overlap=80)
    assert sum(c.metadata["type"] == "timetable" for c in chunks) == len(rows)
    pdf_chunks = [c for c in chunks if c.metadata["type"] == "pdf"]
    assert len(pdf_chunks) > len(pdf)
    assert all(len(c.page_content) <= 500 for c in pdf_chunks)
    assert len({c.metadata["chunk_id"] for c in chunks}) == len(chunks)
