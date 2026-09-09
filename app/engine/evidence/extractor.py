from __future__ import annotations

import ast
from pathlib import Path
from typing import Sequence

from app.engine.models import AnalysisContext, Evidence, RuleMatch


class EvidenceExtractor:
    """
    Deterministically extracts immutable Evidence records from AST nodes and source context.
    Ensures safe encoding handling, bounded line slicing, and robust extraction from untrusted repositories.
    """

    def extract(
        self,
        match: RuleMatch,
        context: AnalysisContext | None = None,
        context_lines: int = 0,
    ) -> Evidence:
        """
        Extract Evidence from a RuleMatch and its AnalysisContext.
        """
        source_lines = self._resolve_source_lines(context)
        file_path = match.file_path or (getattr(context, "file_path", "") if context else "")
        return self.extract_from_node(
            node=match.node,
            source=source_lines,
            file_path=file_path,
            rule_id=match.rule_id,
            context_lines=context_lines,
        )

    def extract_from_node(
        self,
        node: ast.AST | None,
        source: str | bytes | Sequence[str],
        file_path: str = "",
        rule_id: str | None = None,
        context_lines: int = 0,
    ) -> Evidence:
        """
        Extract exact line ranges and safe source excerpt for a given AST node.
        """
        lines = self._normalize_to_lines(source)

        if node is None:
            start_line = 1
            end_line = 1
            col_offset = 0
            end_col_offset = None
        else:
            start_line = getattr(node, "lineno", 1)
            if start_line is None:
                start_line = 1
            end_line = getattr(node, "end_lineno", start_line)
            if end_line is None or end_line < start_line:
                end_line = start_line
            col_offset = getattr(node, "col_offset", 0)
            if col_offset is None:
                col_offset = 0
            end_col_offset = getattr(node, "end_col_offset", None)

        source_excerpt = self._extract_excerpt(
            lines=lines,
            start_line=start_line,
            end_line=end_line,
            context_lines=context_lines,
        )

        return Evidence(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            col_offset=col_offset,
            end_col_offset=end_col_offset,
            source_excerpt=source_excerpt,
            rule_id=rule_id,
        )

    def _resolve_source_lines(self, context: AnalysisContext | Any) -> list[str]:
        """
        Retrieve lines from AnalysisContext or safely read from the file path if not present.
        """
        if context is None:
            return []
        source_lines = getattr(context, "source_lines", None)
        if source_lines:
            return list(source_lines)
        source_code = getattr(context, "source_code", None)
        if source_code:
            return source_code.splitlines()
        file_path = getattr(context, "file_path", None) or getattr(context, "path", None)
        if file_path and Path(file_path).is_file():
            try:
                with open(file_path, "rb") as f:
                    raw = f.read()
                # Safe decode handling invalid encodings without crashing
                return raw.decode("utf-8", errors="replace").splitlines()
            except OSError:
                return []
        return []

    def _normalize_to_lines(self, source: str | bytes | Sequence[str]) -> list[str]:
        """
        Convert raw bytes, string, or sequences to a list of clean string lines.
        Malformed byte sequences are safely replaced with the Unicode replacement character.
        """
        if isinstance(source, bytes):
            return source.decode("utf-8", errors="replace").splitlines()
        elif isinstance(source, str):
            return source.splitlines()
        elif isinstance(source, (list, tuple)):
            return [str(line).rstrip("\r\n") for line in source]
        return []

    def _extract_excerpt(
        self,
        lines: list[str],
        start_line: int,
        end_line: int,
        context_lines: int = 0,
    ) -> str:
        """
        Safely slice source lines bounded by start_line and end_line (1-indexed).
        """
        if not lines:
            return ""

        total_lines = len(lines)
        clamped_start = max(1, min(start_line, total_lines))
        clamped_end = max(clamped_start, min(end_line, total_lines))

        if context_lines > 0:
            slice_start = max(1, clamped_start - context_lines)
            slice_end = min(total_lines, clamped_end + context_lines)
        else:
            slice_start = clamped_start
            slice_end = clamped_end

        # Convert 1-indexed line numbers to 0-indexed slice
        selected = lines[slice_start - 1 : slice_end]
        return "\n".join(selected)
