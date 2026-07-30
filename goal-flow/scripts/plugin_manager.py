#!/usr/bin/env python3
"""Safe personal-marketplace installer for the Goal Flow plugin."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLUGIN_NAME = "goal-flow"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class InstallError(RuntimeError):
    pass


def personal_paths(home: Path) -> tuple[Path, Path]:
    return home / "plugins" / PLUGIN_NAME, home / ".agents" / "plugins" / "marketplace.json"


def read_marketplace(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "name": "personal",
            "interface": {"displayName": "Personal"},
            "plugins": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstallError(f"Invalid marketplace JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("plugins"), list):
        raise InstallError(f"Marketplace must contain a plugins array: {path}")
    if not payload.get("name"):
        raise InstallError(f"Marketplace has no name: {path}")
    payload.setdefault("interface", {"displayName": "Personal"})
    return payload


def plugin_entry() -> dict[str, Any]:
    return {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity",
    }


def merge_entry(marketplace: dict[str, Any]) -> dict[str, Any]:
    plugins = marketplace["plugins"]
    replacement = plugin_entry()
    for index, item in enumerate(plugins):
        if item.get("name") == PLUGIN_NAME:
            plugins[index] = replacement
            break
    else:
        plugins.append(replacement)
    return marketplace


def remove_entry(marketplace: dict[str, Any]) -> dict[str, Any]:
    marketplace["plugins"] = [
        item for item in marketplace["plugins"] if item.get("name") != PLUGIN_NAME
    ]
    return marketplace


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def copy_plugin(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def add_cachebuster(plugin_path: Path) -> None:
    manifest_path = plugin_path / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_version = str(manifest.get("version") or "0.1.0").split("+", 1)[0]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    manifest["version"] = f"{base_version}+codex.local-{stamp}"
    atomic_write_json(manifest_path, manifest)


def run_codex(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["codex", *args], text=True, capture_output=True, check=False
    )


def confirm(message: str, assume_yes: bool) -> None:
    if assume_yes:
        return
    response = input(f"{message} [y/N] ").strip().lower()
    if response not in {"y", "yes"}:
        raise InstallError("Cancelled; no changes were made")


def offer_hook_setup(args: argparse.Namespace) -> None:
    """Offer an interactive Codex session for the user-owned hook trust step."""
    if (
        not getattr(args, "setup_hooks", False)
        or getattr(args, "no_hooks", False)
        or getattr(args, "no_codex", False)
    ):
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Hook setup deferred: run codex, then type /hooks in the Codex CLI.")
        return
    print(
        "\nGoal Flow needs you to review and trust the SessionStart and Stop hooks.\n"
        "The installer cannot click Trust for you; it will open the Codex CLI now."
    )
    response = input("Open Codex CLI for hook setup now? [Y/n] ").strip().lower()
    if response not in {"", "y", "yes"}:
        print("Hook setup skipped. Later run `codex`, then type `/hooks`.")
        return
    print("Opening Codex CLI. In Codex, type `/hooks`, review both Goal Flow hooks, and choose Trust.")
    try:
        result = subprocess.run(["codex"], cwd=Path.cwd(), check=False)
    except KeyboardInterrupt:
        print("\nHook setup interrupted. Run `codex`, then type `/hooks` when ready.")
        return
    if result.returncode == 0:
        print("Codex CLI closed. Start a new Codex task after both hooks show as trusted.")
    else:
        print(f"Codex CLI exited with status {result.returncode}. Hook setup may still be incomplete.")


def install(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser().resolve()
    destination, marketplace_path = personal_paths(home)
    marketplace = merge_entry(read_marketplace(marketplace_path))
    marketplace_name = str(marketplace["name"])
    same_source = destination.exists() and destination.resolve() == PLUGIN_ROOT
    actions = [
        f"Copy plugin to {destination}" if not same_source else f"Use plugin at {destination}",
        f"Merge entry into {marketplace_path}",
    ]
    if not args.no_codex:
        actions.append(f"Run codex plugin add {PLUGIN_NAME}@{marketplace_name}")
    print("Goal Flow install plan:\n- " + "\n- ".join(actions))
    if args.dry_run:
        return 0
    if not args.no_codex and shutil.which("codex") is None:
        raise InstallError("codex CLI was not found; install Codex or use --no-codex for source-only setup")
    confirm("Continue with installation?", args.yes)

    old_marketplace = marketplace_path.read_bytes() if marketplace_path.exists() else None
    backup: Path | None = None
    staging_parent = destination.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".goal-flow-install-", dir=staging_parent)) / PLUGIN_NAME
    try:
        if not same_source:
            copy_plugin(PLUGIN_ROOT, staging)
            add_cachebuster(staging)
            if destination.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                backup = destination.with_name(f"{PLUGIN_NAME}.backup-{stamp}")
                destination.replace(backup)
            staging.replace(destination)
        atomic_write_json(marketplace_path, marketplace)
        if not args.no_codex:
            result = run_codex("plugin", "add", f"{PLUGIN_NAME}@{marketplace_name}", "--json")
            if result.returncode != 0:
                raise InstallError(result.stderr.strip() or result.stdout.strip() or "codex plugin add failed")
        if backup and backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if not same_source and destination.exists():
            shutil.rmtree(destination)
        if backup and backup.exists():
            backup.replace(destination)
        if old_marketplace is None:
            marketplace_path.unlink(missing_ok=True)
        else:
            marketplace_path.write_bytes(old_marketplace)
        raise
    finally:
        if staging.parent.exists():
            shutil.rmtree(staging.parent)

    print("Goal Flow installed successfully.")
    if not getattr(args, "setup_hooks", False):
        print("Next: run `codex`, type `/hooks`, trust the two Goal Flow hooks, then start a new task.")
    offer_hook_setup(args)
    return 0


def recovery_destination(home: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    trash = home / ".Trash"
    parent = trash if trash.exists() else home / ".goal-flow-uninstalled"
    return parent / f"{PLUGIN_NAME}-{stamp}"


def uninstall(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser().resolve()
    destination, marketplace_path = personal_paths(home)
    marketplace = read_marketplace(marketplace_path)
    marketplace_name = str(marketplace["name"])
    recovery = recovery_destination(home) if destination.exists() and not args.purge else None
    actions = [f"Remove {PLUGIN_NAME} from {marketplace_path}"]
    if destination.exists():
        actions.append(
            f"Delete {destination}" if args.purge else f"Move {destination} to {recovery}"
        )
    if not args.no_codex:
        actions.insert(0, f"Run codex plugin remove {PLUGIN_NAME}@{marketplace_name}")
    print("Goal Flow uninstall plan:\n- " + "\n- ".join(actions))
    print("Project .goal-flow/ audit directories will not be touched.")
    if args.dry_run:
        return 0
    if not args.no_codex and shutil.which("codex") is None:
        raise InstallError("codex CLI was not found; use --no-codex only if the plugin is not installed in Codex")
    confirm("Continue with uninstall?", args.yes)

    if not args.no_codex:
        result = run_codex("plugin", "remove", f"{PLUGIN_NAME}@{marketplace_name}", "--json")
        if result.returncode != 0:
            print(
                "Warning: Codex did not report an installed plugin; continuing local cleanup: "
                + (result.stderr.strip() or result.stdout.strip()),
                file=sys.stderr,
            )
    atomic_write_json(marketplace_path, remove_entry(marketplace))
    if destination.exists():
        if args.purge:
            shutil.rmtree(destination)
        else:
            assert recovery is not None
            recovery.parent.mkdir(parents=True, exist_ok=True)
            destination.replace(recovery)
    print("Goal Flow uninstalled successfully.")
    if recovery:
        print(f"Plugin files remain recoverable at: {recovery}")
    return 0


def build_parser(action: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{action.title()} Goal Flow")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without changing files")
    if action == "install":
        parser.add_argument("--setup-hooks", action="store_true", help=argparse.SUPPRESS)
        parser.add_argument("--no-hooks", action="store_true", help="Skip the interactive Hook setup prompt")
    parser.add_argument("--home", default=str(Path.home()), help=argparse.SUPPRESS)
    parser.add_argument("--no-codex", action="store_true", help=argparse.SUPPRESS)
    if action == "uninstall":
        parser.add_argument("--purge", action="store_true", help="Permanently delete plugin files")
    return parser


def main(action: str) -> int:
    args = build_parser(action).parse_args()
    try:
        return install(args) if action == "install" else uninstall(args)
    except (InstallError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
