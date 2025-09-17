# move_unique_from_older.py

## Účel
Skript porovnává obsah dvou složek:

- **Hlavní složka** – aktuální a platná verze (z ní se nic nemaže).
- **Starší složka** – starší verze obsahu.
- **Cílová složka** – zde se uloží všechny soubory, které jsou ve Starší složce, ale jejich **obsah** se nenachází v Hlavní složce.
- **Složka pro symlinky** – zde se uloží všechny symbolické odkazy ze Starší složky (bez ohledu na to, zda jsou i v Hlavní).

Funkce:
- Porovnává se **podle obsahu** (hash SHA-256), ne podle názvu.
- Zachovává **původní adresářovou strukturu**.
- Pokud v cíli existuje soubor stejného jména, přidá se sufix ` (1)`, ` (2)`…
- Symbolické odkazy (symlinky) se vždy přesunou do samostatné složky.
- Po přesunu lze nechat automaticky smazat prázdné adresáře ve Starší složce.
- Podporuje **dry-run** (výchozí) a **apply** režim.
- Zobrazuje **progress a odhadovaný čas (ETA)**.
- Loguje do souboru.

---

## Požadavky
- macOS / Linux (testováno na macOS)
- Python 3.8+

---

## Instalace
Stačí uložit soubor `move_unique_from_older.py` a mít v systému dostupný Python 3.

Volitelně nastav spustitelný bit:
```bash
chmod +x move_unique_from_older.py
```

---

## Použití

### Základní příklad (dry-run)
```bash
python3 move_unique_from_older.py   --main "/Volumes/DATA/Hlavni"   --older "/Volumes/ARCHIV/Starsi"   --dest "/Volumes/STASH/ExtraZeStarsi"   --symlinks-dest "/Volumes/STASH/SymlinkyZeStarsi"   --log-file "/Volumes/STASH/move_unique.log"   --verbose
```

Tento příkaz **jen vypíše**, co by skript udělal. V Hlavní složce nic nemění.

### Reálné provedení (apply)
```bash
python3 move_unique_from_older.py   --main "/Volumes/DATA/Hlavni"   --older "/Volumes/ARCHIV/Starsi"   --dest "/Volumes/STASH/ExtraZeStarsi"   --symlinks-dest "/Volumes/STASH/SymlinkyZeStarsi"   --log-file "/Volumes/STASH/move_unique.log"   --apply
```

### Reálné provedení bez mazání prázdných složek
```bash
python3 move_unique_from_older.py   --main "/Volumes/DATA/Hlavni"   --older "/Volumes/ARCHIV/Starsi"   --dest "/Volumes/STASH/ExtraZeStarsi"   --symlinks-dest "/Volumes/STASH/SymlinkyZeStarsi"   --log-file "/Volumes/STASH/move_unique.log"   --apply   --keep-empty-dirs
```

---

## Parametry
- `--main PATH` – cesta k Hlavní složce (aktuální).
- `--older PATH` – cesta ke Starší složce.
- `--dest PATH` – cílová složka pro soubory navíc.
- `--symlinks-dest PATH` – cílová složka pro symlinky.
- `--apply` – provést reálné přesuny (jinak jen dry-run).
- `--keep-empty-dirs` – zachovat prázdné adresáře ve Starší složce.
- `--algo` – hash algoritmus (výchozí `sha256`).
- `--log-file FILE` – cesta k logu (výchozí `move_unique.log`).
- `--verbose` – více výpisů do konzole.

---

## Poznámky
- Porovnání obsahu pomocí SHA-256 je bezpečné, ale může být pomalejší u velkých složek.  
- Pokud chceš zrychlení, lze doplnit multi-threaded hashování nebo cache.  
- Symlinky se přesouvají jako odkazy (ne cílové soubory).  
- Log obsahuje detailní záznam (přesunuté položky, varování, chyby).

---

## Autor
Vygenerováno pomocí ChatGPT (2025).
