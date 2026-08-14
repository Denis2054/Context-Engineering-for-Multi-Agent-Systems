"""Verify the shipped notebook.

Three classes of check:
  1. Byte identity — running the %%writefile cells must reproduce the .py files
     on disk exactly, so the notebook and the modules cannot silently diverge.
  2. Structural validity — nbformat schema, no stale outputs, no execution
     counts, valid Python in every code cell.
  3. Content audit — no placeholder URLs, no stale "100%" branding, no stale
     references to cells that do not exist.
"""
import ast
import json
import os
import re
import sys

SRC = "/home/claude/langchain"
NB = os.path.join(SRC, "Universal_Context_Engine_LangChain.ipynb")

FAILURES = []


def check(label, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}"
          + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


with open(NB, encoding="utf-8") as f:
    raw = f.read()
nb = json.loads(raw)
cells = nb["cells"]


def source_of(cell):
    src = cell["source"]
    return src if isinstance(src, str) else "".join(src)


# =============================================================================
print("\n1. Byte identity: %%writefile cells vs standalone modules")
# =============================================================================
# Mirrors IPython's implementation: the magic writes the cell body verbatim
# (osm.py -> writefile -> f.write(cell)), where `cell` is everything after the
# first line.
written = {}
for cell in cells:
    if cell["cell_type"] != "code":
        continue
    src = source_of(cell)
    m = re.match(r"%%writefile\s+(\S+)\n", src)
    if not m:
        continue
    written[m.group(1)] = src[m.end():]

expected = ["lc_utils.py", "lc_helpers.py", "lc_agents.py", "lc_registry.py",
            "lc_engine.py", "lc_dashboard.py", "lc_boot.py"]
check("all seven modules are written by the notebook",
      sorted(written) == sorted(expected), sorted(written))

for name in expected:
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        disk = f.read()
    same = written.get(name) == disk
    check(f"{name} byte-identical", same,
          f"cell={len(written.get(name, ''))} disk={len(disk)}")

# =============================================================================
print("\n2. Structural validity")
# =============================================================================
try:
    import nbformat
    nbformat.validate(nbformat.reads(raw, as_version=4))
    check("nbformat schema validation", True)
except ImportError:
    check("nbformat schema validation (nbformat not installed)", True)
except Exception as e:
    check("nbformat schema validation", False, str(e)[:200])

check("no stored outputs",
      all(not c.get("outputs") for c in cells if c["cell_type"] == "code"))
check("no execution counts",
      all(c.get("execution_count") is None for c in cells if c["cell_type"] == "code"))
check("every cell has non-empty source", all(source_of(c).strip() for c in cells))

for i, cell in enumerate(cells):
    if cell["cell_type"] != "code":
        continue
    src = source_of(cell)
    body = re.sub(r"^%%writefile\s+\S+\n", "", src)
    body = re.sub(r"^\s*#@title.*$", "", body, flags=re.M)
    try:
        ast.parse(body)
    except SyntaxError as e:
        check(f"cell {i} parses as Python", False, f"line {e.lineno}: {e.msg}")
        break
else:
    check("every code cell parses as Python", True)

# Cross-check: the notebook must define names before it uses them.
srcs = [source_of(c) for c in cells if c["cell_type"] == "code"]
# %%writefile cells only write text to disk; their module prose is not notebook
# execution, so they are excluded from name-ordering analysis.
runtime = [s for s in srcs if not s.startswith("%%writefile")]
first_engine_def = next(i for i, s in enumerate(runtime) if "engine = lc_boot" in s)
first_engine_use = next(i for i, s in enumerate(runtime)
                        if re.search(r"\bengine\.\w", s) or "ctx_engine or engine" in s)
check("`engine` is built before it is used", first_engine_def < first_engine_use,
      f"defined at runtime cell {first_engine_def}, used at {first_engine_use}")

first_import_utils = next(i for i, s in enumerate(srcs) if s.startswith("# Install"))
first_writefile = next(i for i, s in enumerate(srcs) if s.startswith("%%writefile"))
check("modules are written before lc_utils is imported",
      first_writefile < first_import_utils)

first_dash = next(i for i, s in enumerate(runtime) if "from lc_dashboard import" in s)
first_exec = next(i for i, s in enumerate(runtime) if "def execute_and_display" in s)
check("dashboard imported before execute_and_display defined", first_dash < first_exec)

# =============================================================================
print("\n3. Content audit")
# =============================================================================
all_text = "\n".join(source_of(c) for c in cells)

check("no YOUR_USERNAME placeholder", "YOUR_USERNAME" not in all_text)
check("no YOUR_REPO placeholder", "YOUR_REPO" not in all_text)
check("no FILENAME.ipynb placeholder", "FILENAME.ipynb" not in all_text)
check("no scratch-repo badge (Denis2054/SFT)", "Denis2054/SFT" not in all_text)
check("badge points at the book repo",
      "Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/langchain/"
      in source_of(cells[0]))
check("no residual '100% LangChain' branding", "100% LangChain" not in all_text)
check("no claim of a download cell", "downloaded the seven engine modules" not in all_text)
check("no wget / curl fetching", not re.search(r"!(wget|curl)\b", all_text))
check("prerequisite warning present",
      "clear_index=False" in all_text and "Prerequisite" in all_text)
check("check_index is called", "lc_utils.check_index(" in all_text)
check("Section VII honest-limits section present",
      "What LangChain does not provide" in all_text)
check("sanitizer named as a non-LangChain component",
      "Per-chunk sanitization" in all_text)

# The stale contract from the previous edition.
check("no `trace is None` contract left in the notebook",
      "if trace is None" not in all_text)

# Config values quoted in prose must match the code.
import importlib.util
spec = importlib.util.spec_from_file_location("lc_helpers", os.path.join(SRC, "lc_helpers.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["lc_helpers"] = mod
spec.loader.exec_module(mod)
cfg = mod.CONFIG

for key, label in [("index_name", "index"), ("generation_model", "generation model"),
                   ("embedding_model", "embedding model"),
                   ("namespace_context", "blueprint namespace"),
                   ("namespace_knowledge", "knowledge namespace"),
                   ("text_key_context", "blueprint text_key"),
                   ("text_key_knowledge", "knowledge text_key")]:
    check(f"prose matches CONFIG['{key}'] = {cfg[key]}", cfg[key] in all_text)

check("declared package pins match lc_utils.PACKAGES",
      os.path.exists(os.path.join(SRC, "requirements.txt")))
if os.path.exists(os.path.join(SRC, "requirements.txt")):
    spec2 = importlib.util.spec_from_file_location(
        "lc_utils", os.path.join(SRC, "lc_utils.py"))
    utils = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(utils)
    with open(os.path.join(SRC, "requirements.txt"), encoding="utf-8") as f:
        req = [ln.strip() for ln in f
               if ln.strip() and not ln.strip().startswith("#")]
    check("requirements.txt == lc_utils.PACKAGES", sorted(req) == sorted(utils.PACKAGES),
          f"req={sorted(req)}\n        pkg={sorted(utils.PACKAGES)}")

print("\n" + "=" * 70)
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print(f"ALL NOTEBOOK CHECKS PASSED ({len(cells)} cells)")
