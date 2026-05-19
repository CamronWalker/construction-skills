"""One render function per graph. Each takes (data: dict, output_path: str) → None.

Each function is self-contained: it knows its data shape, its chart type, its
title, axes, and styling. They don't share a base function — duplication is
intentional so each chart can be tweaked in isolation without risk of breaking
its neighbors.
"""

import matplotlib.pyplot as plt

from . import style
