# Importing this package registers all available solvers (see registry.py).
from family_camp2.solvers import cp_sat  # noqa: F401,E402
from family_camp2.solvers.annealing import solver as _annealing_solver  # noqa: F401,E402
