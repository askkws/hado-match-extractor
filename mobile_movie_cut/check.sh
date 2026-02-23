#!/bin/bash
# Run after every code change to catch syntax errors and import issues
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Python Syntax Check ==="
for f in "$SCRIPT_DIR"/*.py; do
    python3 -m py_compile "$f" && echo "  OK: $(basename $f)"
done

echo ""
echo "=== Local Import Warning Check ==="
SCRIPT_DIR="$SCRIPT_DIR" python3 - <<'PYEOF'
import ast, glob, os, sys
script_dir = os.environ.get('SCRIPT_DIR', os.path.dirname(os.path.abspath(__file__)))
issues = []
for fpath in glob.glob(os.path.join(script_dir, '*.py')):
    fname = os.path.basename(fpath)
    with open(fpath) as f:
        src = f.read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        issues.append(f"  SYNTAX ERROR in {fname}: {e}")
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    issues.append(f"  WARN: {fname}: local import in {node.name}(): {ast.unparse(child)}")
if issues:
    for i in issues:
        print(i)
else:
    print("  No local imports found.")
PYEOF

echo ""
echo "=== All checks passed ==="
