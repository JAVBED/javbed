from __future__ import annotations

import os
import shutil
import subprocess
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

    def launch(self) -> tuple[bool, str]:
        executable = self.locate()
        if not executable:
            return False, f"{self.label} engine is not installed yet. Set {self.env_var} to its executable, or add it to PATH."
        try:
            subprocess.Popen([str(executable)], cwd=str(executable.parent))
            return True, f"Started {self.label}."
        except OSError as exc:
            return False, f"Could not start {self.label}: {exc}"

ENGINES = {
    "Java": Engine("Java", "javli", "JAVBED_JAVA", ("javli", "javli.exe")),
    "Bedrock": Engine("Bedrock", "bedli", "JAVBED_BEDROCK", ("bedli", "bedli.exe")),
    "EDU": Engine("EDU", "eduli", "JAVBED_EDU", ("eduli", "eduli.exe")),
    "LCE": Engine("LCE", "legli", "JAVBED_LCE", ("legli", "legli.exe")),
    "Servers": Engine("Servers", "servli", "JAVBED_SERVERS", ("servli", "servli.exe")),
}
