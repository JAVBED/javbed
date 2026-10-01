import json
import tempfile
import unittest
from pathlib import Path

from javbed.launcher_imports import default_roots, discover, inspect


class LauncherImportTests(unittest.TestCase):
    def test_detects_prism_curseforge_and_official_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prism = root / "Prism" / "instances" / "Survival"
            prism.mkdir(parents=True)
            (prism / "instance.cfg").write_text("name=Survival\n", encoding="utf-8")
            (prism / "mmc-pack.json").write_text(json.dumps({"components": [{"uid": "net.minecraft", "version": "1.21.1"}, {"uid": "net.fabricmc.fabric-loader", "version": "0.16"}]}), encoding="utf-8")
            curse = root / "Curse" / "Instances" / "Pack"
            curse.mkdir(parents=True)
            (curse / "minecraftinstance.json").write_text(json.dumps({"name": "Pack", "gameVersion": "1.20.1", "baseModLoader": {"name": "forge-47"}}), encoding="utf-8")
            vanilla = root / ".minecraft"
            (vanilla / "versions").mkdir(parents=True)
            (vanilla / "assets").mkdir()
            (vanilla / "launcher_profiles.json").write_text(json.dumps({"selectedProfile": "p", "profiles": {"p": {"lastVersionId": "1.21.8"}}}), encoding="utf-8")
            rows = discover(roots=[("Prism Launcher", prism.parent), ("CurseForge", curse.parent), ("Official Minecraft Launcher", vanilla)])
            self.assertEqual({item.version for item in rows}, {"1.21.1", "1.20.1", "1.21.8"})
            self.assertEqual(inspect(prism).loader, "fabric")
            self.assertEqual(inspect(curse).loader, "forge")

    def test_default_roots_include_all_requested_launchers(self):
        roots = default_roots(Path("C:/Users/example"), "win32", Path("C:/Users/example/AppData/Roaming"))
        self.assertEqual({name for name, _ in roots}, {"Official Minecraft Launcher", "Prism Launcher", "MultiMC", "Modrinth App", "CurseForge"})


if __name__ == "__main__":
    unittest.main()
