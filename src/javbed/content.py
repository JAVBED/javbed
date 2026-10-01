"""Provider search and compatibility data for Java add-ons."""

from __future__ import annotations

import json
import tempfile
import zipfile
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

MODRINTH = "https://api.modrinth.com/v2"
CURSEFORGE = "https://api.curseforge.com/v1"
CURSEFORGE_GAME = 432
CURSEFORGE_CLASSES = {"mod": 6, "modpack": 4471}
CURSEFORGE_LOADERS = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}


def _get(url: str, key: str = ""):
    headers = {"Accept": "application/json", "User-Agent": "JAVBED/0.1 (+https://github.com/JAVBED/javbed)"}
    if key:
        headers["x-api-key"] = key
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        return json.load(response)


def search(provider: str, kind: str, query: str, minecraft: str = "", loader: str = "", api_key: str = "") -> list[dict]:
    if provider == "modrinth":
        facets = [[f"project_type:{kind}"]]
        if minecraft:
            facets.append([f"versions:{minecraft}"])
        if loader and kind in ("mod", "modpack") and loader != "vanilla":
            facets.append([f"categories:{loader}"])
        url = MODRINTH + "/search?" + urlencode({"query": query, "limit": 20, "facets": json.dumps(facets)})
        hits = _get(url).get("hits", [])
        return [{"provider": provider, "kind": kind, "id": str(hit.get("project_id", "")), "slug": str(hit.get("slug", "")), "name": hit.get("title", ""), "author": hit.get("author", ""), "description": hit.get("description", ""), "downloads": hit.get("downloads", 0), "versions": hit.get("versions", []), "loaders": hit.get("categories", []), "icon": hit.get("icon_url", "")} for hit in hits]
    if provider == "curseforge" and kind in CURSEFORGE_CLASSES:
        if not api_key:
            raise ValueError("Configure a CurseForge API key in Settings first.")
        params = {"gameId": CURSEFORGE_GAME, "classId": CURSEFORGE_CLASSES[kind], "searchFilter": query, "pageSize": 20, "sortField": 2, "sortOrder": "desc"}
        if minecraft:
            params["gameVersion"] = minecraft
        if loader in CURSEFORGE_LOADERS and minecraft and kind == "mod":
            params["modLoaderType"] = CURSEFORGE_LOADERS[loader]
        hits = _get(CURSEFORGE + "/mods/search?" + urlencode(params), api_key).get("data", [])
        return [{"provider": provider, "kind": kind, "id": str(hit.get("id", "")), "slug": str(hit.get("slug", "")), "name": hit.get("name", ""), "author": ", ".join(value.get("name", "") for value in hit.get("authors", [])), "description": hit.get("summary", ""), "downloads": hit.get("downloadCount", 0), "versions": sorted({value.get("gameVersion", "") for value in hit.get("latestFilesIndexes", []) if value.get("gameVersion")}), "loaders": [], "icon": (hit.get("logo") or {}).get("thumbnailUrl", "")} for hit in hits]
    raise ValueError(f"{provider} does not support {kind} browsing.")


def compatible_versions(provider: str, kind: str, project: str, minecraft: str, loader: str = "", api_key: str = "") -> list[dict]:
    if not minecraft:
        raise ValueError("Choose an instance with a Minecraft version.")
    if provider == "modrinth":
        params = {"game_versions": json.dumps([minecraft]), "include_changelog": "false"}
        if loader and loader != "vanilla" and kind in ("mod", "modpack"):
            params["loaders"] = json.dumps([loader])
        url = MODRINTH + "/project/" + quote(project, safe="") + "/version?" + urlencode(params)
        rows = _get(url)
        return [row for row in rows if row.get("status", "listed") == "listed" and minecraft in row.get("game_versions", []) and (kind not in ("mod", "modpack") or loader == "vanilla" or loader in row.get("loaders", []))]
    if provider == "curseforge" and kind in CURSEFORGE_CLASSES:
        if not api_key:
            raise ValueError("Configure a CurseForge API key in Settings first.")
        params = {"gameVersion": minecraft, "pageSize": 50}
        if loader in CURSEFORGE_LOADERS and kind == "mod":
            params["modLoaderType"] = CURSEFORGE_LOADERS[loader]
        url = CURSEFORGE + "/mods/" + quote(project, safe="") + "/files?" + urlencode(params)
        rows = _get(url, api_key).get("data", [])
        return [row for row in rows if minecraft in row.get("gameVersions", [])]
    raise ValueError(f"{provider} does not support {kind} installation.")


def newest_compatible(provider: str, kind: str, project: str, minecraft: str, loader: str = "", api_key: str = "") -> dict | None:
    rows = compatible_versions(provider, kind, project, minecraft, loader, api_key)
    if not rows:
        return None
    if provider == "modrinth":
        rows.sort(key=lambda row: (row.get("version_type") == "release", row.get("date_published", "")), reverse=True)
    else:
        rows.sort(key=lambda row: row.get("fileDate", ""), reverse=True)
    row = rows[0]
    if provider == "modrinth":
        files = row.get("files", [])
        primary = next((item for item in files if item.get("primary")), files[0] if files else {})
        return {"id": str(row.get("id", "")), "version": row.get("version_number", ""), "file_name": primary.get("filename", ""), "dependencies": row.get("dependencies", []), "raw": row}
    return {"id": str(row.get("id", "")), "version": row.get("displayName", ""), "file_name": row.get("fileName", ""), "dependencies": row.get("dependencies", []), "raw": row}


def curseforge_pack_requirements(project: str, file: dict, api_key: str) -> tuple[str, str, str]:
    if not api_key:
        raise ValueError("Configure a CurseForge API key in Settings first.")
    raw = file["raw"]
    url = raw.get("downloadUrl") or _get(CURSEFORGE + "/mods/" + quote(project, safe="") + "/files/" + quote(file["id"], safe="") + "/download-url", api_key)
    if isinstance(url, dict):
        url = url.get("data")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("CurseForge does not expose an automatic download URL for this pack.")
    with tempfile.TemporaryFile() as temporary, urlopen(Request(url, headers={"User-Agent": "JAVBED"}), timeout=90) as response:
        while chunk := response.read(1024 * 1024):
            temporary.write(chunk)
        temporary.seek(0)
        with zipfile.ZipFile(temporary) as archive:
            manifest = json.loads(archive.read("manifest.json"))
    minecraft = str((manifest.get("minecraft") or {}).get("version") or "")
    loaders = (manifest.get("minecraft") or {}).get("modLoaders") or []
    loader_id = str(next((entry.get("id", "") for entry in loaders if entry.get("primary")), loaders[0].get("id", "") if loaders else ""))
    loader, _, loader_version = loader_id.partition("-")
    return minecraft, loader.lower() or "vanilla", loader_version
