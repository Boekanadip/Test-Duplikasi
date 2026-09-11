"""Streamlit review queue UI for human labeling.

Flow:
  1. Loads a review_queue CSV (left/right row indices + evidence columns).
  2. Shows each pair side-by-side with field-level agreement highlights.
  3. Reviewer clicks Match / Not match / Skip. Labels persist to SQLite
     (default data/processed/review_labels.db) so progress survives reloads.
  4. Export button writes training-ready labels CSV
     (record_id_l, record_id_r, clerical_match_score) — the exact format
     ``train_splink_pipeline`` expects.

Usage:
  streamlit run app/review_app.py -- \
      --input data/processed/complex_hard_merge/review_queue.csv \
      --customers data/processed/_complex_hard_500.csv
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = ROOT / "data" / "processed" / "review_labels.db"
EXPORT_DEFAULT = ROOT / "data" / "processed" / "human_review_labels.csv"

COMPARE_FIELDS = ["first_name", "last_name", "email", "phone_number", "dob", "address", "city"]


def ensure_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS labels (
               pair_key TEXT PRIMARY KEY,
               left_row_index INTEGER NOT NULL,
               right_row_index INTEGER NOT NULL,
               label INTEGER NOT NULL,
               reviewer TEXT DEFAULT '',
               notes TEXT DEFAULT '',
               labeled_at TEXT NOT NULL)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               input_path TEXT, db_path TEXT, started_at TEXT)"""
    )
    conn.commit()
    return conn


def load_queue(path: Path, customers: pd.DataFrame | None) -> pd.DataFrame:
    queue = pd.read_csv(path)
    for col in ("left_row_index", "right_row_index"):
        if col not in queue.columns:
            raise ValueError(f"review queue missing {col}; got {list(queue.columns)}")
    queue["pair_key"] = queue.apply(
        lambda r: f"{min(int(r['left_row_index']), int(r['right_row_index']))}"
        f"|{max(int(r['left_row_index']), int(r['right_row_index']))}",
        axis=1,
    )
    return queue


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Review-queue labeling UI")
    p.add_argument("--input", required=True, help="Path to review_queue.csv")
    p.add_argument("--customers", default=None, help="Path to customer CSV for snapshots")
    p.add_argument("--db", default=str(DB_DEFAULT), help="SQLite path for labels")
    return p


