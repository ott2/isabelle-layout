"""Package data: the conformance corpus.

A package rather than a bare directory so `importlib.resources` can address it
by name on every supported Python, including when the distribution is
installed as a zip.  Read it through :mod:`isabelle_layout.conformance`.
"""
