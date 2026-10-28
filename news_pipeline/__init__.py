"""Local, deterministic financial news processing."""

from .pipeline import process_articles
from .io import run_pipeline

__all__ = ["process_articles", "run_pipeline"]
