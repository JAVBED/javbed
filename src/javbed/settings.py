from __future__ import annotations
import json, os
from pathlib import Path

ROOT = Path(os.getenv("LOCALAPPDATA") or (Path.home()/".local"/"share"))/"JAVBED"
FILE = ROOT/"settings.json"
DEFAULTS = {
    "java_memory_mb": 4096,
    "resolution_width": 1280,
    "resolution_height": 720,
    "fullscreen": False,
    "close_on_launch": False,
    "check_updates": True,
    "curseforge_api_key": "",
    "minecraft_directory": "",
    "java_runtime": "",
    "engine_java": "",
    "engine_bedrock": "",
    "engine_edu": "",
    "engine_lce": "",
    "engine_servers": "",
}
def load():
    data=dict(DEFAULTS)
    try:data.update(json.loads(FILE.read_text(encoding="utf-8")))
    except (OSError,ValueError):pass
    return data
def save(data):
    ROOT.mkdir(parents=True,exist_ok=True)
    FILE.write_text(json.dumps(data,indent=2),encoding="utf-8")
def apply_environment(data):
    mapping={"engine_java":"JAVBED_JAVA","engine_bedrock":"JAVBED_BEDROCK","engine_edu":"JAVBED_EDU","engine_lce":"JAVBED_LCE","engine_servers":"JAVBED_SERVERS"}
    for key,env in mapping.items():
        value=str(data.get(key,"")).strip()
        if value:os.environ[env]=value
    key=str(data.get("curseforge_api_key","")).strip()
    if key:os.environ["CURSEFORGE_API_KEY"]=key
