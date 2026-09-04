"""Every intra-project import must resolve to a file git tracks.

An untracked file works perfectly on the machine that created it and does not
exist anywhere else. `molido_strategies/engine.py` imported two strategies that
were never committed: the package was unimportable in a fresh clone and in CI,
while the developer's own tests passed and the built image ran fine, because
both had the files locally. The failure only surfaces for the next person.

This walks the actual imports rather than trusting a list, so a module added
later is covered without anyone remembering to add it here.
"""
import ast
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
SEARCH = ("packages", "apps", "telegram-bot", "scripts")


def _tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def _package_roots() -> dict[str, str]:
    roots = {}
    pkgs = os.path.join(ROOT, "packages")
    for pkg in os.listdir(pkgs):
        d = os.path.join(pkgs, pkg)
        if not os.path.isdir(d):
            continue
        for sub in os.listdir(d):
            if sub.startswith("molido_") and os.path.isdir(os.path.join(d, sub)):
                roots[sub] = os.path.join(d, sub)
    return roots


def _imports(path: str):
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (SyntaxError, UnicodeDecodeError):
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def test_every_molido_import_has_a_tracked_file():
    roots = _package_roots()
    tracked = _tracked()
    problems = []

    for base in SEARCH:
        top = os.path.join(ROOT, base)
        if not os.path.isdir(top):
            continue
        for dirpath, dirnames, files in os.walk(top):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", "node_modules", ".venv", ".git")]
            for name in files:
                if not name.endswith(".py"):
                    continue
                src = os.path.join(dirpath, name)
                for mod in _imports(src):
                    head, *rest = mod.split(".")
                    if head not in roots or not rest:
                        continue
                    as_file = os.path.join(roots[head], *rest) + ".py"
                    as_pkg = os.path.join(roots[head], *rest, "__init__.py")
                    target = as_file if os.path.exists(as_file) else (
                        as_pkg if os.path.exists(as_pkg) else None)
                    rel_src = os.path.relpath(src, ROOT).replace(os.sep, "/")
                    if target is None:
                        problems.append("%s imports %s -- no such module" % (rel_src, mod))
                    elif os.path.relpath(target, ROOT).replace(os.sep, "/") not in tracked:
                        problems.append(
                            "%s imports %s -- the file exists but is not committed" % (rel_src, mod))

    assert not problems, "unresolved intra-project imports:\n  " + "\n  ".join(sorted(set(problems)))
