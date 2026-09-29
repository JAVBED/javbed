from __future__ import annotations
import os, shutil
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Engine:
    label: str
    project: str
    env_var: str
    candidates: tuple[str, ...]

    def locate(self) -> Path | None:
        configured = os.getenv(self.env_var)
        if configured:
            path = Path(configured).expanduser()
            if path.exists(): return path
        for candidate in self.candidates:
            found = shutil.which(candidate)
            if found: return Path(found)
        return None

    def command(self, *args: str) -> tuple[list[str] | None, str | None]:
        exe = self.locate()
        if not exe:
            return None, f"{self.label} engine not found. Set {self.env_var} or add {self.project} to PATH."
        return [str(exe), *args], None

ENGINES = {
    "Java": Engine("Java", "javli", "JAVBED_JAVA", ("javli", "javli.exe")),
    "Bedrock": Engine("Bedrock", "bedli", "JAVBED_BEDROCK", ("bedli", "bedli.exe")),
    "EDU": Engine("EDU", "eduli", "JAVBED_EDU", ("eduli", "eduli.exe")),
    "LCE": Engine("LCE", "legli", "JAVBED_LCE", ("legli", "legli.exe")),
    "Servers": Engine("Servers", "servli", "JAVBED_SERVERS", ("servli", "servli.exe")),
}
