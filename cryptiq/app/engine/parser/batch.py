"""Parsing a whole snapshot's worth of discovered files.

One malformed file produces a parse error and nothing more: the rest of the
repository still parses. Results are ordered by relative path, so the output
does not depend on the order the files arrived in.
"""

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path

from app.engine.discovery import DiscoveredFile
from app.engine.parser.base import ParsedFile, ParseError, ParseErrorType
from app.engine.parser.registry import get_parser

logger = logging.getLogger(__name__)


def parse_sources(sources: Iterable[tuple[str, str]], language: str = "python") -> list[ParsedFile]:
    """Parse (relative path, source text) pairs, ordered by path."""
    parser = get_parser(language)
    if parser is None:
        raise ValueError(f"No parser is registered for language {language!r}.")
    parsed = [parser.parse(source, path) for path, source in sources]
    return sorted(parsed, key=lambda file: file.path)


def parse_all(root: Path, discovered_files: Sequence[DiscoveredFile]) -> list[ParsedFile]:
    """Read and parse the supported files of an extracted snapshot.

    Paths are resolved under root and confirmed to stay inside it, so a
    discovery result cannot direct the parser at anything else on the disk.
    Phase 3 guarantees these files are valid UTF-8; a file that cannot be read
    anyway becomes a READ_ERROR rather than ending the batch.
    """
    resolved_root = root.resolve()
    results: list[ParsedFile] = []
    for discovered in discovered_files:
        if not discovered.is_supported:
            continue
        source = _read(resolved_root, discovered.path)
        if source is None:
            results.append(_read_error(discovered.path))
            continue
        results.append(parse_sources([(discovered.path, source)])[0])

    failed = sum(1 for file in results if not file.parsed)
    logger.info("parsed %d files under %s, %d failed", len(results), root, failed)
    return sorted(results, key=lambda file: file.path)


def _read(resolved_root: Path, relative_path: str) -> str | None:
    target = (resolved_root / relative_path).resolve()
    if resolved_root not in target.parents:
        logger.warning("refusing to read a path outside the snapshot root")
        return None
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("could not read a discovered file: %s", type(exc).__name__)
        return None


def _read_error(path: str) -> ParsedFile:
    from app.engine.parser.python import PythonParser, module_path_for

    parser = PythonParser()
    return ParsedFile(
        path=path,
        language=parser.language,
        parser_version=parser.version,
        module_path=module_path_for(path),
        tree=None,
        error=ParseError(
            path=path,
            error_type=ParseErrorType.READ_ERROR,
            message="The file could not be read as UTF-8 text.",
        ),
    )
