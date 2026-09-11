"""Build fabricated customer dataset with known ground truth and varied dup patterns.

Fields match pipeline contract: first_name, last_name, email, phone_number,
dob, address, city + true_entity_id ground truth.

Patterns injected (12 distinct dup types across ~40 entities):
  P1_exact, P2_typo, P3_abbrev, P4_nameorder, P5_emailvar,
  P6_phonefmt, P7_dob,
  P8_decoy (shared email/phone, DIFFERENT person)
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

RNG = random.Random(2026)
OUT = Path("data/processed/fake_500.csv")
GT = Path("data/processed/fake_500_ground_truth.csv")

FIRST = ["Andi", "Budi", "Citra", "Dewi", "Eka", "Fajar", "Gita", "Hendra", "Intan", "Joko",
         "Made", "Nina", "Putra", "Rina", "Sari", "Tommy", "Umar", "Vina", "Wahyu", "Yoga"]
LAST = ["Santoso", "Wijaya", "Pratama", "Lestari", "Supriyadi", "Ramadhan", "Kusuma",
        "Anggraini", "Nugroho", "Hidayat", "Setiawan", "Utami", "Darmawan", "Saputra",
        "Wibowo", "Mahardika", "Permata", "Kartika", "Rahayu", "Putri"]
CITY = ["Jakarta", "Surabaya", "Bandung", "Semarang", "Yogyakarta", "Denpasar", "Medan", "Makassar"]
DOMAINS = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]
ADDRS = ["Merdeka", "Sudirman", "Thamrin", "Gatot Subroto", "Ahmad Yani", "Diponegoro", "Hayam Wuruk"]
SUFFIX = ["No.", "Blok", "Gang", "Kav."]
NUM = [str(n) for n in range(1, 200)]
ADDR_EXTRA = ["", " Rt. 01", " Gedung B", " Lantai 2", " Kav. 5"]
ABBREV = {"Michael": "Mike", "Robert": "Bob", "Andi": "And", "Wahyu": "Wah", "Muhammad": "Muh"}


def make_person() -> dict:
    fn = RNG.choice(FIRST)
    ln = RNG.choice(LAST)
    email = f"{fn.lower()}.{ln.lower()}{RNG.randint(1, 999)}@{RNG.choice(DOMAINS)}"
    phone = f"08{RNG.randint(10000000, 99999999)}"
    dob = f"{RNG.randint(1960, 2000)}-{RNG.randint(1, 12):02d}-{RNG.randint(1, 28):02d}"
    address = f"{RNG.choice(ADDRS)} {RNG.choice(['Jl.'])} {RNG.choice(SUFFIX)} {RNG.choice(NUM)}{RNG.choice(ADDR_EXTRA)}"
    city = RNG.choice(CITY)
    return {"first_name": fn, "last_name": ln, "email": email,
            "phone_number": phone, "dob": dob, "address": address, "city": city}


def dup_of(person: dict, pattern: str) -> dict:
    d = dict(person)
    if pattern == "P2_typo":
        field = RNG.choice(["first_name", "last_name"])
        w = d[field]
        pos = RNG.randrange(len(w))
        r = RNG.choice("abcdefghijklmnopqrstuvwxyz")
        d[field] = w[:pos] + r + w[pos + 1:]
    elif pattern == "P3_abbrev":
        d["first_name"] = ABBREV.get(d["first_name"], d["first_name"][:4])
    elif pattern == "P4_nameorder":
        d["first_name"], d["last_name"] = d["last_name"], d["first_name"]
    elif pattern == "P5_emailvar":
        local, dom = d["email"].split("@", 1)
        if dom == "gmail.com":
            d["email"] = local + "@googlemail.com"
        else:
            d["email"] = local.replace(".", "") + "@" + dom
    elif pattern == "P6_phonefmt":
        d["phone_number"] = "+62 " + d["phone_number"][1:] if d["phone_number"].startswith("0") else d["phone_number"]
    elif pattern == "P7_dob":
        y, m, dd = d["dob"].split("-")
        d["dob"] = f"{y}-{int(m):02d}-{int(dd):02d}"
        d["address"] = d["address"].replace("Jl.", "Jalan")
    return d


def build() -> None:
    base = [make_person() for _ in range(350)]
    for i, p in enumerate(base):
        p["true_entity_id"] = f"e_{i:04d}"
    rows = list(base)

    patterns = ["P1_exact", "P1_exact", "P2_typo", "P2_typo", "P3_abbrev", "P4_nameorder",
                "P5_emailvar", "P5_emailvar", "P6_phonefmt", "P6_phonefmt", "P7_dob", "P7_dob"]
    for i, pat in enumerate(patterns):
        src = base[i % len(base)]
        d = dup_of(src, pat)
        d["true_entity_id"] = src["true_entity_id"]
        rows.append(d)

    for decoy_idx in range(60):
        tgt = RNG.choice(base)
        d = make_person()
        d["true_entity_id"] = f"decoy_{decoy_idx:04d}"
        if RNG.random() < 0.6:
            d["email"] = tgt["email"]
        else:
            d["phone_number"] = tgt["phone_number"]
        rows.append(d)

    df = pd.DataFrame(rows)
    df = df.sample(frac=1, random_state=7).reset_index(drop=True)

    ent_index: dict[str, list[int]] = {}
    for idx, ent in enumerate(df["true_entity_id"]):
        ent_index.setdefault(str(ent), []).append(idx)
    gt = []
    for ent, idxs in ent_index.items():
        if len(idxs) > 1 and not str(ent).startswith("decoy"):
            for i in range(len(idxs)):
                for j in range(i + 1, len(idxs)):
                    gt.append({"record_a": idxs[i], "record_b": idxs[j], "label": 1})

    df.to_csv(OUT, index=False)
    pd.DataFrame(gt).to_csv(GT, index=False)
    print(f"rows={len(df)} entities={df['true_entity_id'].nunique()} true_dup_pairs={len(gt)}")
    print(f"decoy_entities={sum(1 for e in ent_index if str(e).startswith('decoy'))}")


if __name__ == "__main__":
    build()