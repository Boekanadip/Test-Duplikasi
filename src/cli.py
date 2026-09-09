from __future__ import annotations

import argparse
from collections.abc import Sequence

from .config import build_config
from .logging_setup import configure_logging
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='entity-resolution',
        description='Generate entity-resolution candidate decisions. No automatic merge.',
    )
    parser.add_argument('--input', required=True, help='Path to the customer CSV.')
    parser.add_argument('--output', default=None, help='Optional path for the candidate artifact.')
    parser.add_argument('--high-confidence-threshold', type=int, default=4)
    parser.add_argument('--candidate-threshold', type=int, default=2)
    parser.add_argument('--output-sep', default=',')
    parser.add_argument('--log-level', default='INFO')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = build_config(
        args.input,
        args.output,
        high_confidence_threshold=args.high_confidence_threshold,
        candidate_threshold=args.candidate_threshold,
        output_sep=args.output_sep,
        log_level=args.log_level,
    )
    configure_logging(config.log_level)
    decisions = run_pipeline(config)
    counts = decisions['match_decision'].value_counts().to_dict()
    print(f'candidate_pairs={len(decisions)} decisions={counts}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
