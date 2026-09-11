"""Entity Resolution review UI — full 4-tab workflow.

Tab 1 (Input Baru):  upload Google-Form CSV -> import -> baseline -> Splink
                      -> concord merge -> review_queue (run inside UI).
Tab 2 (Review):       human labels Match/Not-match/Skip persisted to SQLite.
Tab 3 (Hasil):        merged entities + summary + review queue stats.
Tab 4 (Retrain):      labels for this session -> retrain Splink -> tune
                      threshold -> re-run merge. Model learns from new data.

Sessions: each upload creates data/processed/ui_sessions/<stamp>/ holding
clean.csv, predictions.csv, merge outputs, review_queue.csv. Labels live in
data/processed/review_labels.db keyed by session.

Usage:
  streamlit run app/review_app.py            # UI-managed (recommended)
  streamlit run app/review_app.py -- --db path/to/review_labels.db
"""
from __future__ import annotations

import argparse
import io
import json
import sqlite3
import warnings
from datetime import datetime
from importlib import util as _util
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = ROOT / "data" / "processed" / "review_labels.db"
SESSIONS = ROOT / "data" / "processed" / "ui_sessions"
EXPORT_DEFAULT = ROOT / "data" / "processed" / "human_review_labels.csv"

DB_PATH = DB_DEFAULT  # overridable via --db before run() is called


def set_db(path: str) -> None:
    global DB_PATH
    DB_PATH = Path(path)

COMPARE_FIELDS = ["first_name", "last_name", "email", "phone_number", "dob", "address", "city"]

_INP = _util.spec_from_file_location("import_form_csv", ROOT / "scripts" / "import_form_csv.py")
_MF = _util.module_from_spec(_INP)
_INP.loader.exec_module(_MF)
import_form_csv = _MF.import_form_csv

