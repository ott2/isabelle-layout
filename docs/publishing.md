# Publishing a release

Written for the first release, when none of it was habit yet. Everything here
is checkable, so where a step exists to prevent a specific failure, the failure
is named.

## The order, and why it is not arbitrary

**GitHub first, then the tag, then PyPI.** The built metadata contains
`Project-URL: Homepage, https://github.com/ott2/isabelle-layout`, which PyPI
renders as a link on the project page. Publishing before the repository exists
ships a release whose own metadata 404s, and the metadata cannot be corrected
without a new version number.

---

## Part 1 — GitHub

**Create the repository empty.** No README, no `.gitignore`, no licence file.
GitHub offers to add them, and each one creates a commit on the remote that the
local history does not have, so the first `git push` is rejected as a
non-fast-forward — recoverable only by merging an unrelated history or forcing.

```sh
git remote add origin git@github.com:ott2/isabelle-layout.git   # or https://
git push -u origin main
```

Then tag the commit the artefacts were built from, and push the tag
separately — `git push` does not push tags:

```sh
git tag -a v0.1.0 -m "isabelle-layout 0.1.0"
git push origin v0.1.0
```

Tag *before* uploading, so the tag names the tree that produced the artefacts.
If the upload then fails and something has to change, the fix is a new version,
not a moved tag — a tag that moves after being pushed is worse than no tag.

Untracked working files (`.scratch-*`, `dist/`, `.venv/`) are not pushed.

---

## Part 2 — the PyPI account, once

1. Register at <https://pypi.org/account/register/> and verify the email.
2. **Enable 2FA** — PyPI requires it for uploads. Save the recovery codes
   somewhere you will still have them after losing the phone.

### The token, and why the first one is different

PyPI scopes API tokens to a project, but it cannot scope one to a project that
does not exist yet. So the first upload needs an **account-scoped** token:

* Account settings → *API tokens* → *Add API token*
* Scope: **Entire account**
* Copy it immediately — `pypi-AgEIcHlwaS5vcmc…`. It is shown exactly once.

After the first successful upload, create a token scoped to
`isabelle-layout` and **revoke the account-scoped one**. An account-scoped
token can publish anything you own, so it should exist for one upload only.

The long-term answer is **Trusted Publishing** — GitHub Actions authenticates
to PyPI over OIDC and no token exists to leak. It needs a workflow file, which
is the CI deliberately deferred at 0.1.0. Set it up when the CI matrix lands;
it also works for a project that does not yet exist, via a *pending publisher*.

---

## Part 3 — giving twine the token

The username is the literal string `__token__`, not your account name.

**Recommended: `~/.pypirc`.** It avoids shell quoting entirely, which matters
because the token is long and the correct incantation differs between shells.

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc…

[testpypi]
username = __token__
password = pypi-AgENdGVzdC5weXBpLm9yZw…
```

```sh
chmod 600 ~/.pypirc
```

List **both** index servers if you write this file. Twine defaults
`index-servers` to `pypi testpypi` and fills in both URLs, but only while the
key is absent — naming just `pypi` silently removes TestPyPI's default URL.
No `repository =` lines are needed; twine knows both.

*Alternative, no file:* omit `~/.pypirc` and twine prompts for username and
password. The prompt is fine; `-r testpypi` still resolves correctly.

*Alternative, environment:* `TWINE_USERNAME` / `TWINE_PASSWORD`. Note that the
`VAR=value command` prefix form is `sh`/`bash`/`zsh` syntax and does **not**
work in `csh`/`tcsh`; use `env TWINE_USERNAME=__token__ TWINE_PASSWORD=… twine
upload dist/*`, which works everywhere.

---

## Part 4 — the TestPyPI rehearsal (optional, recommended once)

TestPyPI is a **separate installation**: separate database, separate account,
separate token, separate 2FA. Registering on one gives you nothing on the
other. Register at <https://test.pypi.org/account/register/>.

```sh
twine upload -r testpypi dist/*
```

Then install it the way a stranger would, into a throwaway environment:

```sh
python3 -m venv /tmp/tp
/tmp/tp/bin/pip install --index-url https://test.pypi.org/simple/ --no-deps isabelle-layout
/tmp/tp/bin/python -c "import isabelle_layout, isabelle_layout.conformance as c; \
    print(isabelle_layout.__version__, len(c.cases()))"
```

`--no-deps` because TestPyPI does not mirror real PyPI, so any dependency
resolves to whatever unrelated thing happens to sit there under that name.
This package has none, so it changes nothing today — but the habit is what
stops a future dependency being silently satisfied by a stranger's package.

**What the rehearsal proves that `twine check` does not:** how the README
actually renders on a project page, that the upload credentials work, and that
a real `pip install` from an index yields an importable package with its data
files. **What it does not prove:** anything about real PyPI's state — and note
that it consumes version `0.1.0` on TestPyPI, so a second rehearsal needs a
different version.

---

## Part 5 — the upload

Rebuild from a clean `dist/`. `twine upload dist/*` uploads whatever is in the
directory, so a stale artefact from an earlier version is uploaded without
comment.

```sh
rm -rf dist
python -m build
twine check --strict dist/*
twine upload dist/*
```

`python -m build` builds the sdist, then builds the wheel **from that sdist**,
so this also checks that the sdist is complete — a file present locally but
missing from `[tool.hatch.build.targets.sdist] include` fails here rather than
in a user's checkout.

If an upload half-completes, `twine upload --skip-existing dist/*` re-runs it
without erroring on the files that already landed.

Then verify as a stranger:

```sh
python3 -m venv /tmp/real
/tmp/real/bin/pip install isabelle-layout
/tmp/real/bin/python -c "import isabelle_layout; print(isabelle_layout.__version__)"
```

---

## Part 6 — after the first upload

- [ ] Create a project-scoped API token; **revoke the account-scoped one**.
- [ ] Cut a GitHub Release against `v0.1.0` (optional; the tag is the record).
- [ ] Add the CI matrix. `requires-python = ">=3.9"` and the classifiers
      through 3.14 are currently verified *statically only* — every module
      parses under `ast.parse(feature_version=(3, 9))`, all carry
      `from __future__ import annotations`, and there is no runtime PEP 604,
      no match statement and no post-3.9 stdlib call. Only 3.14 is installed
      on this machine. This is the first thing to add after release.
- [ ] Tell `isabelle-query` the floor is real: it pins
      `isabelle-layout>=0.1.0,<0.2.0` against a package that did not exist on
      an index until now.

---

## What cannot be undone

- **A version number is permanent.** PyPI refuses a file for a version it has
  already seen, even after the release is deleted. A bad `0.1.0` is fixed by
  publishing `0.1.1`, never by re-uploading. This is the only genuinely
  unrecoverable step, and it is why the rehearsal is worth one evening.
- **The author email becomes public** on the project page and in the metadata
  of every downloaded artefact.
- **The name is claimed.** `isabelle-layout` becomes yours on first upload.
