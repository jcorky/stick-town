"""Wind: one deterministic field (field.py) driving trunks, limbs, branches, leaves and grass (response.py,
sway.py), exported as per-vertex attributes (attrs.py) for the viewer's shader (viewer/wind.js).
See docs/TECHNIQUES.md §34."""

from . import response, sway
from .field import BEAUFORT, CANOPY_A, DAVENPORT_CY, LAND, Wind


def constants():
    """Every number the viewer's wind shader needs besides the field itself (one source of truth)."""
    return dict(U_REF=response.U_REF, U0=response.U0, VOGEL_B=response.VOGEL_B, ZETA_BRANCH=response.ZETA_BRANCH,
                D_MAX=response.D_MAX, L_MAX=response.L_MAX, F1_MAX=response.F1_MAX, F2_MAX=response.F2_MAX,
                LIMB_L=sway.LIMB_L, BRANCH_L=sway.BRANCH_L, ALPHA_MAX=sway.ALPHA_MAX, U_ALPHA=sway.U_ALPHA,
                FLUTTER_HZ=sway.FLUTTER_HZ, FLUTTER_A=sway.FLUTTER_A, U_FLUTTER=sway.U_FLUTTER,
                GRASS_HZ=sway.GRASS_HZ, ZETA_GRASS=sway.ZETA_GRASS, GRASS_BETA=sway.GRASS_BETA,
                GRASS_U0=sway.GRASS_U0, DAVENPORT_CY=DAVENPORT_CY, CANOPY_A=CANOPY_A,
                BEAUFORT={str(k): v for k, v in BEAUFORT.items()}, LAND={str(k): v for k, v in LAND.items()})


__all__ = ["Wind", "constants", "response", "sway"]
