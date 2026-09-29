"""jevsg — Jev x Subgrid edge coordinates (research code).

Stage G1 (this package's current scope): the representation A of Subgrid Marching
Tetrahedra — per grid edge, the number of surface crossings and their positions — with an
exact encoder (mesh -> A), the pinned reference reconstructor (A -> mesh), and the
evaluation used to measure what the round trip preserves.  See ``docs/proposal.md``.
"""

from jevsg.grid import TetGrid
from jevsg.representation import EdgeCoordinates

__all__ = ["EdgeCoordinates", "TetGrid"]
__version__ = "0.1.0"
