# eBook Indexer Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a Python CLI tool using `uv`, `click`, and `sqlite3` to index EPUB metadata from a directory and provide full-text search.

**Architecture:**
- **CLI:** Click-based interface for `discover`, `index`, and `search` commands.
- **Scanner:** Recursive directory walker that identifies `.epub` files.
- **Extractor:** EPUB metadata extraction using `ebooklib`.
- **Database:** SQLite with FTS5 for efficient metadata storage and searching.
- **Project Setup:** `uv` for dependency management and project structure (following the `playlist-builder` pattern).

**Tech Stack:** `python >= 3.11`, `uv`, `click`, `sqlite3` (FTS5), `ebooklib`, `beautifulsoup4`, `loguru`, `rich`, `ty`, `poethepoet`.

---

### Task 1: Project Initialization

**Objective:** Initialize the project using `uv` and set up the directory structure. 

**Files:**
- Create: `pyproject.toml`
- Create: `src/ebdx/__init__.py`
- Create: `src/ebdx/cli.py`

**Step 1: Initialize uv project**
Run: `uv init --lib ebdx`

**Step 2: Configure pyproject.toml**
Update `pyproject.toml` with dependencies (`click`, `loguru`, `rich`, `ebooklib`, `beautifulsoup4`, `platformdirs`), dev tools (`poethepoet`, `ruff`, `ty`, `pytest`, `flowmark-rs`), and a `poe` task runner.

---

### Task 2: Basic CLI Shell

**Objective:** Implement a Click CLI with `discover`, `index`, and `search` stubs.

**Files:**
- Modify: `src/ebdx/cli.py`

**Step 1: Implement Click entry point**
```python
@click.group()
def cli(): pass

@cli.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
def discover(paths):
    """Locate EPUB files in the specified paths."""

@cli.command()
@click.argument("root", type=click.Path(exists=True))
def index(root):
    """Index metadata from discovered EPUBs."""

@cli.command()
@click.argument("query")
def search(query):
    """Search for ebooks."""
```

---

### Task 3: Database Schema & Connection

**Objective:** Set up SQLite database with FTS5.

**Files:**
- Create: `src/ebdx/db.py`

---

### Task 4: EPUB Metadata Extraction

**Objective:** Implement metadata extraction from `.epub` files.

**Files:**
- Create: `src/ebdx/extractor.py`

---

### Task 5: Scanner and Indexing Logic

**Objective:** Walk the directory, extract metadata, and save to the database.

**Files:**
- Create: `src/ebdx/scanner.py`
- Modify: `src/ebdx/cli.py`

---

### Task 6: Search Implementation

**Objective:** Implement full-text search querying.

**Files:**
- Modify: `src/ebdx/db.py`
- Modify: `src/ebdx/cli.py`
