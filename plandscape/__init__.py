"""plandscape — procedural landscapes of the American South.

Everything is deterministic from a world seed: the same prompt + seed always
produces the same terrain, trees, paths and animal behaviour, while changing
any seed key yields a new, distinct variant ("infinite combinations").

Core runs on numpy + scipy only, so it works in locked-down sandboxes.
"""

__version__ = "0.2.0"
