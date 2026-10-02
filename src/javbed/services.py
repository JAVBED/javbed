from __future__ import annotations
import json, os, re, urllib.request, webbrowser
from pathlib import Path
from .engines import ENGINES, ROOT

GITHUB_API="https://api.github.com/repos/{repo}/releases/latest"

def latest_release(repo):
    req=urllib.request.Request(GITHUB_API.format(repo=repo),headers={"Accept":"application/vnd.github+json","User-Agent":"JAVBED"})
    with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)

def engine_status():
    rows=[]
    for label,engine in ENGINES.items():
        path=engine.locate()
        tag=""
        meta=engine.directory/"release.json"
        if meta.exists():
            try:tag=json.loads(meta.read_text(encoding="utf-8")).get("tag","")
            except Exception:pass
        rows.append((label,str(path or ""),tag))
    return rows

def javbed_update(current):
    release=latest_release("JAVBED/javbed")
    tag=release.get("tag_name","")
    def version(value):
        match=re.fullmatch(r"v?(\d+(?:\.\d+)*)",str(value),re.IGNORECASE)
        return tuple(int(part) for part in match.group(1).split(".")) if match else None
    latest, installed = version(tag), version(current)
    width=max(len(latest or ()),len(installed or ()))
    newer=bool(latest and installed and latest+(0,)*(width-len(latest)) > installed+(0,)*(width-len(installed)))
    return tag, newer, release.get("html_url","")

def open_url(url):
    if url:webbrowser.open(url)
