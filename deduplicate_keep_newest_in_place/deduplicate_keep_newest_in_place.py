#!/usr/bin/env python3
import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def unique_destination(base_dir: Path, filename: str) -> Path:
    """
    Vrátí volnou cestu v base_dir (při kolizi přidá ' (1)', ' (2)', ...).
    """
    candidate = base_dir / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    i = 1
    while True:
        candidate = base_dir / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1

def remove_empty_dirs(root: Path, keep: List[Path]):
    """
    Smaže prázdné podadresáře pod root (bottom-up), kromě adresářů v `keep` a samotného rootu.
    """
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        p = Path(dirpath)
        if p == root or any(p.resolve() == k.resolve() for k in keep):
            continue
        try:
            if not any(p.iterdir()):
                p.rmdir()
                print(f"🧹 Removed empty directory: {p}")
        except Exception as e:
            print(f"⚠️  Could not remove {p}: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Najdi obsahové duplikáty v Hlavní složce, ponech nejnovější na místě a ostatní přesuň do 'Duplikáty/'."
    )
    parser.add_argument("main_dir", type=str, help="Cesta k Hlavní složce")
    parser.add_argument("--dry-run", action="store_true", help="Neprovádět změny, jen vypsat plán")
    parser.add_argument("--follow-symlinks", action="store_true", help="Následovat symlinky (default: ne)")
    args = parser.parse_args()

    main_dir = Path(args.main_dir).expanduser().resolve()
    if not main_dir.exists() or not main_dir.is_dir():
        print("❌ Zadaná Hlavní složka neexistuje nebo není adresář.")
        sys.exit(1)

    duplicates_dir = main_dir / "Duplikáty"
    if not args.dry_run:
        duplicates_dir.mkdir(exist_ok=True)

    # Projít všechny soubory mimo 'Duplikáty'
    print(f"📁 Scanning: {main_dir}")
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(main_dir, followlinks=args.follow_symlinks):
        # Vynecháme 'Duplikáty' z průchodu
        dirnames[:] = [d for d in dirnames if (Path(dirpath) / d).resolve() != duplicates_dir.resolve()]
        for name in filenames:
            p = Path(dirpath) / name
            try:
                if not p.is_file():
                    continue
                files.append(p)
            except Exception:
                continue

    # Hashování souborů
    print(f"🔎 Hashing {len(files)} files (SHA-256)...")
    by_hash: Dict[str, List[Path]] = {}
    for i, fpath in enumerate(files, 1):
        try:
            file_hash = sha256_of_file(fpath)
        except Exception as e:
            print(f"⚠️  Skip (cannot hash) {fpath}: {e}")
            continue
        by_hash.setdefault(file_hash, []).append(fpath)
        if i % 50 == 0 or i == len(files):
            print(f"  ... {i}/{len(files)} hashed", end="\r")
    print()

    # Akce: pro každý hash ponechat nejnovější na místě, ostatní přesunout do Duplikáty/relativní/cesta
    actions: List[Tuple[Path, Path]] = []  # (src, dst) pro přesun duplicit
    kept: List[Path] = []

    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except Exception:
            return -1.0

    for file_hash, paths in by_hash.items():
        if not paths:
            continue
        if len(paths) == 1:
            # Unikát – nic nepřesouvat
            kept.append(paths[0])
            continue

        # Vyber nejnovější podle mtime
        newest = max(paths, key=mtime)
        max_m = mtime(newest)
        # Tie-breaker: pokud shodné mtime, preferuj kratší cestu (deterministické)
        ties = [p for p in paths if abs(mtime(p) - max_m) < 1e-6]
        if len(ties) > 1:
            newest = sorted(ties, key=lambda p: (len(str(p)), str(p)))[0]

        kept.append(newest)

        # Zbývající přesunout do Duplikáty
        for p in paths:
            if p == newest:
                continue
            rel = p.resolve().relative_to(main_dir.resolve())
            dst_parent = (duplicates_dir / rel).parent
            if not args.dry_run:
                dst_parent.mkdir(parents=True, exist_ok=True)
            dst_final = (duplicates_dir / rel)
            if dst_final.exists():
                dst_final = unique_destination(dst_parent, p.name)
            actions.append((p, dst_final))

    # Shrnutí
    total_dups = len(actions)
    print(f"📊 Groups with duplicates: {sum(1 for v in by_hash.values() if len(v) > 1)}")
    print(f"✔️  Kept in place: {len(kept)} files (one per content group)")
    print(f"↪️  To move to 'Duplikáty': {total_dups} files")

    # Proveď přesuny
    for src, dst in actions:
        print(f"↪️  {src}  ➜  {dst}")
        if not args.dry_run:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
            except Exception as e:
                print(f"❌ Move failed for {src} -> {dst}: {e}")

    # Smazat prázdné složky (kromě kořene a 'Duplikáty')
    if not args.dry_run:
        remove_empty_dirs(main_dir, keep=[duplicates_dir])

    print("✅ Hotovo." if not args.dry_run else "📝 Dry-run dokončen (žádné změny neprovedeny).")

if __name__ == "__main__":
    main()
