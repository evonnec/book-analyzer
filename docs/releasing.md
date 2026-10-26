# Releasing

Releases are cut from a git tag. Pushing a tag `vX.Y.Z` triggers
`.github/workflows/release.yml`, which checks, builds, and creates a GitHub Release, and
optionally publishes to PyPI.

## Versioning policy (SemVer)

The version lives in `pyproject.toml` (`project.version`) and follows
[Semantic Versioning](https://semver.org). For this CLI the public interface is the command
line: the arguments, the stdin message format, the stdout format, and exit codes.

- MAJOR: breaking change to the input or output format, the arguments, or exit codes, or
  dropping a supported Python version.
- MINOR: backwards-compatible features, such as new options or new accepted input forms.
- PATCH: backwards-compatible bug fixes, docs, and internal changes.

Pre-releases use PEP 440 suffixes such as `1.0.0rc1`, tagged `v1.0.0rc1`. The tag must be the
normalized form (`1.0.0-rc.1` is not accepted). Pre-releases are marked as such on GitHub.

## Release steps

1. Open a PR that bumps `version` in `pyproject.toml` and refreshes the lock file:

   ```sh
   uv version --bump patch   # or minor / major; or: uv version 1.0.0rc1
   uv lock
   ```

   Merge it once CI is green.
2. After the merge, update `main` and confirm the version:

   ```sh
   git switch main && git pull
   grep -m1 '^version' pyproject.toml
   ```
3. Tag that commit and push the tag:

   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

## What the workflow does

1. Checks out the tag and installs Python (from `.python-version`) and locked dependencies.
2. Fails if the tag is not a valid version tag, or does not equal `v` + `project.version`.
3. Runs ruff (lint and format), mypy, and pytest.
4. Runs `uv build` (sdist and wheel) and smoke tests the wheel in a clean environment.
5. Creates a GitHub Release with generated notes and the wheel and sdist attached.
6. If the repository variable `PUBLISH_TO_PYPI` is `true`, the `publish-pypi` job uploads the
   same files to PyPI with `uv publish` using Trusted Publishing (OIDC, no API tokens). It
   runs in the `pypi` environment, so any required reviewers must approve it first.

The workflow can also be run manually (Actions, Release, Run workflow) with the name of an
existing tag.

## One-time PyPI setup

1. On pypi.org, go to Your projects, Publishing, and add a pending trusted publisher:
   PyPI project name `book-analyzer`, owner `evonnec`, repository `book-analyzer`, workflow
   `release.yml`, environment `pypi`.
2. In the GitHub repo, Settings, Environments, create an environment named `pypi`
   (optionally with required reviewers).
3. In Settings, Secrets and variables, Actions, Variables, add `PUBLISH_TO_PYPI` = `true`.

The first successful publish turns the pending publisher into a normal one. PyPI never allows
re-uploading a version, so a published version cannot be replaced.

## Recovering from a bad tag

Delete the GitHub Release (if one was created) and the tag, fix the problem, and tag again:

```sh
gh release delete vX.Y.Z --yes          # if the release exists
git push origin --delete vX.Y.Z
git tag -d vX.Y.Z
```

- Tag does not match `pyproject.toml`, or checks failed before the release was created: fix
  via a PR, merge, then re-tag the new commit with the same version.
- Already published to PyPI: that version is burned. Optionally yank it on pypi.org, then
  release a new patch version.
