# Publishing a release

The steps, in order; where one prevents a specific failure, it names it.
Commands work as written under sh, bash, zsh and tcsh, and use the repository's
`.venv` (`pip install build twine`, once). The pushes and the upload are
outward-facing, so they are taken only when asked for. Not shipped in the
sdist; see `exclude` in `pyproject.toml`.

## 1. Pre-flight

```sh
.venv/bin/pip install '.[test]' && .venv/bin/python -m pytest
.venv/bin/python -c "import ast,pathlib; [ast.parse(p.read_text(), str(p), feature_version=(3,9)) for p in pathlib.Path('src').rglob('*.py')]"
curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/isabelle-layout/X.Y.Z/json
```

- Install, not `-e`: whether the package data ships is the one question an
  editable install cannot answer.
- The `ast.parse` line stands in for the CI matrix there isn't, only 3.14 being
  installed. It catches post-3.9 *grammar* alone — `match` fails it, `int|str`
  does not, being a BinOp until evaluated — so also check by eye for
  `from __future__ import annotations` and post-3.9 stdlib calls.
- The `curl` must print 404, or the version is spent.
- **No consumer caps this package**: `isabelle-query` declares
  `isabelle-layout>=0.2.0`, floor only. A `<` bound upstream is the one thing
  that can make a correct publish unusable.

## 2. The release commit

Drop the `.dev0` from `version` in `pyproject.toml`, reinstall, and commit with
the **release notes as the message** — subject `X.Y.Z — summary`, then markdown
for users. `release.yml` publishes that message and reads nothing else; a tag
annotation is ignored, `--notes-from-tag` having mis-published `isabelle-query`
v0.2.5 by falling back to the commit message silently.

## 3. Build, before tagging

A broken build costs nothing; a pushed tag should never move.

**`dist/` accumulates and nothing in it is deleted**, since the artefact as
published is what answers a later question about a release and a rebuild from
the tag is not guaranteed byte-identical. `build` adds to the directory rather
than replacing it, and `dist/` is untracked, so retention is local.

```sh
.venv/bin/python -m build
.venv/bin/twine check --strict dist/isabelle_layout-X.Y.Z-*.whl dist/isabelle_layout-X.Y.Z.tar.gz
tar tzf dist/isabelle_layout-X.Y.Z.tar.gz
```

- **Name the version; never `dist/*`,** which with history kept hands twine
  everything there. `dist/isabelle_layout-X.Y.Z*` is no safer — it matches
  `…-X.Y.Z.dev0-…` too, and uploading a dev artefact spends the release version
  permanently. The hyphen before the platform tags is what excludes it.
- `build` makes the wheel *from the sdist*, so a file missing from the sdist's
  `include` fails here, not in a user's checkout.
- `tar tzf` should list `src/`, `docs/decisions.md`, `scripts/`, `tests/`,
  `README.md`, `LICENSE`, `pyproject.toml`, `PKG-INFO` and `.gitignore`, and
  neither `docs/publishing.md` nor `scripts/verify_move.py`.

## 4. Tag and push

```sh
git tag -a vX.Y.Z -m "isabelle-layout X.Y.Z"
git push origin main
git push origin vX.Y.Z
gh run list -R ott2/isabelle-layout -L 3
gh release view vX.Y.Z -R ott2/isabelle-layout
```

Tag before uploading, so the tag names the tree that produced the artefacts.
`git push` does not push tags on its own, and the tag push is the whole GitHub
publish: the workflow creates the Release on the runner, and the two `gh`
commands only read the result. Creating it locally with `gh release create`
would put the notes somewhere other than the commit message, which is where
this project keeps them. Actions resolves the workflow from the pushed ref, so
it must already be in the tagged commit's tree (it is). Re-pushing a tag edits
the existing Release, so wrong notes are fixed by a *new* commit, tagged and
pushed; never by `--amend`, which leaves the branch a sibling of the remote,
not a descendant.

## 5. Upload to PyPI

```sh
.venv/bin/twine upload -r pypi-isabelle-layout dist/isabelle_layout-X.Y.Z-*.whl dist/isabelle_layout-X.Y.Z.tar.gz
```

**Every project gets its own `~/.pypirc` section, `pypi-<project>`**, so `-r`
selects both the index and the token scoped to that project in one word.
Nothing is passed on the command line or through the environment, where `ps`
would show the token and the shell would remember it.

```ini
[distutils]
index-servers =
    pypi
    testpypi
    pypi-isabelle-layout

[pypi-isabelle-layout]
repository = https://upload.pypi.org/legacy/
username = __token__
password = pypi-AgEIcHlwaS5vcmc…
```

`chmod 600 ~/.pypirc`. Three things that file gets wrong quietly:

- **The section must be listed in `index-servers`.** Twine reads per-section
  keys only for the servers named there, so an unlisted section fails with
  `Missing 'pypi-isabelle-layout' section` while sitting in plain sight in the
  file.
- **Any section not called `pypi` or `testpypi` needs `repository =`.** Those
  two names are the only ones twine supplies an upload URL for.
- **Keep `testpypi` on the list.** Its default URL is injected only while it is
  named there, so naming only the others silently takes it away.

Re-run a half-completed upload with `--skip-existing`. **Trusted Publishing**
would retire the token altogether, uploading from Actions over OIDC.

## 6. Verify as a stranger would

```sh
python3 -m venv /tmp/real
/tmp/real/bin/pip install isabelle-layout==X.Y.Z
/tmp/real/bin/python -c "import isabelle_layout, isabelle_layout.conformance as c; print(isabelle_layout.__version__, len(c.cases()))"
/tmp/real/bin/isabelle-layout --self-check
```

Then look at the project page: `twine check` says nothing about how the README
renders. Keep that `python -c` on one line — a `\` continuation inside double
quotes survives as a newline under csh, and Python rejects the indented line.

Finally, bump `version` to the next `.dev0` in its own commit, so an install
from the checkout never claims to be the release.

## A TestPyPI rehearsal, if the packaging changes shape

A separate installation — separate database, account, token and 2FA — and it
spends that version number there too.

```sh
.venv/bin/twine upload -r testpypi dist/isabelle_layout-X.Y.Z-*.whl dist/isabelle_layout-X.Y.Z.tar.gz
python3 -m venv /tmp/tp
/tmp/tp/bin/pip install --index-url https://test.pypi.org/simple/ --no-deps isabelle-layout
```

`--no-deps` because TestPyPI does not mirror PyPI, so a dependency resolves to
whatever unrelated thing sits there under that name. This package has none; the
habit is what stops a future one being satisfied by a stranger's package.

## What cannot be undone

- **A version number is permanent.** PyPI refuses a file for a version it has
  already seen, even after the release is deleted. A bad `X.Y.Z` is fixed by
  publishing `X.Y.Z+1`.
- **A pushed commit or tag is never rewritten** — see `CLAUDE.md`.
- **The author email is public** in the metadata of every artefact downloaded.
- **The name is claimed**, and already spent.