def main() -> None:
    import streamlit as st

    args, _ = build_parser().parse_known_args()
    input_path = Path(args.input)
    db_path = Path(args.db)
    customers = pd.read_csv(args.customers) if args.customers else None
    queue = load_queue(input_path, customers)
    conn = ensure_db(db_path)
    done = pd.read_sql("SELECT pair_key, label FROM labels", conn)
    done_map = dict(zip(done["pair_key"], done["label"])) if len(done) else {}

    st.set_page_config(page_title="Entity Resolution Review", layout="wide")
    st.title("Entity Resolution — Review Queue")
    st.caption(f"input={input_path}  customers={args.customers or 'none'}  db={db_path}")

    counts = queue["match_decision"].value_counts() if "match_decision" in queue else pd.Series(dtype=int)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total pairs", len(queue))
    col2.metric("Labeled", len(done_map))
    col3.metric("Remaining", len(queue) - len(done_map))
    if len(counts):
        st.write("match_decision:", counts.to_dict())

    # filter
    show = st.radio("Show", ["Unlabeled", "All", "Match", "Not match"], horizontal=True, index=0)
    unlabeled = queue[~queue["pair_key"].isin(done_map)]
    if show == "All":
        view = queue
    elif show == "Match":
        view = queue[queue["pair_key"].isin([k for k, v in done_map.items() if v == 1])]
    elif show == "Not match":
        view = queue[queue["pair_key"].isin([k for k, v in done_map.items() if v == 0])]
    else:
        view = unlabeled
    st.caption(f"viewing {len(view)} pairs")

    if len(view) == 0:
        st.success("Queue empty for this filter. Nice work.")
        return

    # picker
    options = view["pair_key"].tolist()
    idx = st.session_state.get("pair_idx", 0)
    idx = min(idx, len(options) - 1)
    pair_key = st.selectbox("Pair", options, index=idx, format_func=lambda k: f"{k}")
    row = view[view["pair_key"] == pair_key].iloc[0]
    l, r = int(row["left_row_index"]), int(row["right_row_index"])

    # evidence header
    meta = []
    for c in ["match_decision", "agreement_count", "match_probability", "concord_score",
              "identity_agreement", "supporting_blocking_strategies"]:
        if c in row.index and pd.notna(row[c]):
            meta.append(f"**{c}**: {row[c]}")
    st.markdown(" · ".join(meta))

    # snapshots
    if customers is not None and l in customers.index and r in customers.index:
        left = customers.loc[l]
        right = customers.loc[r]
        c1, c2 = st.columns(2)
        c1.subheader(f"Left record {l}")
        c2.subheader(f"Right record {r}")
        agree_flags = {}
        for f, std in [("first_name", None), ("last_name", None), ("email", None),
                       ("phone_number", None), ("dob", None), ("address", None), ("city", None)]:
            lv, rv = str(left.get(f, "")), str(right.get(f, ""))
            same = lv.strip().casefold() == rv.strip().casefold() and lv.strip() != ""
            agree_flags[f] = same
        for f in COMPARE_FIELDS:
            lv, rv = str(left.get(f, "")), str(right.get(f, ""))
            mark = "✅" if agree_flags.get(f) else "⚠️"
            c1.write(f"{mark} **{f}**: {lv}")
            c2.write(f"{mark} **{f}**: {rv}")
    else:
        st.info("No customer snapshot available (pass --customers). Showing evidence columns only.")
        st.write(row.to_frame().T)

    # labeling actions
    st.divider()
    reviewer = st.text_input("Reviewer", value=st.session_state.get("reviewer", ""))
    notes = st.text_area("Notes", value="", height=60)
    b1, b2, b3 = st.columns(3)

    def save(label: int | None) -> None:
        if reviewer:
            st.session_state["reviewer"] = reviewer
        if label is None:
            return
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "INSERT OR REPLACE INTO labels (pair_key, left_row_index, right_row_index, label, reviewer, notes, labeled_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (pair_key, l, r, label, reviewer or "", notes or "", now),
        )
        conn.commit()

    if b1.button("✅ Match (1)", use_container_width=True):
        save(1)
        st.session_state["pair_idx"] = idx + 1
        st.rerun()
    if b2.button("❌ Not match (0)", use_container_width=True):
        save(0)
        st.session_state["pair_idx"] = idx + 1
        st.rerun()
    if b3.button("⏭ Skip", use_container_width=True):
        st.session_state["pair_idx"] = idx + 1
        st.rerun()

    st.divider()
    e1, e2 = st.columns(2)
    with e1:
        if st.button("Export training labels CSV"):
            all_labels = pd.read_sql("SELECT left_row_index, right_row_index, label FROM labels ORDER BY labeled_at", conn)
            out = pd.DataFrame({
                "record_id_l": all_labels["left_row_index"].astype("int64").astype("string"),
                "record_id_r": all_labels["right_row_index"].astype("int64").astype("string"),
                "clerical_match_score": all_labels["label"].astype(int),
            })
            EXPORT_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
            out.to_csv(EXPORT_DEFAULT, index=False)
            st.success(f"exported {len(out)} labels → {EXPORT_DEFAULT}")
    with e2:
        if st.button("Undo last label"):
            conn.execute("DELETE FROM labels WHERE pair_key = (SELECT pair_key FROM labels ORDER BY labeled_at DESC LIMIT 1)")
            conn.commit()
            st.rerun()

    with st.expander("Progress so far"):
        prog = pd.read_sql("SELECT pair_key, label, reviewer, labeled_at FROM labels ORDER BY labeled_at DESC LIMIT 20", conn)
        st.dataframe(prog, use_container_width=True)
        st.caption(json.dumps({"match": int((prog['label'] == 1).sum()) if len(prog) else 0,
                               "not_match": int((prog['label'] == 0).sum()) if len(prog) else 0}))


if __name__ == "__main__":
    main()
