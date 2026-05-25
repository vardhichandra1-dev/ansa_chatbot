"""
ANSA Custom Button — Shell Entity Counter
==========================================
This script creates a dockable chat-style panel inside ANSA with a custom button.
When clicked, it counts all SHELL (2D mesh) elements in the current model
and displays the result inside the panel.

HOW TO RUN IN ANSA:
    1. Open ANSA
    2. Go to: Scripts > Run Script
    3. Select this file
    4. The panel will appear docked inside ANSA
"""

import ansa
from ansa import base, constants, guitk

# ─────────────────────────────────────────────
# OPERATION: Count Shell Elements in Model
# ─────────────────────────────────────────────
def count_shell_elements():
    """
    Queries the current ANSA model and counts all SHELL (2D mesh) entities.
    Returns a formatted result string.
    """
    try:
        # Get the current active deck (model)
        deck = base.CurrentDeck()

        # Collect all SHELL entities (2D mesh elements)
        shells = base.CollectEntities(deck, None, 'SHELL')

        if shells is None:
            return "No shell elements found in the current model."

        count = len(shells)
        return f"Shell element count: {count} elements found in current model."

    except Exception as e:
        return f"Error during operation: {str(e)}"


# ─────────────────────────────────────────────
# GUI: Build the Panel using ANSA BCGui
# ─────────────────────────────────────────────
def build_panel():
    """
    Creates a dockable GUI panel inside ANSA using the BCGui (guitk) library.
    Contains:
        - A title label
        - A 'Count Shells' button
        - A result display area
    """

    # Create main window (dockable panel)
    window = guitk.BCWindow('ANSA AI Assistant', guitk.constants.BCWindowFlagType.BCNoFlag)
    window.setFixedSize(350, 200)

    # Vertical layout container
    layout = guitk.BCBoxLayout(guitk.constants.BCOrientationType.BCVertical)

    # ── Title Label ──
    title = guitk.BCLabel('ANSA Custom Tool Panel')
    title.setFont(guitk.BCFont('Arial', 11, True))  # Bold title
    layout.addWidget(title)

    # ── Separator ──
    layout.addSpacing(10)

    # ── Result Display Label (updates after button click) ──
    result_label = guitk.BCLabel('Click the button to run an operation.')
    result_label.setWordWrap(True)

    # ── Button: Count Shell Elements ──
    def on_button_click():
        """Handler: runs the operation and updates the result label."""
        result_label.setText('Running... please wait.')
        result = count_shell_elements()
        result_label.setText(result)

    button = guitk.BCPushButton('Count Shell Elements')
    button.onClicked(on_button_click)

    # ── Add widgets to layout ──
    layout.addWidget(button)
    layout.addSpacing(10)
    layout.addWidget(result_label)

    # ── Attach layout to window and show ──
    window.setLayout(layout)
    window.show()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == '__main__':
    build_panel()
