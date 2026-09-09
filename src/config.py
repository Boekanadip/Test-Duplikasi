from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    """Central configuration for the candidate pipeline."""

    input_path: Path
    output_path: Path | None = None
    high_confidence_threshold: int = 4
    candidate_threshold: int = 2
    output_sep: str = ','
    log_level: str = 'INFO'

    def __post_init__(self) -> None:
        if self.candidate_threshold < 1:
            raise ValueError('candidate_threshold must be >= 1.')
        if self.high_confidence_threshold < self.candidate_threshold:
            raise ValueError('high_confidence_threshold must be >= candidate_threshold.')


def build_config(
    input_path: str | Path,
    output_path: str | Path | None = None,
    **overrides,
) -> PipelineConfig:
    return PipelineConfig(
        input_path=Path(input_path),
        output_path=Path(output_path) if output_path is not None else None,
        **overrides,
    )
