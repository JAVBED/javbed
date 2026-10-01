"""Conservative Java crash detection based on recent logs and reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Diagnosis:
    cause: str
    evidence: str
    log: Path | None
    report: Path | None
    suspect_mod: str = ""


PATTERNS = (
    (r"(?i)mod[s]? .{0,120}(?:requires?|depends? on|missing dependency)", "A mod dependency appears to be missing or incompatible."),
    (r"(?i)(?:incompatible mod|mod resolution encountered|conflicting mods)", "One or more mods appear incompatible with this instance."),
    (r"(?i)(?:duplicate mod|duplicate.*mod id|found duplicate)", "Duplicate mods may be installed."),
    (r"(?i)(?:unsupportedclassversionerror|class file version|requires java \d+)", "The selected Java runtime may be too old for this game or mod."),
    (r"(?i)(?:outofmemoryerror|could not reserve enough space|java heap space)", "Minecraft appears to have run out of memory."),
    (r"(?i)(?:mixin apply failed|mixin transformation|mixin\.transformer)", "A mod or loader mixin failed; check mod and loader compatibility."),
    (r"(?i)(?:failed to load.*config|corrupt.*config)", "A mod configuration may be damaged."),
    (r"(?i)(?:noclassdeffounderror|classnotfoundexception|missing library)", "A required Java class or library could be missing."),
    (r"(?i)(?:requires minecraft|minecraft version.*not supported)", "A mod may target another Minecraft version."),
    (r"(?i)(?:wrong loader|requires fabric|requires forge|requires neoforge|requires quilt)", "A mod may require another loader."),
)


def diagnose(game_dir: Path, started_at: float, exit_code: int | None) -> Diagnosis | None:
    log = game_dir / "logs" / "latest.log"
    reports = game_dir / "crash-reports"
    recent = sorted((path for path in reports.glob("*.txt") if path.is_file() and path.stat().st_mtime >= started_at - 2), key=lambda path: path.stat().st_mtime, reverse=True) if reports.is_dir() else []
    report = recent[0] if recent else None
    fresh_log = log if log.is_file() and log.stat().st_mtime >= started_at - 2 else None
    if exit_code in (None, 0) and report is None:
        return None
    source = report or fresh_log
    content = ""
    if source:
        try:
            with source.open("rb") as stream:
                stream.seek(max(0, source.stat().st_size - 512 * 1024))
                content = stream.read().decode("utf-8", errors="replace")
        except OSError:
            pass
    for pattern, explanation in PATTERNS:
        match = re.search(pattern, content)
        if match:
            return Diagnosis(explanation, match.group(0)[:220], fresh_log, report)
    if report:
        return Diagnosis("Minecraft produced a crash report. The cause is unclear from common signatures.", "Recent crash report", fresh_log, report)
    return Diagnosis(f"Minecraft exited with code {exit_code}. The cause is unclear.", f"Exit code {exit_code}", fresh_log, None)
