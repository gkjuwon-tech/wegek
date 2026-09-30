"""Stage G2 — selection diagnosis (proposal §6, G2 row).

A *local problem* hides the crossings inside a small block of the grid and asks which
of a set of candidate completions to put back.  Candidates are generated without the
answer (inside/outside labellings of the hidden nodes, optionally continuing thin walls),
scored by an oracle that rebuilds the whole shape, and then chosen by random choice,
simple rules and Jev under identical inputs.
"""
