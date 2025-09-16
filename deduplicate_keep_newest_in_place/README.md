# Deduplicate Keep Newest In Place

A Python script for macOS / Linux that recursively scans a given folder, finds files with identical content, and keeps only the most recent copy of each file **in its original location**. All other duplicates are moved to a **`Duplikáty`** folder created inside the root of the scanned folder.

## Features

- Recursively scans the entire target folder.
- Detects duplicates by **file content** (SHA-256 hash).
- For each group of duplicates:
  - **Keeps the newest file** (by modification time) in place,
  - Moves all other copies to `Duplikáty/` (preserving their relative paths).
- Removes empty directories after moving files.
- Ensures unique filenames in the target if conflicts occur.
- Provides a **dry-run mode** (`--dry-run`) to preview actions without making changes.
- Optionally follows symlinks (`--follow-symlinks`).

## Requirements

- macOS or Linux  
- Python 3 (preinstalled on macOS)

## Installation

Clone the repository:

```bash
git clone https://github.com/yourusername/deduplicate-keep-newest.git
cd deduplicate-keep-newest
```

Make the script executable:

```bash
chmod +x deduplicate_keep_newest_in_place.py
```

## Usage

### 1. Navigate to the folder you want to clean
For example, if your target folder is `Photos` on the Desktop:

```bash
cd ~/Desktop/Photos
```

### 2. Test in dry-run mode

```bash
/path/to/deduplicate_keep_newest_in_place.py . --dry-run
```

> `.` means “the current folder” (`Photos` in this case).

### 3. Run for real

```bash
/path/to/deduplicate_keep_newest_in_place.py .
```

### 4. Optional flags

- `--dry-run` – only prints planned actions, no changes are made.  
- `--follow-symlinks` – include files through symbolic links.

## Example

Given the folder:

```
Main/
├── img1.jpg
├── Sub1/
│   ├── img1.jpg
│   └── img2.jpg
└── Sub2/
    └── img2.jpg
```

If `Sub1/img1.jpg` and `Sub2/img2.jpg` are duplicates of the root files, the script will keep the newest version of each in place and move the others into `Duplikáty/`:

```
Main/
├── img1.jpg
├── Sub1/
│   └── img2.jpg   (kept newest version)
├── Duplikáty/
│   ├── Sub1/img1.jpg
│   └── Sub2/img2.jpg
└── Sub2/          (removed if empty)
```
