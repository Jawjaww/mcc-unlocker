#!/usr/bin/env python3
"""Fetch pinned community unlock assets locally (never into the repo).

The community repository does not declare a redistribution license. The script
therefore stores the files under the user's data directory and requires an
explicit acknowledgement. It verifies size and SHA-256 before an atomic rename.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "assets" / "unlock" / "provenance.json"


def load_provenance() -> dict:
    return json.loads(PROVENANCE.read_text(encoding="utf-8"))


def check_only() -> int:
    data = load_provenance()
    print("Assets épinglés (non téléchargés) :")
    for name, entry in sorted(data["files"].items()):
        print(f"  {name}: {entry['size_bytes']} octets — {entry['sha256']}")
        print(f"    licence: {entry['license']}; redistribuable: {entry['redistributable']}")
    print(f"Commit source : {data['commit']}")
    return 0


def vendored_repo() -> Path | None:
    candidate = ROOT / "vendor" / "Monsieur-Cuisine-Connect-Hack"
    return candidate if (candidate / "hacks" / "recovery.img").is_file() else None


def copy_from_repo(source: Path, destination: Path, *, expected_size: int, expected_sha256: str) -> None:
    if destination.exists():
        raise FileExistsError(f"refus d'écraser {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".part", dir=destination.parent)
    tmp_path = Path(temporary)
    try:
        with open(source, "rb") as src, os.fdopen(fd, "wb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        data = tmp_path.read_bytes()
        if len(data) != expected_size:
            raise ValueError(f"taille inattendue: {len(data)} != {expected_size}")
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected_sha256:
            raise ValueError(f"SHA-256 inattendu: {actual} != {expected_sha256}")
        os.replace(tmp_path, destination)
    finally:
        tmp_path.unlink(missing_ok=True)


def download(url: str, destination: Path, *, expected_size: int, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".part", dir=destination.parent)
    tmp_path = Path(temporary)
    digest = hashlib.sha256()
    size = 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MCC-Unlocker-asset-fetcher/1"})
        with urllib.request.urlopen(req, timeout=60) as response, os.fdopen(fd, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if size != expected_size:
            raise ValueError(f"taille inattendue: {size} != {expected_size}")
        if digest.hexdigest() != expected_sha256:
            raise ValueError(f"SHA-256 inattendu: {digest.hexdigest()} != {expected_sha256}")
        if destination.exists():
            raise FileExistsError(f"refus d'écraser {destination}")
        os.replace(tmp_path, destination)
    finally:
        tmp_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-provenance", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--download", action="store_true", help="ignorer le dépôt vendor et télécharger")
    parser.add_argument("--dest", type=Path, default=Path.home() / ".mcc-unlocker" / "assets")
    args = parser.parse_args(argv)
    if args.check_only:
        return check_only()
    if not args.accept_provenance:
        print(
            "Refus : ces assets viennent d'un dépôt communautaire sans licence de "
            "redistribution déclarée. Relance avec --accept-provenance après avoir "
            "vérifié la provenance.",
            file=sys.stderr,
        )
        return 2
    data = load_provenance()
    repo = None if args.download else vendored_repo()
    print(f"Source : {data['source_repo']} @ {data['commit']}")
    print("Licence non déclarée : les fichiers restent locaux et ne sont pas redistribués.")
    sources = {
        "twrp_recovery.img": repo / "hacks" / "recovery.img" if repo else None,
        "l706_dfbh_v_695scatter.txt": repo / "informations" / "l706_dfbh_v_695scatter.txt" if repo else None,
    }
    for name, entry in sorted(data["files"].items()):
        destination = args.dest.expanduser() / name
        print(f"Récupération de {name} → {destination}")
        try:
            source = sources.get(name)
            if source is not None:
                copy_from_repo(
                    source,
                    destination,
                    expected_size=int(entry["size_bytes"]),
                    expected_sha256=str(entry["sha256"]),
                )
            else:
                download(
                    entry["url"],
                    destination,
                    expected_size=int(entry["size_bytes"]),
                    expected_sha256=str(entry["sha256"]),
                )
        except Exception as exc:  # noqa: BLE001
            print(f"Échec {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(f"  OK {name} ({entry['size_bytes']} octets, SHA-256 vérifié)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
