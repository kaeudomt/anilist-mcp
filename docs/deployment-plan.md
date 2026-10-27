# Private repository and deployment configuration

The user approved private deployment on 2026-10-27. The repository is [`kaeudomt/anilist-mcp`](https://github.com/kaeudomt/anilist-mcp). GitHub reported `private: true`, default branch `main`, and `has_pages: false` before the first push; the Pages site endpoint returned HTTP 404.

## Repository and workflow

| Setting | Proposed value |
| --- | --- |
| GitHub owner | `kaeudomt`, confirmed by the user's approval and GitHub CLI authentication |
| Repository | `kaeudomt/anilist-mcp`, **private** |
| Default branch | `main` |
| GitHub Pages | **Disabled** and verified disabled before pushing any exports |
| Workflow | `.github/workflows/sync.yml` |
| Triggers | `0 17 * * *` UTC (00:00 ICT daily) and manual `workflow_dispatch` |
| Job token | Built-in, repository-scoped `GITHUB_TOKEN` with only `contents: write` |
| Actions used | Official `actions/checkout@v7` and `actions/setup-python@v7` |
| Tracked data | `data/anime-list.json`, `data/summary.json`, `data/summary.md` |
| External credentials | None; AniList public GraphQL requires no OAuth |

The GitHub CLI was reauthenticated through its browser device flow and verified the authenticated account as `kaeudomt`. The scheduled workflow itself needs no personal access token.

The workflow runs tests, fetches and validates the complete AniList list, compares it with the committed snapshot while ignoring the retrieval timestamp, and commits only if content changed. `actions/checkout` keeps the built-in token available to authenticated `git push` for that job; it is not added to a commit. A failed API fetch or validation prevents the commit and leaves the previous remote data in place. A push failure, including branch protection blocking the bot, fails the run and requires fixing repository settings.

If a snapshot changes, all three files get the same new UTC retrieval timestamp. If data is unchanged, files and timestamp stay as they were, avoiding a timestamp-only commit. The latest Actions run is the evidence of the latest *check*; the file timestamp is the time the current committed snapshot was retrieved.

## Privacy and permissions

Only people and apps authorized to read the private repository can access its files through GitHub. The exports still enter the repository's **Git history**; earlier snapshots can remain in that history after later commits. The exports contain public AniList list data, including personal scores, statuses, progress, start/completion dates, custom lists, and timestamps. The code does not export notes, reviews, manga, or credentials.

The GitHub connection in ChatGPT is separate from `GITHUB_TOKEN`. The user must connect the GitHub plugin and authorize access to this private repository. Installing a plugin alone does not grant repository access. The user's GitHub authorization screen may request broader permissions; review it before accepting. No ChatGPT repository access or complete-file retrieval is claimed until tested in the user's ordinary Plus chat.

For a new private repository, Pages should have no site. For an existing repository, check **Settings → Pages** and disable any publishing source and existing site before pushing exports. GitHub states [Pages sites can be public even when their repository is private](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site), so repository privacy alone is insufficient.

The workflow requires permission to push to the default branch. The workflow file grants only `contents: write`; check organization restrictions or branch rules if GitHub rejects the push. No personal access token is planned.

## Deployment checks

The user authorized creating and pushing this private repository and running the workflow. Before pushing data, verify visibility is **private** and Pages is disabled. After pushing, run the workflow manually once, inspect the private files and Actions log, and repeat the privacy checks. The ChatGPT account-side test in [the compatibility report](feasibility-private-github.md) remains separate and must succeed before claiming ChatGPT compatibility. Never make this repository public or enable Pages without fresh explicit approval.
