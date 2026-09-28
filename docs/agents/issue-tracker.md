# Issue tracker: GitHub

Issues and specs (PRDs) for this repo are GitHub issues on `ozanozbeker/oxyscraper`. Use the `gh` CLI for every operation. Inside the clone, `gh` reads the repo from the git remote.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for a multi-line body.
- **Read an issue**: `gh issue view <number> --comments`. Fetch the labels too, and filter comments with `jq`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`. Add `--label` and `--state` filters as needed.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply or remove labels**: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` to triage external PRs as feature requests. `/triage` reads this flag.)_

When the flag is `yes`, PRs take the same labels and states as issues. Use the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments`, and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`, then keep only an `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR` or `NONE`. Drop `OWNER`, `MEMBER` and `COLLABORATOR`.
- **Comment, label or close**: `gh pr comment`, `gh pr edit --add-label` or `--remove-label`, `gh pr close`.

Issues and PRs share one number space, so a bare `#42` can be either. Try `gh pr view 42` first, then `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

`/wayfinder` uses these. The **map** is one issue, and its **child** issues are the tickets.

- **Map**: one issue labelled `wayfinder:map`, whose body holds the Notes, Decisions-so-far and Fog sections. Create it with `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue, through `gh api` on the sub-issues endpoint. If sub-issues are not enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Label it `wayfinder:<type>`, where the type is `research`, `prototype`, `grilling` or `task`.
- **Blocking**: use GitHub's **native issue dependencies**, the canonical form that the UI shows. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`. `<blocker-db-id>` is the blocker's numeric **database id** from `gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ its `#number` or `node_id`. `issue_dependencies_summary.blocked_by` counts open blockers only. If dependencies are not available, put a `Blocked by: #<n>, #<n>` line at the top of the child body instead. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children with `gh issue list --state open`, scoped to the map's sub-issues or task list. Drop any child with an assignee or an open blocker: `issue_dependencies_summary.blocked_by > 0`, or an open issue in its `Blocked by` line. Take the first remaining child in map order.
- **Claim**: `gh issue edit <n> --add-assignee @me`. Make this the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist and link) to the map's Decisions-so-far.
