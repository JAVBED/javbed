from __future__ import annotations
import json, os, sys
from pathlib import Path

def data_root(application_dir=None, local_app_data=None):
    if application_dir is None:
        application_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    location = Path(application_dir)
    if (location / "portable.txt").is_file():
        return location / "JAVBED-data"
    return Path(local_app_data or os.getenv("LOCALAPPDATA") or (Path.home()/".local"/"share"))/"JAVBED"

ROOT = data_root()
FILE = ROOT/"settings.json"
_applied_env = set()
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
    "story_mode_s1_path": "",
    "story_mode_s2_path": "",
    "game_dungeons_path": "",
    "game_dungeons2_path": "",
    "game_legends_path": "",
    "bedrock_worlds_path": "",
    "edu_worlds_path": "",
    "servli_home": "",
    "server_backup_keep": 10,
    "server_backup_mode": "off",
    "minimize_on_launch": False,
    "theme": "dark",
    "accent_color": "#3c8527",
    "compact_navigation": False,
    "show_artwork": True,
    "startup_page": "Java",
    "show_onboarding": True,
    "onboarding_complete": False,
}
def load():
    data=dict(DEFAULTS)
    try:
        stored=json.loads(FILE.read_text(encoding="utf-8"))
        if isinstance(stored,dict):
            data.update(stored)
            if "onboarding_complete" not in stored:
                data["onboarding_complete"]=True
    except (OSError,ValueError):pass
    return data
def save(data):
    ROOT.mkdir(parents=True,exist_ok=True)
    FILE.write_text(json.dumps(data,indent=2),encoding="utf-8")
def apply_environment(data):
    mapping={"engine_java":"JAVBED_JAVA","engine_bedrock":"JAVBED_BEDROCK","engine_edu":"JAVBED_EDU","engine_lce":"JAVBED_LCE","engine_servers":"JAVBED_SERVERS"}
    for key,env in mapping.items():
        value=str(data.get(key,"")).strip()
        if value:
            os.environ[env]=value
            _applied_env.add(env)
        elif env in _applied_env:
            os.environ.pop(env,None)
            _applied_env.remove(env)
    key=str(data.get("curseforge_api_key","")).strip()
    if key:
        os.environ["CURSEFORGE_API_KEY"]=key
        _applied_env.add("CURSEFORGE_API_KEY")
    elif "CURSEFORGE_API_KEY" in _applied_env:
        os.environ.pop("CURSEFORGE_API_KEY",None)
        _applied_env.remove("CURSEFORGE_API_KEY")
    home = str(data.get("servli_home", "")).strip()
    if home:
        os.environ["SERVLI_HOME"] = home
        _applied_env.add("SERVLI_HOME")
    elif "SERVLI_HOME" in _applied_env:
        os.environ.pop("SERVLI_HOME", None)
        _applied_env.remove("SERVLI_HOME")
