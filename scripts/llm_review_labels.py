"""Auto-review pending boundary pairs using the 9Router gateway LLM."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

GATEWAY_URL = os.environ.get('NINEROUTER_URL', 'http://localhost:20128')
GATEWAY_KEY = os.environ.get('NINEROUTER_KEY', '')
MODEL = os.environ.get('NINEROUTER_MODEL', 'db/thirty/deepseek-v4-pro')
FALLBACK_MODELS = ['db/thirty/deepseek-v4-pro', 'db/thirty/qwen3.7-max', 'db/thirty/grok-4.5', 'db/thirty/glm-5.2']
BATCH_SIZE = 5
RETRY_AFTER_FALLBACK = 60

DETAIL_COLUMNS = ['first_name', 'last_name', 'email', 'phone_number', 'dob',
                  'address', 'city', 'state', 'country']

PROMPT_TEMPLATE = """Kamu adalah reviewer entity resolution untuk dataset CRM. Beberapa record bisa \
merepresentasikan orang yang sama dengan variasi penulisan. Untuk setiap pasangan record di bawah, \
putuskan apakah keduanya merepresentasikan ENTITAS/ORANG yang sama.

Aturan:
- match=1 jika bukti identitas kuat menunjukkan orang yang sama (mis. nama+email atau nama+telepon cocok).
- match=0 jika ada konflik identitas jelas (nama berbeda, email & telepon & tanggal lahir berbeda).
- match=-1 jika bukti tidak cukup/ambigu, JANGAN menebak.

Jawab PERSIS dalam satu blok JSON array tanpa teks lain:
[{{"pair": 0, "match": 1, "reason": "singkat"}}]

Pairs:
{blocks}"""


def _format_block(pair_index: int, left: pd.Series, right: pd.Series) -> str:
    def fmt(row_id: str, s: pd.Series) -> str:
        parts = ' | '.join(f'{c}={s[c]}' for c in DETAIL_COLUMNS)
        return f'Record {row_id}: {parts}'
    return f'=== Pair {pair_index} ===\n{fmt("L", left)}\n{fmt("R", right)}'


def _extract_json_array(content: str) -> list[dict]:
    content = content.strip()
    content = re.sub(r'^data:\s*', '', content, flags=re.M)
    content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content).strip()
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if not match:
        raise ValueError(f'No JSON array in model response: {content[:300]}')
    return json.loads(match.group(0))


def _call_chat(messages: list[dict]) -> str:
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {GATEWAY_KEY}',
    }
    last_error: Exception | None = None
    for model in [MODEL, *[m for m in FALLBACK_MODELS if m != MODEL]]:
        body = json.dumps({
            'model': model,
            'messages': messages,
            'max_tokens': 2048,
            'stream': False,
        }).encode('utf-8')
        req = urllib.request.Request(
            f'{GATEWAY_URL}/v1/chat/completions', data=body, headers=headers, method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode('utf-8')
            raw = re.sub(r'\ndata: \[DONE\]\s*$', '', raw).strip()
            return json.loads(raw)['choices'][0]['message']['content']
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 503:
                continue  # try next model
            raise
    assert last_error is not None
    raise last_error


def review_pairs(pairs: pd.DataFrame, raw: pd.DataFrame, batch_size: int = BATCH_SIZE) -> pd.DataFrame:
    """Return review labels for each pair using the gateway LLM."""
    pairs = pairs.copy()
    pairs['record_id_l'] = pairs['record_id_l'].astype('string')
    pairs['record_id_r'] = pairs['record_id_r'].astype('string')
    indexed = raw.set_index('record_id')
    results: list[dict] = []

    for start in range(0, len(pairs), batch_size):
        batch = pairs.iloc[start:start + batch_size]
        blocks = '\n'.join(
            _format_block(idx, indexed.loc[l], indexed.loc[r])
            for idx, (l, r) in enumerate(zip(batch['record_id_l'], batch['record_id_r']))
        )
        messages = [{'role': 'user', 'content': PROMPT_TEMPLATE.format(blocks=blocks)}]

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                content = _call_chat(messages)
                parsed = _extract_json_array(content)
                if len(parsed) != len(batch):
                    raise ValueError(
                        f'Expected {len(batch)} judgments, got {len(parsed)}'
                    )
                for i, (_, row) in enumerate(batch.iterrows()):
                    verdict = parsed[i]
                    if verdict.get('pair') != i:
                        raise ValueError(f'Pair index mismatch: {verdict}')
                    results.append({
                        'record_id_l': str(row['record_id_l']),
                        'record_id_r': str(row['record_id_r']),
                        'review_label': int(verdict.get('match', -99)),
                        'review_reason': str(verdict.get('reason', '')),
                        'review_source': 'llm',
                    })
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(2)
        else:
            raise RuntimeError(f'Batch {start} failed after 3 attempts: {last_error}')

        print(f'  reviewed {min(start + batch_size, len(pairs))}/{len(pairs)}')
        time.sleep(2.0)  # pace to avoid provider rate limits

    return pd.DataFrame(results, columns=[
        'record_id_l', 'record_id_r', 'review_label', 'review_reason', 'review_source',
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default='data/processed/review_queue_pending_boundary.csv')
    parser.add_argument('--output', default='data/processed/reviewed_nearmiss_llm.csv')
    parser.add_argument('--raw', default='data/raw/crm_50000_customers_dirty_v3.csv')
    parser.add_argument('--limit', type=int, default=None, help='Only review first N pairs.')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pairs = pd.read_csv(args.input)
    if args.limit:
        pairs = pairs.head(args.limit)
    print(f'pairs={len(pairs)} model={MODEL} url={GATEWAY_URL}')

    raw = pd.read_csv(args.raw)
    raw['record_id'] = raw.index.astype('string')
    labels = review_pairs(pairs, raw)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    labels.to_csv(out, index=False)
    print('distribution:', labels['review_label'].value_counts().to_dict())
    print(f'saved={out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())