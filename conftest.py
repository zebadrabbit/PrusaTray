"""Pytest configuration.

test_dialog.py and test_notifications.py are hand-run GUI demos, not automated
tests: they open a modal dialog / show real toasts and end in app.exec(), which
never returns. Collecting them would hang `pytest -q` (what CI runs).
"""

collect_ignore = ["test_dialog.py", "test_notifications.py"]
