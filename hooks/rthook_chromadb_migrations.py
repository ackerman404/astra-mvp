"""
Runtime hook: fix chromadb migration namespace packages in frozen PyInstaller exe.

ROOT CAUSE:
  ChromaDB's sqlite.py calls importlib_resources.files() for three subdirectories
  that contain only .sql migration files and have NO __init__.py:
    - chromadb/migrations/embeddings_queue/
    - chromadb/migrations/sysdb/
    - chromadb/migrations/metadb/

  In regular Python these are found as namespace packages via _NamespacePath.
  In frozen PyInstaller exes they are not registered as importable packages at all,
  so importlib.import_module() raises:
    ModuleNotFoundError: No module named 'chromadb.migrations.embeddings_queue'

FIX:
  Pre-register each directory as a namespace package in sys.modules with
  submodule_search_locations that satisfies importlib_resources.NamespaceReader's
  check: 'NamespacePath' must appear in str(submodule_search_locations).

  We use a small NamespacePathList wrapper class whose __str__/__repr__ contain
  "NamespacePath", matching what Python's _NamespacePath produces for real
  namespace packages. NamespaceReader then resolves the actual .sql file paths
  from sys._MEIPASS.
"""
import os
import sys


class _NamespacePathList(list):
    """
    A list subclass whose repr contains 'NamespacePath' so that
    importlib_resources.readers.NamespaceReader accepts it as a valid
    namespace package path (it checks: 'NamespacePath' in str(namespace_path)).
    """
    def __repr__(self):
        return f"_NamespacePath({super().__repr__()})"

    def __str__(self):
        return self.__repr__()


def _register_chroma_migration_namespaces():
    import importlib.machinery
    import importlib.util

    base_path = sys._MEIPASS

    migration_pkgs = [
        ("chromadb.migrations.embeddings_queue",
         os.path.join(base_path, "chromadb", "migrations", "embeddings_queue")),
        ("chromadb.migrations.sysdb",
         os.path.join(base_path, "chromadb", "migrations", "sysdb")),
        ("chromadb.migrations.metadb",
         os.path.join(base_path, "chromadb", "migrations", "metadb")),
    ]

    for pkg_name, pkg_path in migration_pkgs:
        if pkg_name in sys.modules:
            continue
        if not os.path.isdir(pkg_path):
            continue

        spec = importlib.machinery.ModuleSpec(
            name=pkg_name,
            loader=None,
            origin=None,
            is_package=True,
        )
        # Use _NamespacePathList so NamespaceReader's string check passes
        spec.submodule_search_locations = _NamespacePathList([pkg_path])

        module = importlib.util.module_from_spec(spec)
        module.__package__ = pkg_name
        module.__path__ = _NamespacePathList([pkg_path])
        sys.modules[pkg_name] = module


if getattr(sys, "frozen", False):
    _register_chroma_migration_namespaces()
