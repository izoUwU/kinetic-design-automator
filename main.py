"""
Kinetic Design Automator - Main Entry Point

Launches the Kinetic Design Automator GUI for parameterized wafer mask layout generation
and automated optical micrograph analysis.
"""

import sys
import traceback
from kinetic_design_automator import (
    ChipDesignGUI,
    GLOBAL_PARAMS,
    IN_KLAYOUT,
    _get_app,
    _get_main_win,
    create_full_chip_design,
    create_single_quadrant_chip,
)


def main():
    try:
        app = _get_app()
        main_win = _get_main_win(app)
        dialog = ChipDesignGUI(main_win)

        if IN_KLAYOUT:
            dialog.exec_()
        else:
            dialog.exec()
    except Exception as e:
        traceback.print_exc()
        print(f"GUI launch failed. Deploying layout non-interactively. Error: {e}")
        GLOBAL_PARAMS["enable_optional_layers"] = True
        create_full_chip_design()
        create_single_quadrant_chip()


if __name__ == "__main__":
    main()
