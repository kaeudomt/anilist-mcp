# Repository configuration and deployment history

The user approved private deployment on 2026-10-27, then explicitly requested that [`kaeudomt/anilist-mcp`](https://github.com/kaeudomt/anilist-mcp) become **public**. GitHub reported `visibility: public` and `has_pages: false` after the change. The Pages site endpoint still returned HTTP 404.

## Repository and workflow

| Setting | Proposed value |
| --- | --- |
| GitHub owner | `kaeudomt`, confirmed by the user's approval and GitHub CLI authentication |
| Repository | `kaeudomt/anilist-mcp`, **public** |
| Default branch | `main` |
| GitHub Pages | **Disabled**; repository files are public through GitHub itself |
| Workflow | `.github/workflows/sync.yml` |
| Triggers | `0 17 * * *` UTC (00:00 ICT daily) and manual `workflow_dispatch` |
| Job token | Built-in, repository-scoped `GITHUB_TOKEN` with only `contents: write` |
| Actions used | Official `actions/checkout@v7` and `actions/setup-python@v7` |
| Tracked data | `data/anime-list.json`, `data/summary.json`, `data/summary.md` |
| External credentials | None; AniList public GraphQL requires no OAuth |

The GitHub CLI was reauthenticated through its browser device flow and verified the authenticated account as `kaeudomt`. The scheduled workflow itself needs no personal access token.

The workflow runs tests, fetches and validates the complete AniList list, compares it with the committed snapshot while ignoring the retrieval timestamp, and commits only if content changed. `actions/checkout` keeps the built-in token available to authenticated `git push` for that job; it is not added to a commit. A failed API fetch or validation prevents the commit and leaves the previous remote data in place. A push failure, including branch protection blocking the bot, fails the run and requires fixing repository settings.

If a snapshot changes, all three files get the same new UTC retrieval timestamp. If data is unchanged, files and timestamp stay as they were, avoiding a timestamp-only commit. The latest Actions run is the evidence of the latest *check*; the file timestamp is the time the current committed snapshot was retrieved.

## Public data and permissions

Anyone can read and copy the repository's current files, **Git history**, and Actions logs. Earlier snapshots can remain in that history after later commits. The exports contain AniList list data, including personal scores, statuses, progress, start/completion dates, custom lists, and timestamps. The code does not export notes, reviews, manga, or credentials. A scan of the committed history before the visibility change found no common credential patterns.

The GitHub connection in ChatGPT is separate from `GITHUB_TOKEN`. Public repository files can be fetched without GitHub authorization, but ChatGPT's ability to retrieve the complete list remains unverified in an ordinary Plus conversation.

GitHub Pages remains disabled. The public GitHub repository and its raw file URLs expose the exports directly; no Pages deployment is configured.

GitHub's [60-day public-repository inactivity rule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) can disable the scheduled workflow if no repository activity occurs. The export workflow intentionally avoids commits for unchanged data, so its schedule should be monitored.

The workflow requires permission to push to the default branch. The workflow file grants only `contents: write`; check organization restrictions or branch rules if GitHub rejects the push. No personal access token is planned.

## Deployment checks

The user authorized private deployment and subsequently authorized making the repository public. Verify that Pages remains disabled and that scheduled runs continue to succeed. The ChatGPT account-side test in the [historical compatibility report](feasibility-private-github.md) remains separate and must succeed before claiming ChatGPT compatibility. Do not enable Pages without explicit approval.
