#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
move_unique_from_older.py

Funkce:
- Porovnává OBSAH (SHA-256) Hlavní a Starší složky.
- Běžné soubory, které jsou NAVÍC ve Starší (jejich obsah není v Hlavní), přesune do Cílové (se zachováním struktury).
- SYMLINKY ze Starší přesune vždy do Čtvrté složky pro symlinky (se zachováním struktury), bez ohledu na existenci v Hlavní.
- Při kolizi názvu přidá sufix ` (n)` před příponu.
- Umí DRY-RUN (výchozí) a APPLY (`--apply`).
- Po přesunech smaže prázdné adresáře ve Starší (lze vypnout).
- Zobrazuje průběh a ETA.
- Loguje do souboru (parametr `--log-file`) a stručně do konzole.

Použití (příklad):
    python3 move_unique_from_older.py \
        --main "/PATH/TO/Hlavni" \
        --older "/PATH/TO/Starsi" \
        --dest "/PATH/TO/Cilova" \
        --symlinks-dest "/PATH/TO/Symlinky" \
        --log-file "/PATH/TO/move.log" \
        --apply
"""

import argparse
import hashlib
import logging
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Iterable, Iterator, Tuple, List, Set

CHUNK_SIZE = 1024 * 1024  # 1 MiB
PROGRESS_UPDATE_INTERVAL = 0.5  # s


# ---------- Logging helpers ----------

def setup_logging(log_file: Path, verbose: bool) -> logging.Logger:
    logger = logging.getLogger("mover")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)  # vše do souboru
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO if verbose else logging.WARNING)  # stručně do konzole
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.debug("Logger initialized.")
    return logger


def eprint_inline(s: str):
    """Inline progress do stderr (1 řádek)."""
    sys.stderr.write("\r" + s)
    sys.stderr.flush()


def clear_inline():
    sys.stderr.write("\r" + " " * 120 + "\r")
    sys.stderr.flush()


# ---------- Utils ----------

def file_hash(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def unique_destination_path(dest_path: Path) -> Path:
    if not dest_path.exists():
        return dest_path
    stem, suffix, parent = dest_path.stem, dest_path.suffix, dest_path.parent
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def ensure_parent_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def is_subpath(path: Path, potential_parent: Path) -> bool:
    try:
        path.resolve().relative_to(potential_parent.resolve())
        return True
    except Exception:
        return False


def iter_paths(root: Path) -> Iterator[Path]:
    for p in root.rglob("*"):
        yield p


def count_items(root: Path) -> Tuple[int, int, int]:
    """Vrátí (files, symlinks, dirs)."""
    files = syms = dirs = 0
    for p in iter_paths(root):
        try:
            if p.is_symlink():
                syms += 1
            elif p.is_file():
                files += 1
            elif p.is_dir():
                dirs += 1
        except Exception:
            # Počítání je best-effort
            pass
    return files, syms, dirs


def format_eta(done: int, total: int, start_ts: float) -> str:
    if total <= 0 or done <= 0:
        return "ETA: —"
    elapsed = time.time() - start_ts
    rate = done / max(elapsed, 1e-6)
    remaining = (total - done) / max(rate, 1e-6)
    # hezky formátovat
    def fmt(t):
        t = int(round(t))
        m, s = divmod(t, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"
    return f"ETA: {fmt(remaining)}"


# ---------- Core ----------

def build_hash_set(main_root: Path, logger: logging.Logger, algo: str) -> Set[str]:
    files_total, _, _ = count_items(main_root)
    logger.info(f"Indexuji Hlavní složku: očekávám ~{files_total} souborů (bez symlinků).")

    hashes: Set[str] = set()
    processed = 0
    start = time.time()
    last_update = 0.0

    for p in iter_paths(main_root):
        try:
            if p.is_symlink():
                continue
            if p.is_file():
                h = file_hash(p, algo=algo)
                hashes.add(h)
                processed += 1

                now = time.time()
                if now - last_update >= PROGRESS_UPDATE_INTERVAL:
                    perc = (processed / files_total * 100) if files_total else 0
                    eprint_inline(f"[Hlavní] {processed}/{files_total} ({perc:.1f}%)  {format_eta(processed, files_total, start)}")
                    last_update = now
        except Exception as ex:
            logger.warning(f"Nelze zpracovat '{p}': {ex}")

    clear_inline()
    logger.info(f"Hotovo: {processed} souborů v Hlavní. Unikátních hashů: {len(hashes)}")
    return hashes


def plan_moves(
    main_hashes: Set[str],
    older_root: Path,
    dest_root: Path,
    symlinks_dest: Path,
    logger: logging.Logger,
    algo: str
) -> Tuple[List[Tuple[Path, Path]], List[Tuple[Path, Path]], int]:
    """Vrací (moves_regular, moves_symlinks, scanned_regular_files)"""
    reg_total, syms_total, _ = count_items(older_root)
    logger.info(f"Procházím Starší složku: ~{reg_total} souborů a ~{syms_total} symlinků.")

    moves_regular: List[Tuple[Path, Path]] = []
    moves_syms: List[Tuple[Path, Path]] = []

    processed_reg = 0
    processed_syms = 0
    start_reg = time.time()
    start_sym = time.time()
    last_update_reg = 0.0
    last_update_sym = 0.0

    for p in iter_paths(older_root):
        try:
            if p.is_symlink():
                # symlink -> vždy přesunout do symlinks_dest (zachovat strukturu)
                rel = p.relative_to(older_root)
                dest = unique_destination_path(symlinks_dest / rel)
                moves_syms.append((p, dest))
                processed_syms += 1
                now = time.time()
                if now - last_update_sym >= PROGRESS_UPDATE_INTERVAL:
                    perc = (processed_syms / syms_total * 100) if syms_total else 100.0
                    eprint_inline(f"[Starší/SYMLINKY] {processed_syms}/{syms_total} ({perc:.1f}%)  {format_eta(processed_syms, syms_total, start_sym)}")
                    last_update_sym = now
                continue

            if p.is_file():
                h = file_hash(p, algo=algo)
                if h not in main_hashes:
                    rel = p.relative_to(older_root)
                    dest = unique_destination_path(dest_root / rel)
                    moves_regular.append((p, dest))
                processed_reg += 1

                now = time.time()
                if now - last_update_reg >= PROGRESS_UPDATE_INTERVAL:
                    perc = (processed_reg / reg_total * 100) if reg_total else 0
                    eprint_inline(f"[Starší/SOUBORY] {processed_reg}/{reg_total} ({perc:.1f}%)  {format_eta(processed_reg, reg_total, start_reg)}")
                    last_update_reg = now

        except Exception as ex:
            logger.warning(f"Chyba při zpracování '{p}': {ex}")

    clear_inline()
    logger.info(f"Plán hotov. Kandidátů k přesunu: {len(moves_regular)} souborů, {len(moves_syms)} symlinků.")
    return moves_regular, moves_syms, processed_reg


def remove_empty_dirs(older_root: Path, logger: logging.Logger) -> List[Path]:
    removed: List[Path] = []
    # Post-order: topdown=False
    all_dirs = []
    for dirpath, dirnames, filenames in os.walk(older_root, topdown=False):
        all_dirs.append(Path(dirpath))
    total = len(all_dirs)
    start = time.time()
    last = 0.0

    for i, p in enumerate(all_dirs, 1):
        if p.resolve() == older_root.resolve():
            continue
        try:
            if not any(p.iterdir()):
                p.rmdir()
                removed.append(p)
                logger.debug(f"Odstraněn prázdný adresář: {p}")
        except Exception as ex:
            logger.warning(f"Nelze odstranit '{p}': {ex}")

        now = time.time()
        if now - last >= PROGRESS_UPDATE_INTERVAL:
            perc = (i / total * 100) if total else 100.0
            eprint_inline(f"[Úklid] {i}/{total} ({perc:.1f}%)  {format_eta(i, total, start)}")
            last = now

    clear_inline()
    return removed


def main():
    parser = argparse.ArgumentParser(
        description="Přesune soubory (podle obsahu) navíc ze Starší do Cílové a symlinky ze Starší do Složky pro symlinky."
    )
    parser.add_argument("--main", required=True, type=Path, help="Cesta k Hlavní složce (aktuální).")
    parser.add_argument("--older", required=True, type=Path, help="Cesta ke Starší verzi složky.")
    parser.add_argument("--dest", required=True, type=Path, help="Cesta k Cílové (záchytné) složce pro běžné soubory.")
    parser.add_argument("--symlinks-dest", required=True, type=Path, help="Cesta ke speciální složce pro SYMLINKY.")
    parser.add_argument("--apply", action="store_true", help="Provede reálné přesuny a úklid.")
    parser.add_argument("--keep-empty-dirs", action="store_true", help="Neodstraňovat prázdné adresáře ve Starší složce.")
    parser.add_argument("--algo", default="sha256", help="Hash algoritmus (výchozí sha256).")
    parser.add_argument("--log-file", type=Path, default=Path("move_unique.log"), help="Cesta k log souboru.")
    parser.add_argument("--verbose", action="store_true", help="Více výpisů do konzole.")
    args = parser.parse_args()

    main_root: Path = args.main
    older_root: Path = args.older
    dest_root: Path = args.dest
    symlinks_dest: Path = args.symlinks_dest
    log_file: Path = args.log_file

    logger = setup_logging(log_file, verbose=args.verbose)
    logger.info("=== Start ===")

    # Validace vstupů
    for label, p in [("Hlavní", main_root), ("Starší", older_root)]:
        if not p.exists() or not p.is_dir():
            logger.error(f"{label} složka neexistuje nebo není adresář: {p}")
            print(f"[ERROR] {label} složka neexistuje nebo není adresář: {p}", file=sys.stderr)
            sys.exit(2)

    # Cílové složky vytvořit
    dest_root.mkdir(parents=True, exist_ok=True)
    symlinks_dest.mkdir(parents=True, exist_ok=True)

    # Bezpečnostní kontroly
    if main_root.resolve() == older_root.resolve():
        logger.error("Hlavní a Starší složka nesmí být stejná.")
        print("[ERROR] Hlavní a Starší složka nesmí být stejná.", file=sys.stderr)
        sys.exit(2)

    # Nesmíme zapisovat do Hlavní
    for label, target in [("Cílová", dest_root), ("Složka pro symlinky", symlinks_dest)]:
        if is_subpath(target, main_root):
            logger.error(f"{label} složka nesmí být uvnitř Hlavní složky: {target}")
            print(f"[ERROR] {label} složka nesmí být uvnitř Hlavní složky: {target}", file=sys.stderr)
            sys.exit(2)

    # Info o rozmístění
    if is_subpath(dest_root, older_root):
        logger.warning("Cílová složka je uvnitř Starší složky. Je to možné, ale může to zpomalit úklid.")
    if is_subpath(symlinks_dest, older_root):
        logger.warning("Složka pro symlinky je uvnitř Starší složky. Je to možné, ale může to zpomalit úklid.")

    # 1) Hash set Hlavní
    main_hashes = build_hash_set(main_root, logger, algo=args.algo)

    # 2) Plán přesunů (Starší)
    moves_regular, moves_syms, scanned_regular = plan_moves(
        main_hashes, older_root, dest_root, symlinks_dest, logger, algo=args.algo
    )

    # Dry-run výpis
    logger.info(f"DRY-RUN je {'VYPNUTÝ' if args.apply else 'ZAPNUTÝ'}")
    print(f"[INFO] Nalezeno k přesunu: {len(moves_regular)} souborů + {len(moves_syms)} symlinků.")
    print(f"[LOG] Kompletní detaily jsou v logu: {log_file}")

    if not args.apply:
        # ukažme pár položek
        preview = 10
        for (src, dst) in moves_regular[:preview]:
            print(f"  • (soubor) '{src}' -> '{dst}'")
        for (src, dst) in moves_syms[:preview]:
            print(f"  • (symlink) '{src}' -> '{dst}'")
        if len(moves_regular) > preview or len(moves_syms) > preview:
            print("  … další položky viz log.")
        if not args.keep_empty_dirs:
            print("  • Po přesunu by se mazaly prázdné adresáře ve Starší složce.")
        print("==== DRY-RUN: žádné změny neprovedeny ====")
        logger.info("DRY-RUN: konec.")
        return

    # 3) APPLY: přesuny
    # 3a) běžné soubory
    total = len(moves_regular)
    start = time.time()
    last = 0.0
    moved_regular = 0
    for i, (src, dst) in enumerate(moves_regular, 1):
        try:
            ensure_parent_dir(dst)
            shutil.move(str(src), str(dst))
            logger.info(f"[MOVE file] {src} -> {dst}")
            moved_regular += 1
        except Exception as ex:
            logger.error(f"[ERROR file] {src} -> {dst}: {ex}")

        now = time.time()
        if now - last >= PROGRESS_UPDATE_INTERVAL:
            perc = (i / total * 100) if total else 100.0
            eprint_inline(f"[Přesun SOUBORŮ] {i}/{total} ({perc:.1f}%)  {format_eta(i, total, start)}")
            last = now
    clear_inline()

    # 3b) symlinky
    total_s = len(moves_syms)
    start_s = time.time()
    last_s = 0.0
    moved_syms = 0
    for i, (src, dst) in enumerate(moves_syms, 1):
        try:
            ensure_parent_dir(dst)
            shutil.move(str(src), str(dst))  # přesouvá samotný odkaz, ne cíl
            logger.info(f"[MOVE symlink] {src} -> {dst}")
            moved_syms += 1
        except Exception as ex:
            logger.error(f"[ERROR symlink] {src} -> {dst}: {ex}")

        now = time.time()
        if now - last_s >= PROGRESS_UPDATE_INTERVAL:
            perc = (i / total_s * 100) if total_s else 100.0
            eprint_inline(f"[Přesun SYMLINKŮ] {i}/{total_s} ({perc:.1f}%)  {format_eta(i, total_s, start_s)}")
            last_s = now
    clear_inline()

    # 4) Úklid prázdných adresářů
    removed_dirs = []
    if not args.keep_empty_dirs:
        removed_dirs = remove_empty_dirs(older_root, logger)
        logger.info(f"Odstraněno prázdných adresářů: {len(removed_dirs)}")

    # 5) Souhrn
    print("\n==== SOUHRN ====")
    print(f"  Přesunuto souborů:  {moved_regular} / {len(moves_regular)}")
    print(f"  Přesunuto symlinků: {moved_syms} / {len(moves_syms)}")
    if not args.keep_empty_dirs:
        print(f"  Odstraněno prázdných adresářů ve Starší složce: {len(removed_dirs)}")
    print(f"  Log: {log_file}")
    logger.info("=== Hotovo ===")


if __name__ == "__main__":
    main()
