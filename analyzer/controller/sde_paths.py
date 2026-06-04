"""
Dodaje ścieżki Intel BF-SDE do sys.path, żeby kontroler znalazł
bfrt_grpc i moduły potrzebne do BfRuntime.

Wzór z PTF tests Intel SDE. Wykrywa lokalizację SDE z env SDE_INSTALL
(z fallback'iem na zaobserwowaną ścieżkę w środowisku Mariusza).

Wystarczy zaimportować ten moduł jako pierwszy:
    import sde_paths   # noqa: F401
    import bfrt_grpc.client as gc
"""
import os
import sys

SDE_INSTALL = os.environ.get(
    "SDE_INSTALL",
    "/home/student/sde/bf-sde-9.13.4/install",
)

_PY = f"python{sys.version_info.major}.{sys.version_info.minor}"

_paths = [
    f"{SDE_INSTALL}/lib/{_PY}/site-packages",
    f"/usr/local/lib/{_PY}/dist-packages",
    f"{SDE_INSTALL}/lib/{_PY}/site-packages/p4testutils",
    f"{SDE_INSTALL}/lib/{_PY}/site-packages/tofino",
]

for p in _paths:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.append(p)

if not os.path.isdir(SDE_INSTALL):
    print(f"[sde_paths] OSTRZEŻENIE: SDE_INSTALL='{SDE_INSTALL}' nie istnieje. "
          f"Ustaw zmienną SDE_INSTALL lub edytuj sde_paths.py.",
          file=sys.stderr)
