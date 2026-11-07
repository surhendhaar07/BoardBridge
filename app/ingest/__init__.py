"""Document parsing and text cleaning for BoardBridge ingestion."""

from typing import TYPE_CHECKING

from app.ingest.clean import clean_text, drop_lines, repeated_lines, shape

if TYPE_CHECKING:
    from app.ingest.parse import parse_file


def __getattr__(name: str):
    if name == "parse_file":
        from app.ingest.parse import parse_file

        return parse_file
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["clean_text", "drop_lines", "repeated_lines", "shape", "parse_file"]
