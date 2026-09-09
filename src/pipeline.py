from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .blocking import generate_candidate_pairs
from .comparison import build_comparison_vectors
from .config import PipelineConfig, build_config
from .decision import apply_match_policy
from .io import load_customer_csv, save_artifact
from .logging_setup import configure_logging
from .standardization import standardize_customers

logger = logging.getLogger(__name__)


def run_pipeline(config: PipelineConfig) -> pd.DataFrame:
    """Run the candidate pipeline using an explicit configuration."""
    logger.info('Loading input: %s', config.input_path)
    raw = load_customer_csv(config.input_path)
    logger.info('Loaded rows=%d columns=%d', len(raw), raw.shape[1])

    standardized = standardize_customers(raw).reset_index(drop=True)
    logger.info('Standardized derived columns created')

    pairs = generate_candidate_pairs(standardized)
    logger.info('Candidate pairs generated: %d', len(pairs))

    comparisons = build_comparison_vectors(standardized, pairs)
    decisions = apply_match_policy(
        comparisons,
        high_confidence_threshold=config.high_confidence_threshold,
        candidate_threshold=config.candidate_threshold,
    )
    logger.info('Decision counts: %s', decisions['match_decision'].value_counts().to_dict())

    if config.output_path is not None:
        save_artifact(decisions, config.output_path, sep=config.output_sep)
        logger.info('Saved candidate artifact: %s', config.output_path)

    return decisions


def run_candidate_pipeline(
    input_path: str | Path,
    output_path: str | Path | None = None,
    **overrides,
) -> pd.DataFrame:
    """Build a config, configure logging, and run the pipeline."""
    config = build_config(input_path, output_path, **overrides)
    configure_logging(config.log_level)
    return run_pipeline(config)
