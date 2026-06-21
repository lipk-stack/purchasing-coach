"""Purchasing Coach — chat with a purchasing guideline and generate tender checklists."""

import logging

__version__ = "2.1.0"

# Library code logs to the "coach" logger; a NullHandler keeps it silent unless
# the application (e.g. the CLI) configures logging. See coach.cli for setup.
logging.getLogger("coach").addHandler(logging.NullHandler())
