# Publishing a release

Written for the first release, when none of it was habit yet, and kept because
the parts that bit are not the parts anyone expects. Everything here is
checkable, so where a step exists to prevent a specific failure, the failure is
named.

*Not shipped in the sdist:* this is our release process, not something anyone
downloading the source needs — see `exclude` in `pyproject.toml`.

## The short version, now that the repository exists

```sh
# 1. drop the `.dev0` from `version` in pyproject.toml, and reinstall
# 2. commit, with the RELEASE NOTES as the commit message
git push origin main
git push origin vX.Y.Z            # triggers the Release workflow
rm -rf dist && python -m build && twine check --strict dist/* && twine upload dist/*
```

The rest of this file is why each of those is shaped the way it is.

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

**The release notes go in the version-bump commit's message.** That is not a
style preference: `.github/workflows/release.yml` reads
`repos/<repo>/commits/<tag>` and publishes that commit's message as the GitHub
Release body. So the release commit is written *for users* — what changed since
the last release — and everything about how the work happened belongs in the
commits around it.

```sh
git commit -m "0.2.2 — first published release" -m "## Added …"
git tag -a v0.2.2 -m "isabelle-layout 0.2.2"
git push origin main
git push origin v0.2.2      # `git push` alone does not push tags
```

Pushing the tag is the whole publish: the workflow creates the Release from the
runner, so nothing local needs `gh` or the web UI. It is idempotent, so a
re-pushed tag repairs a bad publish rather than erroring.

Do **not** put the notes in the tag annotation. `--notes-from-tag` reads the
annotation and silently falls back to the commit message when the runner's
local tag is lightweight, which mis-published `isabelle-query` v0.2.5's first
run. Dereferencing the tag to its commit is deterministic, so that is what the
workflow does — and it means the annotation is read by nothing.

The workflow must exist in the **tagged commit's tree**: for `on: push: tags`,
Actions resolves the workflow from the pushed ref, not from the default branch.

Tag *before* uploading to PyPI, so the tag names the tree that produced the
artefacts. If the upload then fails and something has to change, the fix is a
new version, not a moved tag — a tag that moves after being pushed is worse
than no tag.

**Do not `--amend` a release commit that has been pushed, ever.** It leaves the
branch a *sibling* of what the remote has rather than a descendant, so the next
push is rejected and the only ways out are a force-push or a reconciling
merge — both worse than the imperfect message that prompted it. This cost the
0.2.0 number. Version numbers before first publication are free; history that
other people may have fetched is not.

Untracked working files (`.scratch-*`, `dist/`, `.venv/`) are not pushed.

---

## Part 2 — the PyPI account, once

1. Register at <https://pypi.org/account/register/> and verify the email.
2. **Enable 2FA** — PyPI requires it for uploads. Save the recovery codes
   somewhere you will still have them after losing the phone.

### The token

**`isabelle-layout` now exists on PyPI, so use a token scoped to it.** Account
settings → *API tokens* → *Add API token*, scope `isabelle-layout`. It is shown
exactly once — `pypi-AgEIcHlwaS5vcmc…` — so copy it immediately.

The awkward step is only ever the *first* upload of a project, and it is
already paid here: PyPI cannot scope a token to a project that does not exist,
so 0.2.2 needed an **account-scoped** token. That token can publish anything
you own and should have been revoked straight after.

**For the next new project** — `isabelle-query`, `isabelle-watchdog` — do not
repeat that. Register a **pending publisher** instead: Account settings →
*Publishing* → the project name plus GitHub owner, repo, workflow filename and
environment, all before the project exists. The first upload then comes from
Actions over OIDC, creates the project, and no token is needed at any point.
That is **Trusted Publishing**, and it also removes the token from this laptop
for projects already published.

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
that it consumes version `0.2.2` on TestPyPI, so a second rehearsal needs a
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
- [ ] Check the Release actually published. Pushing the tag triggers
      `.github/workflows/release.yml`, which creates it from the tagged
      commit's message; nothing local is required. If the body looks wrong,
      fix the commit message on a *new* commit, re-tag that, and push — the
      workflow edits an existing Release rather than erroring.
- [ ] Add the CI matrix. `requires-python = ">=3.9"` and the classifiers
      through 3.14 are currently verified *statically only* — every module
      parses under `ast.parse(feature_version=(3, 9))`, all carry
      `from __future__ import annotations`, and there is no runtime PEP 604,
      no match statement and no post-3.9 stdlib call. Only 3.14 is installed
      on this machine. This is the first thing to add after release.
- [x] `isabelle-query`'s upper bound. It declared
      `isabelle-layout>=0.1.0,<0.2.0`, which `0.2.0` does not satisfy, and with
      0.1.x never published there was no earlier release to fall back to.
      Already fixed upstream (`>=0.2.0`, floor only) before this release —
      nothing to do, but check it still reads that way before uploading, since
      a cap is the one thing that can make a correct publish unusable.

---

## What cannot be undone

- **A version number is permanent.** PyPI refuses a file for a version it has
  already seen, even after the release is deleted. A bad `0.2.2` is fixed by
  publishing `0.2.3`, never by re-uploading. This is the only genuinely
  unrecoverable step, and it is why the rehearsal is worth one evening.
- **The author email becomes public** on the project page and in the metadata
  of every downloaded artefact.
- **The name is claimed.** `isabelle-layout` becomes yours on first upload.