FORM_COLS = ["first_name", "last_name", "email", "phone_number", "dob", "address", "city"]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_db(db_path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(db_path) if db_path else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS labels (
               session TEXT NOT NULL,
               pair_key TEXT NOT NULL,
               left_row_index INTEGER NOT NULL,
               right_row_index INTEGER NOT NULL,
               label INTEGER NOT NULL,
               reviewer TEXT DEFAULT '',
               notes TEXT DEFAULT '',
               labeled_at TEXT NOT NULL,
               PRIMARY KEY (session, pair_key))"""
    )
    conn.commit()
    return conn


def labels_for_session(conn: sqlite3.Connection, session: str) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT left_row_index, right_row_index, label FROM labels WHERE session=? ORDER BY labeled_at",
        conn, params=(session,),
    )


def queue_pair_key(row: pd.Series) -> str:
    return f"{min(int(row['left_row_index']), int(row['right_row_index']))}|{max(int(row['left_row_index']), int(row['right_row_index']))}"


def write_export(labels: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "record_id_l": labels["left_row_index"].astype("int64").astype("string"),
        "record_id_r": labels["right_row_index"].astype("int64").astype("string"),
        "clerical_match_score": labels["label"].astype(int),
    }).to_csv(path, index=False)


def is_form_format(frame: pd.DataFrame) -> bool:
    heads = {c.strip().casefold() for c in frame.columns}
    return not {c.casefold() for c in FORM_COLS}.issubset(heads)


def run_session(uploaded_bytes, session: Path) -> dict:
    """Full pipeline for one uploaded CSV. Returns summary dict."""
    # 1. read + import
    raw = pd.read_csv(io.BytesIO(uploaded_bytes))
    clean = import_form_csv(session / "_tmp_form.csv") if is_form_format(raw) else raw
    clean = clean.loc[:, ~clean.columns.duplicated(keep="last")]
    clean_path = session / "form_clean.csv"
    clean.to_csv(clean_path, index=False)

    # 2. baseline decisions
    from src.blocking import generate_candidate_pairs
    from src.comparison import build_comparison_vectors
    from src.decision import apply_match_policy
    from src.standardization import standardize_customers
    std = standardize_customers(clean)
    comp = build_comparison_vectors(std, generate_candidate_pairs(std))
    base = apply_match_policy(comp)
    base_path = session / "baseline.csv"
    base.to_csv(base_path, index=False)
    n_base = len(base)

    # 3. splink predict (labels if available, else unsupervised)
    from src.splink_pipeline import prepare_splink_input, run_splink_pipeline, train_splink_pipeline
    warnings.filterwarnings("ignore")
    conn = ensure_db()
    labels = labels_for_session(conn, session.name)
    conn.close()
    n_labels = len(labels)
    if n_labels >= 2:
        lbl_path = session / "labels.csv"
        write_export(labels, lbl_path)
        preds = train_splink_pipeline(str(clean_path), str(lbl_path), str(session / "predictions.csv"))
        mode = f"trained({n_labels} labels)"
    else:
        preds = run_splink_pipeline(str(clean_path), str(session / "predictions.csv"))
        mode = "unsupervised (u-prob only)"
    n_preds = len(preds)

    # 4. concord merge
    from src.merge import run_merge_pipeline
    merge_thr = st.session_state.get("merge_threshold", 0.95)
    res = run_merge_pipeline(str(clean_path), str(session / "predictions.csv"),
                             str(session), auto_threshold=merge_thr, review_threshold=0.15)
    summary = res["summary"]

    return {
        "session": session, "clean": clean_path, "base": base_path,
        "baseline_pairs": n_base, "splink_pairs": n_preds, "splink_mode": mode,
        "merge_summary": summary,
    }


def tab_input() -> None:
    st.subheader("1 — Input data baru (Google Form CSV)")
    uploaded = st.file_uploader("Unggah CSV (header Google-Form atau first_name,last_name,...)",
                                type=["csv"])
    merge_thr = st.slider("Auto-merge concord threshold", 0.80, 1.0, 0.95, 0.01,
                          help="concord_score >= ini -> auto_merge; band 0.15-0.95 -> review")
    st.session_state["merge_threshold"] = merge_thr

    if uploaded is None:
        st.info("Tunggu upload. Data baru akan: import → baseline → Splink → merge → review queue.")
        return

    if st.button("Jalankan pipeline", type="primary"):
        if "running" not in st.session_state:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session = SESSIONS / f"session_{stamp}"
            session.mkdir(parents=True, exist_ok=True)
            upload_dir = session / "_tmp_form.csv"
            upload_dir.write_bytes(uploaded.getbuffer())
            try:
                with st.spinner("Standardize → blocking → baseline → Splink → merge ..."):
                    info = run_session(uploaded.getvalue(), session)
                st.session_state.update(info)
                st.success("Pipeline selesai. Buka tab Review.")
                st.json({k: (str(v) if isinstance(v, Path) else v)
                         for k, v in info["merge_summary"].items()})
            except ValueError as e:
                st.error(str(e))
                import traceback as _tb
                st.code(_tb.format_exc())
                st.info(
                    "Header yang diharapkan (boleh varian kata, case-insensitive):\n"
                    "- first_name: `first name / nama depan / nama`\n"
                    "- last_name: `last name / nama belakang`\n"
                    "- email: `email`\n"
                    "- phone_number: `phone number / nomor telepon / no telepon / phone`\n"
                    "- dob: `dob / tanggal lahir / tgl lahir / date of birth`\n"
                    "- address: `address / alamat`\n"
                    "- city: `city / kota`\n"
                    "AWALAN `Pertanyaan N - ...` di Google Forms otomatis dipotong.\n"
                    "Gunakan contoh: `Nota/f/fixtures/customers_sample.csv` sebagai referensi."
                )
                return
            return

    info = st.session_state.get("session")
    if info is None:
        return
    st.write(f"Session aktif: `{info['session'].name}`")
    m = info["merge_summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidate pairs", m["candidate_pairs"])
    c2.metric("Auto-merge", m["auto_merge_pairs"])
    c3.metric("Review queue", m["review_required_pairs"])
    c4.metric("Entities", m["output_entities"])
    st.caption(f"Splink {info['splink_mode']}")


@st.cache_data(show_spinner=False)
def _load_queue(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def tab_review() -> None:
    st.subheader("2 — Review pasangan (Match / Not match / Skip)")
    info = st.session_state.get("session")
    if info is None:
        st.info("Upload data dulu di tab 1.")
        return
    session = Path(info["session"])
    queue_path = session / "review_queue.csv"
    if not queue_path.exists():
        st.warning("review_queue.csv belum ada — cek tab 1.")
        return
    queue = _load_queue(str(queue_path))
    customers = pd.read_csv(session / "form_clean.csv")
    conn = ensure_db()
    done = labels_for_session(conn, session.name)
    done_map = dict(zip(done["pair_key"], done["label"])) if len(done) else {}

    c1, c2, c3 = st.columns(3)
    c1.metric("Total pairs", len(queue))
    c2.metric("Labeled", len(done_map))
    c3.metric("Remaining", len(queue) - len(done_map))

    if "match_decision" in queue:
        st.write("match_decision:", queue["match_decision"].value_counts().to_dict())

    show = st.radio("Show", ["Unlabeled", "All", "Match", "Not match"], horizontal=True, index=0)
    if show == "All":
        view = queue
    elif show == "Match":
        view = queue[queue["pair_key"].isin([k for k, v in done_map.items() if v == 1])]
    elif show == "Not match":
        view = queue[queue["pair_key"].isin([k for k, v in done_map.items() if v == 0])]
    else:
        view = queue[~queue["pair_key"].isin(done_map)]
    st.caption(f"viewing {len(view)} pairs")

    if len(view) == 0:
        st.success("Queue selesai untuk filter ini. Bisa lanjut ke tab 4 (retrain).")
        return

    opts = view["pair_key"].tolist()
    idx = st.session_state.get("pair_idx", 0)
    idx = min(idx, len(opts) - 1)
    pair_key = st.selectbox("Pasangan", opts, index=idx)
    row = view[view["pair_key"] == pair_key].iloc[0]
    l, r = int(row["left_row_index"]), int(row["right_row_index"])

    meta = [f"**{c}**: {row[c]}" for c in
            ["match_decision", "agreement_count", "match_probability", "concord_score", "identity_agreement"]
            if c in row.index and pd.notna(row[c])]
    st.markdown(" · ".join(meta))

    cL, cR = st.columns(2)
    cL.subheader(f"Left record {l}")
    cR.subheader(f"Right record {r}")
    for f in COMPARE_FIELDS:
        lv = str(customers.loc[l, f]) if l in customers.index else ""
        rv = str(customers.loc[r, f]) if r in customers.index else ""
        mark = "✅" if lv.strip().casefold() == rv.strip().casefold() and lv.strip() != "" else "⚠️"
        cL.write(f"{mark} **{f}**: {lv}")
        cR.write(f"{mark} **{f}**: {rv}")

    st.divider()
    reviewer = st.text_input("Reviewer", value=st.session_state.get("reviewer", ""))
    notes = st.text_area("Notes", height=60)
    b1, b2, b3 = st.columns(3)

    def save(label: int | None) -> None:
        if reviewer:
            st.session_state["reviewer"] = reviewer
        if label is not None:
            conn.execute(
                "INSERT OR REPLACE INTO labels (session,pair_key,left_row_index,right_row_index,label,reviewer,notes,labeled_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (session.name, pair_key, l, r, label, reviewer or "", notes or "", now()),
            )
            conn.commit()
        st.session_state["pair_idx"] = int(pair_key.split("|")[0] if False else idx + 1)
        st.rerun()

    if b1.button("✅ Match (1)", use_container_width=True):
        save(1)
    if b2.button("❌ Not match (0)", use_container_width=True):
        save(0)
    if b3.button("⏭ Skip", use_container_width=True):
        save(None)

    st.divider()
    with st.expander("Progress / export"):
        prog = pd.read_sql("SELECT session,pair_key,label,reviewer,labeled_at FROM labels WHERE session=? ORDER BY labeled_at DESC LIMIT 20",
                           conn, params=(session.name,))
        st.dataframe(prog, use_container_width=True)
        if st.button("Export training labels CSV"):
            all_lb = labels_for_session(conn, session.name)
            if len(all_lb):
                write_export(all_lb, EXPORT_DEFAULT)
                st.success(f"exported {len(all_lb)} labels → {EXPORT_DEFAULT}")
            else:
                st.warning("Belum ada label.")
    conn.close()


def tab_results() -> None:
    st.subheader("3 — Hasil merge")
    info = st.session_state.get("session")
    if info is None:
        st.info("Upload data dulu di tab 1.")
        return
    session = Path(info["session"])
    st.json({k: str(v) for k, v in info["merge_summary"].items()})

    merged_path = session / "merged_records.csv"
    members_path = session / "entity_members.csv"
    if merged_path.exists():
        merged = pd.read_csv(merged_path)
        st.write(f"Merged records: {len(merged)}")
        st.dataframe(merged[["entity_id", "member_count"]].head(30), use_container_width=True)
        st.download_button("Download merged_records.csv", merged.to_csv(index=False).encode(),
                           "merged_records.csv", "text/csv")
    if members_path.exists():
        st.write("Sample entity members:")
        st.dataframe(pd.read_csv(members_path).head(20), use_container_width=True)


def tab_retrain() -> None:
    st.subheader("4 — Retrain dari label baru")
    info = st.session_state.get("session")
    if info is None:
        st.info("Upload data dulu di tab 1.")
        return
    session = Path(info["session"])
    clean_path = session / "form_clean.csv"
    conn = ensure_db()
    labels = labels_for_session(conn, session.name)
    conn.close()
    pos = int(labels["label"].sum()) if len(labels) else 0
    st.write(f"Label tersedia: **{len(labels)}** (match={pos}, not_match={len(labels)-pos})")

    if len(labels) < 2:
        st.warning("Perlu ≥2 label untuk retrain. Label dulu di tab 2.")
        return

    if st.button("Retrain Splink + re-tune threshold", type="primary"):
        from src.splink_pipeline import (
            evaluate_splink_holdout, split_labels, train_splink_pipeline,
        )
        lbl_path = session / "labels.csv"
        write_export(labels, lbl_path)
        train, holdout = split_labels(lbl_path)
        with st.spinner("Training m/u pada label ..."):
            preds = train_splink_pipeline(str(clean_path), str(session / "retrain_labels.csv"),
                                          str(session / "retrain_pred.csv"))
        # persist split for reproducibility
        train.to_csv(session / "retrain_labels.csv", index=False)
        holdout.to_csv(session / "holdout_labels.csv", index=False)
        rows = []
        best_t, best_f1 = 0.5, -1
        for t in [0.1, 0.3, 0.5, 0.7, 0.9]:
            m = evaluate_splink_holdout(preds, holdout, threshold=t)
            rows.append({"threshold": t, **{k: m[k] for k in ("true_positive", "false_positive", "false_negative", "precision", "recall", "f1")}})
            if m["f1"] > best_f1:
                best_t, best_f1 = t, m["f1"]
        sweep = pd.DataFrame(rows)
        st.write("Holdout evaluation (pair in holdout tidak pernah untuk training):")
        st.dataframe(sweep, use_container_width=True)
        st.success(f"Best split @ {best_t} → rerun merge auto_threshold={best_t}")
        st.session_state["merge_threshold"] = float(best_t)
        st.session_state["best_f1"] = float(best_f1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Review queue UI — full pipeline")
    p.add_argument("--db", default=str(DB_DEFAULT), help="SQLite path for review labels")
    return p


def main() -> None:
    args, _ = build_parser().parse_known_args()
    set_db(args.db)
    st.set_page_config(page_title="Entity Resolution — Full Workflow", layout="wide", page_icon="🧬")
    st.title("Entity Resolution — Input · Review · Hasil · Retrain")
    st.caption("Form CSV → import → baseline → Splink → concord merge → review → retrain (belajar terus)")

    t1, t2, t3, t4 = st.tabs(["📥 1. Input Baru", "✅ 2. Review", "📊 3. Hasil", "🔁 4. Retrain"])
    with t1:
        tab_input()
    with t2:
        tab_review()
    with t3:
        tab_results()
    with t4:
        tab_retrain()


if __name__ == "__main__":
    main()