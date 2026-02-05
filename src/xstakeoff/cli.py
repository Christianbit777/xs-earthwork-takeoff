import re
import argparse
from pathlib import Path
import fitz  # PyMuPDF
from .pdf_extract import extract_merged_polylines_in_rect, polyline_length

STATION_RE = re.compile(r"\b\d{3}\+\d{2}\b")

def find_station_text(page: fitz.Page, clip: fitz.Rect):
    """Return list of (station_str, rect) within clip region."""
    hits = []
    words = page.get_text("words", clip=clip)
    for w in words:
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        if STATION_RE.match(text):
            hits.append((text, fitz.Rect(x0, y0, x1, y1)))
    return hits

def detect_section_frames(page: fitz.Page):
    """
    Robust method: detect all station labels (e.g., 445+00) and build a section
    frame around each station. Works well on WisDOT/CADDS cross section sheets
    that stack 3 sections vertically.

    Returns: list of fitz.Rect, top-to-bottom
    """
    # 1) Find all station labels on the whole page
    station_hits = []
    words = page.get_text("words")  # all words on page
    for w in words:
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        if STATION_RE.match(text):
            station_hits.append((text, fitz.Rect(x0, y0, x1, y1)))

    # If we can't find stations, fall back to previous heuristic (optional)
    if not station_hits:
        return []

    # 2) Sort stations top-to-bottom by their y position
    station_hits = sorted(station_hits, key=lambda s: s[1].y0)

    # 3) Infer typical vertical spacing between sections
    ys = [r.y0 for _, r in station_hits]
    deltas = [ys[i+1] - ys[i] for i in range(len(ys) - 1)]
    # Use median delta as section height proxy; fall back to page height / 3
    if deltas:
        deltas_sorted = sorted(deltas)
        median_delta = deltas_sorted[len(deltas_sorted)//2]
        section_h = max(200, median_delta * 0.9)  # conservative
    else:
        section_h = page.rect.height / 3

    # 4) Build frames around each station
    frames = []
    margin_left = page.rect.width * 0.03
    margin_right = page.rect.width * 0.02

    for i, (st, r) in enumerate(station_hits):
        # Put station near the right edge inside the section.
        # Center the section vertically around the station y.
        y_center = (r.y0 + r.y1) / 2
        y0 = y_center - section_h / 2
        y1 = y_center + section_h / 2

        # Clamp to page
        y0 = max(0, y0)
        y1 = min(page.rect.height, y1)

        fr = fitz.Rect(margin_left, y0, page.rect.width - margin_right, y1)
        frames.append(fr)

    # 5) Deduplicate overlapping frames (in case station text repeats)
    frames_sorted = sorted(frames, key=lambda r: r.y0)
    merged = []
    for fr in frames_sorted:
        if not merged:
            merged.append(fr)
            continue
        prev = merged[-1]
        # If heavily overlapping, keep the larger union
        overlap = prev & fr
        if overlap and overlap.get_area() > 0.4 * min(prev.get_area(), fr.get_area()):
            merged[-1] = prev | fr
        else:
            merged.append(fr)

    return merged

def make_debug_overlay(input_pdf: Path, output_pdf: Path, page_index: int):
    doc = fitz.open(str(input_pdf))
    page = doc.load_page(page_index)

    frames = detect_section_frames(page)
    print(
        f"Detected {len(frames)} frame(s): "
        f"{[(round(r.x0), round(r.y0), round(r.x1), round(r.y1)) for r in frames]}"
    )

    page.insert_text((40, 40), f"Detected {len(frames)} frame(s)", fontsize=14)

    for i, fr in enumerate(frames, start=1):
        # --- DRAW SECTION FRAME ---
        shape = page.new_shape()
        shape.draw_rect(fr)
        shape.finish(
            width=6,
            color=(1, 0, 0),
            fill=(1, 0.7, 0.7),
            fill_opacity=0.25,
        )
        shape.commit()

        # --- SECTION LABEL ---
        stations = find_station_text(page, clip=fr)
        station = None
        if stations:
            station = sorted(stations, key=lambda s: -s[1].x1)[0][0]

        page.insert_text(
            (fr.x0 + 10, fr.y0 + 20),
            f"Section {i}: {station or 'NO STATION FOUND'}",
            fontsize=12,
        )

        polys = extract_merged_polylines_in_rect(
            page,
            fr,
            endpoint_tol=2.0,
            min_length=120.0,
        )

        TOP_N = 12
        polys = polys[:TOP_N]

        for j, poly in enumerate(polys, start=1):
            # Draw polyline
            shp = page.new_shape()
            shp.draw_polyline(poly)
            shp.finish(width=2, color=(0, 0, 1))  # blue
            shp.commit()

            # Label polyline
            L = polyline_length(poly)
            x0, y0 = poly[0]
            page.insert_text(
                (x0 + 3, y0 + 3),
                f"S{i}-P{j} L={L:.0f}",
                fontsize=7,
            )

    doc.save(str(output_pdf))
    doc.close()

def main():
    ap = argparse.ArgumentParser(
        prog="xstakeoff",
        description="Cross-section takeoff debug overlay (frame + station detection)",
    )
    ap.add_argument("pdf", help="Input PDF path")
    ap.add_argument("--page", type=int, required=True, help="0-based page index")
    ap.add_argument("--out", default="out_debug.pdf", help="Output marked PDF")
    args = ap.parse_args()

    print("cli.py started")  # proof-of-life
    make_debug_overlay(Path(args.pdf), Path(args.out), args.page)
    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()


