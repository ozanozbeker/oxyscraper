# Contributing

This file holds how oxyscraper is changed, tested and released.
[How is oxy versioned, documented and released?](https://github.com/ozanozbeker/oxyscraper/issues/22) records each decision and the evidence for it.

## Setup

You need [uv](https://docs.astral.sh/uv/) and the [GitHub CLI](https://cli.github.com/).

```sh
uv sync
uv run prek install
```

`prek install` writes a `pre-commit` hook, which runs the linters, and a `commit-msg` hook, which checks the message format.
The tests run in CI, not in a hook.

## Pull requests

Every change reaches `main` through a pull request, the maintainer's included.
CI then runs before the change lands.

```sh
git switch main && git pull
git switch -c <branch>
git commit
git push
gh pr create --fill
gh pr merge --auto --squash
```

- `git commit` runs the `pre-commit` and `commit-msg` hooks.
  A hook that fixes a file stops the commit, so run `git add -A` and commit again.
- `gh pr create --fill` copies the message of a single commit into the pull request.
  With several commits, pass `--title` yourself.
- `gh pr merge --auto --squash` merges the pull request once the required checks pass.
  `gh pr checks --watch` shows them.

Pull requests merge by squash only, and the squash commit takes the pull request's title and description.
Since release-please reads that commit:

- The title follows [Conventional Commits](https://www.conventionalcommits.org/).
  The `title` check runs the `commit-msg` hook from `prek.toml` against it.
- A breaking change ends the description with a one-line `BREAKING CHANGE:` footer that links to its section of the upgrade page.
- To correct a merged entry, edit the merged pull request's description.
  Put the corrected message between `BEGIN_COMMIT_OVERRIDE` and `END_COMMIT_OVERRIDE`, and release-please uses it on its next run.

## Pull requests from bots

- Dependabot opens `chore: bump the uv group` and `ci: bump the actions group` on Mondays.
- `prek-update.yml` opens `chore: update prek hooks and dev floors` on the first of each month.
- release-please opens `chore(main): release X.Y.Z`, and it updates that pull request after each merge that users would see.

Their types start no release, so merge the first two with `gh pr merge <number> --auto --squash` once they pass.
The release pull request waits until you want to release.

## What the rulesets block

- The `main` ruleset blocks every push to `main`, and a merge before `all-green` and `title` pass.
  The admin can still merge a failing pull request with **Merge without waiting for requirements to be met**, so keep that for emergencies.
- The `version tags` ruleset lets only the App and the admin create, update or delete a `v*` tag.

## Versions

Versions follow [SemVer](https://semver.org/).
Below 1.0, a new minor always means a breaking change.

| Commit | Changelog | Bump below 1.0 |
| --- | --- | --- |
| `feat`, `fix`, `perf`, `docs`, `deps`, `revert` | visible | patch |
| `refactor`, `test`, `build`, `ci`, `style`, `chore` | hidden | none on its own |
| any type with `!`, or a `BREAKING CHANGE:` footer | visible | minor |

`bump-minor-pre-major` and `bump-patch-for-minor-pre-major` in `release-please-config.json` set the last column.
No commit reaches 1.0 on its own.
Leaving `0.x` takes a `Release-As: 1.0.0` footer, and the policy for after 1.0 is set then.

## Breaking changes

The pull request that makes a break also writes its migration into [`user_guide/upgrading.qmd`](user_guide/upgrading.qmd), under the next minor's heading, such as `## 0.4`.
Every break before a release goes into the same next minor, so the heading is known when the pull request opens.
Below 1.0, a break needs no deprecation period.

## CI

`ci.yml` runs on each pull request and each push to `main`:

- `test` runs on Ubuntu, macOS and Windows, on every supported Python, against the built wheel.
- `next-python` runs the next CPython from its first beta, and it may fail.
- `lowest` runs the floor Python with each dependency at its floor.
- `coverage` runs the tests on Ubuntu and the newest Python, and fails under 100% line coverage.
  The config excludes only `TYPE_CHECKING` blocks, so every other exclusion is a `# pragma: no cover` that a reviewer sees.
  The job uploads the report to Codecov, and a failed upload fails no check.
- `lint` runs every prek hook on every file.
- `docs` builds the site, which runs every example.
- `all-green` passes when the jobs above pass.
  The `main` ruleset requires only this job and `title`, so a change to the jobs never touches the ruleset.

pytest turns warnings into errors, so a new upstream deprecation fails the Dependabot pull request that brings it in.

## Live tests

pytest deselects the tests marked `live`, because they call the Oxylabs API and bill the account.
A run bills about 11 results.

- `live.yml` runs `pytest -m live` weekly and on manual dispatch, in the `live` environment.
- The environment holds the secrets `OXY_WSA_USERNAME`, `OXY_WSA_PASSWORD` and `OXYLAKE_URI`.
  A missing secret fails the run instead of skipping it.
- The job stays outside `all-green`, so a fork's pull request never needs a secret and an Oxylabs outage blocks no merge.

To run the suite locally, put the same three variables in `.env`:

```sh
uv run --env-file .env pytest -m live
```

Set `OXY_CAPTURES` to a folder outside the repo to keep every request and response in `exchanges.jsonl`.
The captures hold the account's client name, so they stay out of the repo and out of CI.

## Dependencies

Each runtime floor in `pyproject.toml` is as low as the `lowest` job proves, except the `httpx2` floor.
The job proves 2.10.0, and the floor is 2.12.0, because a user's security audit flags every version below it.
[Why oxy's floor is 2.12.0](docs/research/httpx2.md#why-oxys-floor-is-2120) records the costs below that version.
A runtime floor rises only in a `deps:` commit, which the changelog shows to users.
Each floor in the `dev` group equals the tool's version in `uv.lock`.
Users never install that group, so a `chore:` commit raises its floors.
Dependabot moves `uv.lock` and the pinned actions weekly, after a 7-day cooldown that its security updates skip.
Its `chore` and `ci` prefixes keep those pull requests out of the changelog.
Dependabot does not read `prek.toml` and raises no floor, so `prek-update.yml` updates the hooks and sets each `dev` floor to its locked version monthly.

## Python versions

oxyscraper supports every CPython that has not reached its end of life.

- A version joins at its final release.
  Add its classifier in `pyproject.toml` and its entry in the `test` matrix, and point `next-python` at the version after it.
- A version leaves in the first release after its end of life, in a `feat!:` commit.
  Raise `requires-python`, `.python-version`, ruff's `target-version`, `default_language_version` in `prek.toml` and the Python of the `lowest` job.
  Then remove the version's classifier and its matrix entry.

## Releasing

1. release-please keeps a release pull request open with the next version, `CHANGELOG.md` and `uv.lock`.
2. Merging it makes the App create the tag and the GitHub release.
3. `release.yml` builds the distributions, and its `pypi` job waits for approval.
   On the run's page, click **Review deployments**, tick `pypi`, then click **Approve and deploy**.
   The job then uploads the distributions to PyPI with attestations.
4. `docs.yml` deploys the site.

A release published by hand starts the same two workflows, which makes it the recovery path.

## When something fails

- **A CI job fails.**
  `gh pr checks` names the job, and `gh run view <run-id> --log-failed` prints its log.
  Push a fix to the same branch, and auto-merge stays on.
- **The title check fails.**
  Fix the title with `gh pr edit --title`, and the check runs again.
- **A changelog entry is wrong after the merge.**
  Use `BEGIN_COMMIT_OVERRIDE`, as [Pull requests](#pull-requests) describes.
- **`release.yml` or `docs.yml` fails after the tag exists.**
  `gh run rerun <run-id> --failed` runs the failed jobs again.

## Traps

- Never pass `release-type` to `release-please-action`.
  The action then ignores `release-please-config.json`, and it prints no warning.
- The `uv.lock` JSONPath in `release-please-config.json` reads `@.name.value`, not `@.name`.
  release-please parses each TOML value into an object, and without `.value` it updates nothing.
- An edit to the release pull request's body is lost when `main` moves before the merge, and it never reaches `CHANGELOG.md`.
  Migration notes go in the upgrade page.
- `GITHUB_TOKEN` cannot run CI on a pull request it opens, and a release it creates starts no workflow.
  So release-please and `prek-update.yml` use the App's token.
- The `pypi` and `github-pages` environments accept `v*` tags only, and both release workflows run on the release's tag.
- A numpydoc `Returns` block starts with a `:` line.
  griffe, which great-docs uses, reads a bare description line as the return type.

## Repository settings

The workflows need these settings, which GitHub holds outside the repo:

1. Install a GitHub App on the repo, with write access to contents, issues and pull requests.
2. Create the `release` environment for `main` only, with the variable `APP_CLIENT_ID` and the secret `APP_PRIVATE_KEY`.
3. Create the `pypi` environment for `v*` tags only, with a required reviewer and no admin bypass.
4. Create the `live` environment for `main` only, with the secrets that the live tests read.
5. Add a pending trusted publisher on PyPI for `release.yml` and the `pypi` environment.
6. Sign the repo in to Codecov.
   The `coverage` job uploads with OIDC, so it needs no token.
7. Set Pages to deploy from GitHub Actions, and limit the `github-pages` environment to `v*` tags.
8. Allow squash merges only, with the pull request title and description.
   Turn on auto-merge, head branch deletion, required SHA pinning, Dependabot alerts and security updates, and CodeQL default setup.
9. After the first CI run, add the rulesets.
   The `main` ruleset requires a pull request with no approvals, squash merges, and the `all-green` and `title` checks.
   It blocks force pushes and deletion, and the admin can bypass it for pull requests only.
   The tag ruleset lets only the App and the admin create, update or delete `v*` tags.
