# Publishing a release

The steps, in order. Where a step exists to prevent a specific failure, it
names the failure. The two pushes and the upload are outward-facing, so they
are taken only when asked for.

Commands assume tcsh and the repository's `.venv`
(`.venv/bin/pip install build twine`, once).

*Not shipped in the sdist:* this is our release process, not something anyone
downloading the source needs — see `exclude` in `pyproject.toml`.

## 1. Pre-flight

- **The tests pass against a real install**:
  `.venv/bin/pip install '.[test]' && .venv/bin/python -m pytest`. Not `-e`:
  whether the package data ships is the one question an editable install
  cannot answer.
- **The 3.9 floor holds.** There is no CI matrix and only 3.14 is installed
  here, so it is checked statically:

  ```sh
  .venv/bin/python -c "import ast,pathlib; [ast.parse(p.read_text(), str(p), feature_version=(3,9)) for p in pathlib.Path('src').rglob('*.py')]"
  ```

  That catches post-3.9 *grammar* — a `match` statement fails it — and nothing
  else. A PEP 604 annotation like `int|str` parses clean under it and breaks
  only when evaluated, so the other half is read by eye: every annotated module
  carries `from __future__ import annotations`, and no post-3.9 stdlib call has
  crept in.
- **No consumer caps this package.** `isabelle-query` declares
  `isabelle-layout>=0.2.0` — floor, no ceiling. A `<` bound upstream is the one
  thing that can make a correct publish unusable.
- **The version is unused on PyPI.** Should print 404:

  ```sh
  curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/isabelle-layout/X.Y.Z/json
  ```

## 2. The release commit

1. Drop the `.dev0` from `version` in `pyproject.toml`, and reinstall.
2. Commit with the **release notes as the commit message**: subject
   `X.Y.Z — summary`, then markdown written for users about what changed.
   `.github/workflows/release.yml` publishes that message as the GitHub Release
   and reads nothing else — a tag annotation in particular is ignored. The
   alternative, `--notes-from-tag`, reads the annotation and falls back silently
   to the commit message when the runner's tag is lightweight, which
   mis-published `isabelle-query` v0.2.5.

## 3. Build, before tagging

```sh
rm -rf dist
.venv/bin/python -m build
.venv/bin/twine check --strict dist/*
tar tzf dist/*.tar.gz
```

- `rm -rf dist` because `twine upload dist/*` uploads whatever it finds, a
  stale artefact from an earlier version included.
- `build` makes the wheel *from the sdist*, so a file missing from
  `[tool.hatch.build.targets.sdist] include` fails here rather than in a user's
  checkout.
- `tar tzf` should list `src/`, `docs/decisions.md`, `scripts/`, `tests/`,
  `README.md`, `LICENSE`, `pyproject.toml`, `PKG-INFO` and `.gitignore` — and
  neither `docs/publishing.md` nor `scripts/verify_move.py`.

Build before tagging: a broken build costs nothing, while a pushed tag should
never move.

## 4. Tag and push

```sh
git tag -a vX.Y.Z -m "isabelle-layout X.Y.Z"
git push origin main
git push origin vX.Y.Z
```

`git push` does not push tags on its own, and the tag push is the whole GitHub
publish — the workflow creates the Release on the runner, so nothing local
needs `gh`. Actions resolves the workflow from the pushed ref rather than from
the default branch, so it must already exist in the tagged commit's tree (it
does). Re-pushing a tag is idempotent, so it repairs a bad publish rather than
erroring:

```sh
curl -s https://api.github.com/repos/ott2/isabelle-layout/releases/tags/vX.Y.Z
```

If the notes are wrong, fix them in a *new* commit, tag that, and push; the
workflow edits an existing Release rather than failing. Never `--amend` a
release commit that has been pushed — it leaves the branch a *sibling* of the
remote rather than a descendant, and the only ways out are a force-push or a
reconciling merge.

Tag before uploading to PyPI, so the tag names the tree that produced the
artefacts.

## 5. Upload to PyPI

```sh
.venv/bin/twine upload dist/*
```

The username is the literal string `__token__`, not an account name, and the
token must be scoped to `isabelle-layout`. `~/.pypirc` at mode 600 avoids shell
quoting, which matters because the token is long:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc…
```

List **both** index servers if you write that file. Twine defaults
`index-servers` to `pypi testpypi` and fills in both URLs, but only while the
key is absent; naming just `pypi` silently removes TestPyPI's. Twine will
otherwise prompt, which is fine. Under tcsh the `VAR=value command` prefix form
does not work — use `env TWINE_USERNAME=__token__ TWINE_PASSWORD=…
.venv/bin/twine upload dist/*`.

A half-completed upload is re-run with `--skip-existing`.

**Trusted Publishing** would remove the token from this laptop: the upload
comes from Actions over OIDC instead. Registering a *pending publisher* before
a project's first upload also avoids the account-scoped token that a first
upload otherwise requires, PyPI being unable to scope a token to a project that
does not yet exist.

## 6. Verify as a stranger would

```sh
python3 -m venv /tmp/real
/tmp/real/bin/pip install isabelle-layout==X.Y.Z
/tmp/real/bin/python -c "import isabelle_layout, isabelle_layout.conformance as c; \
    print(isabelle_layout.__version__, len(c.cases()))"
/tmp/real/bin/isabelle-layout --self-check
```

Then look at the project page and the Release. `twine check` says nothing about
how the README actually renders.

## 7. Afterwards

Bump `version` to the next `.dev0` in its own commit, so that an install from
the checkout never claims to be the release.

## A rehearsal on TestPyPI, if the packaging has changed shape

TestPyPI is a **separate installation** — separate database, account, token and
2FA. Registering on one gives nothing on the other.

```sh
.venv/bin/twine upload -r testpypi dist/*
python3 -m venv /tmp/tp
/tmp/tp/bin/pip install --index-url https://test.pypi.org/simple/ --no-deps isabelle-layout
```

`--no-deps` because TestPyPI does not mirror real PyPI, so any dependency
resolves to whatever unrelated thing happens to sit there under that name. This
package has none, so it changes nothing today — the habit is what stops a future
dependency being silently satisfied by a stranger's package. A rehearsal
consumes that version number on TestPyPI, so a second one needs a new version.

## What cannot be undone

- **A version number is permanent.** PyPI refuses a file for a version it has
  already seen, even after the release is deleted. A bad `X.Y.Z` is fixed by
  publishing `X.Y.Z+1`, never by re-uploading.
- **A pushed commit or tag is never rewritten.** No `--amend`, no moved tag, no
  force-push — see `CLAUDE.md`.
- **The author email is public**, on the project page and in the metadata of
  every artefact ever downloaded.
- **The name is claimed.** Already spent: `isabelle-layout` is ours.
