"""Live integration suite package.

The __init__.py is required: without it this directory's conftest.py is imported
as top-level ``conftest`` and shadows ``tests/conftest.py``, which the unit tests
import by that name.
"""
