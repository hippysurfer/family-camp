# Importing this package registers all available solvers (see registry.py).
# _stub is imported first (registers "annealing" until Step 19 replaces it);
# cp_sat is imported after, so its own "cp_sat" registration wins.
from family_camp2.solvers import _stub  # noqa: F401,E402
from family_camp2.solvers import cp_sat  # noqa: F401,E402
