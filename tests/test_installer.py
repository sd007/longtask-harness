from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "goal-flow" / "scripts"))
import plugin_manager  # noqa: E402


INSTALL = ROOT / "goal-flow" / "scripts" / "install.py"
UNINSTALL = ROOT / "goal-flow" / "scripts" / "uninstall.py"
INSTALL_WRAPPER = ROOT / "install.sh"
UNINSTALL_WRAPPER = ROOT / "uninstall.sh"


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        marketplace = self.home / ".agents" / "plugins" / "marketplace.json"
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(json.dumps({
            "name": "personal",
            "interface": {"displayName": "My Plugins"},
            "plugins": [{
                "name": "keep-me",
                "source": {"source": "local", "path": "./plugins/keep-me"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }],
        }), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), "--home", str(self.home), "--no-codex", *args],
            text=True, capture_output=True, check=False,
        )

    def marketplace(self) -> dict:
        path = self.home / ".agents" / "plugins" / "marketplace.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_install_merges_marketplace_and_copies_plugin(self) -> None:
        result = self.run_script(INSTALL, "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / "plugins" / "goal-flow" / ".codex-plugin" / "plugin.json").exists())
        self.assertTrue((self.home / "plugins" / "goal-flow" / ".mcp.json").exists())
        installed_manifest = json.loads(
            (self.home / "plugins" / "goal-flow" / ".codex-plugin" / "plugin.json").read_text()
        )
        self.assertTrue(installed_manifest["version"].startswith("0.11.0+codex.local-"))
        self.assertEqual(installed_manifest["mcpServers"], "./.mcp.json")
        mcp = json.loads((self.home / "plugins" / "goal-flow" / ".mcp.json").read_text())
        approval = mcp["mcpServers"]["goal-flow-approval"]
        self.assertEqual(approval["args"], ["-u", "./mcp/approval_server.py"])
        self.assertEqual(approval["cwd"], ".")
        self.assertEqual([item["name"] for item in self.marketplace()["plugins"]], ["keep-me", "goal-flow"])

    def test_bundled_mcp_configuration_completes_real_initialize_handshake(self) -> None:
        plugin_manager.validate_mcp_server(ROOT / "goal-flow")

    def test_dry_run_changes_nothing(self) -> None:
        before = self.marketplace()
        result = self.run_script(INSTALL, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / "plugins" / "goal-flow").exists())
        self.assertEqual(self.marketplace(), before)

    def test_interactive_install_offers_codex_hook_setup(self) -> None:
        args = Namespace(setup_hooks=True, no_hooks=False, no_codex=False)
        with (
            patch.object(plugin_manager.sys.stdin, "isatty", return_value=True),
            patch.object(plugin_manager.sys.stdout, "isatty", return_value=True),
            patch("builtins.input", return_value="y"),
            patch("plugin_manager.subprocess.run") as run,
        ):
            run.return_value.returncode = 0
            plugin_manager.offer_hook_setup(args)
        run.assert_called_once_with(["codex"], cwd=Path.cwd(), check=False)

    def test_one_command_wrappers_install_and_uninstall(self) -> None:
        self.assertTrue(os.access(INSTALL_WRAPPER, os.X_OK))
        self.assertTrue(os.access(UNINSTALL_WRAPPER, os.X_OK))
        installed = subprocess.run(
            [str(INSTALL_WRAPPER), "--home", str(self.home), "--no-codex"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        plugin = self.home / "plugins" / "goal-flow"
        self.assertTrue((plugin / "install.sh").exists())
        self.assertTrue((plugin / "uninstall.sh").exists())

        removed = subprocess.run(
            [str(UNINSTALL_WRAPPER), "--home", str(self.home), "--no-codex"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(plugin.exists())

    def test_installed_plugin_can_uninstall_itself(self) -> None:
        installed = subprocess.run(
            [str(INSTALL_WRAPPER), "--home", str(self.home), "--no-codex"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        plugin = self.home / "plugins" / "goal-flow"
        installed_uninstaller = plugin / "uninstall.sh"
        self.assertTrue(os.access(installed_uninstaller, os.X_OK))

        removed = subprocess.run(
            [str(installed_uninstaller), "--home", str(self.home), "--no-codex"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(plugin.exists())

    def test_uninstall_preserves_other_entries_and_is_recoverable(self) -> None:
        self.assertEqual(self.run_script(INSTALL, "--yes").returncode, 0)
        result = self.run_script(UNINSTALL, "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([item["name"] for item in self.marketplace()["plugins"]], ["keep-me"])
        self.assertFalse((self.home / "plugins" / "goal-flow").exists())
        recovered = list((self.home / ".goal-flow-uninstalled").glob("goal-flow-*"))
        self.assertEqual(len(recovered), 1)
        self.assertTrue((recovered[0] / ".codex-plugin" / "plugin.json").exists())

    def test_reinstall_replaces_entry_without_duplicates(self) -> None:
        self.assertEqual(self.run_script(INSTALL, "--yes").returncode, 0)
        self.assertEqual(self.run_script(INSTALL, "--yes").returncode, 0)
        names = [item["name"] for item in self.marketplace()["plugins"]]
        self.assertEqual(names.count("goal-flow"), 1)
        self.assertFalse(list((self.home / "plugins").glob("goal-flow.backup-*")))

    def test_invalid_marketplace_is_never_overwritten(self) -> None:
        path = self.home / ".agents" / "plugins" / "marketplace.json"
        path.write_text("{invalid", encoding="utf-8")
        result = self.run_script(INSTALL, "--yes")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(path.read_text(encoding="utf-8"), "{invalid")
        self.assertFalse((self.home / "plugins" / "goal-flow").exists())

    def test_failed_codex_install_restores_previous_plugin_and_marketplace(self) -> None:
        self.assertEqual(self.run_script(INSTALL, "--yes").returncode, 0)
        destination = self.home / "plugins" / "goal-flow"
        marker = destination / "previous-install.txt"
        marker.write_text("keep this version\n", encoding="utf-8")
        marketplace_before = self.marketplace()

        fake_bin = self.home / "fake-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        fake_codex.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"
        result = subprocess.run(
            [sys.executable, str(INSTALL), "--home", str(self.home), "--yes"],
            text=True, capture_output=True, check=False, env=environment,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep this version\n")
        self.assertEqual(self.marketplace(), marketplace_before)
        self.assertFalse(list((self.home / "plugins").glob("goal-flow.backup-*")))

    def test_failed_mcp_check_restores_previous_plugin_and_marketplace(self) -> None:
        self.assertEqual(self.run_script(INSTALL, "--yes").returncode, 0)
        destination = self.home / "plugins" / "goal-flow"
        marker = destination / "previous-install.txt"
        marker.write_text("keep this version\n", encoding="utf-8")
        marketplace_before = self.marketplace()
        args = Namespace(
            home=str(self.home),
            no_codex=True,
            yes=True,
            dry_run=False,
            setup_hooks=False,
            no_hooks=True,
        )

        with patch.object(
            plugin_manager,
            "validate_mcp_server",
            side_effect=plugin_manager.InstallError("broken MCP"),
        ):
            with self.assertRaises(plugin_manager.InstallError):
                plugin_manager.install(args)

        self.assertEqual(marker.read_text(encoding="utf-8"), "keep this version\n")
        self.assertEqual(self.marketplace(), marketplace_before)
        self.assertFalse(list((self.home / "plugins").glob("goal-flow.backup-*")))


if __name__ == "__main__":
    unittest.main()
