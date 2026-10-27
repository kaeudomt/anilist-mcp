# Private GitHub repository to ChatGPT Plus: feasibility

Checked **2026-10-27**. This distinguishes official documentation, local evidence, and account-side questions.

## Confirmed by official documentation

- OpenAI says [plugins work in regular Chat and Work](https://learn.chatgpt.com/docs/plugins) on ChatGPT web, desktop, and mobile. The catalog includes a GitHub plugin. A plugin may require a separate service connection before its tools become available. Availability depends on the plan, workspace, plugin, and authenticated account.
- OpenAI says [a plugin's availability does not grant access to connected files](https://learn.chatgpt.com/docs/enterprise/apps-and-connectors). The connected GitHub identity must have repository access, and the enabled tool actions must permit the read. Installing or connecting GitHub is therefore not proof that ChatGPT can read a particular private repository.
- GitHub's [Pages documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site) explicitly warns that a Pages site can be publicly accessible even if its repository is private. Pages must stay disabled.
- GitHub creates a [repository-scoped `GITHUB_TOKEN`](https://docs.github.com/en/actions/concepts/security/github_token) for Actions jobs. A workflow can request only [`contents: write`](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) to push committed files. This ordinary self-repository push needs no personal access token; branch rules may still block it.
- [Scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) run from the default branch and can be delayed or dropped under load. GitHub's 60-day inactivity auto-disable rule is stated for **public** repositories; it does not apply as documented to the proposed private repository. Other causes, such as a disabled workflow or inactive actor, can still stop scheduling. GitHub Free currently includes [2,000 private-repository Actions minutes per month](https://docs.github.com/en/billing/reference/product-usage-included).

## Verified in the project and private repository

- The GitHub plugin is listed as installed in this environment's plugin directory, but its repository tools and this user's private-repository authorization are not available in this session. This is **not** a ChatGPT Plus private-file access test.
- A live, unauthenticated AniList GraphQL POST fetch returned **170 unique entries** for `kaeudomt`, including **65 completed** and **3 currently watching**. The full snapshot was cross-checked against `MediaListCollection`. The exported JSON was about **287 KB** and the Markdown summary about **4 KB** at that run. Counts can change.
- Local tests verify that unchanged AniList content causes no file update, a changed entry updates all exports, and an API failure leaves previously valid files untouched. On 2026-10-27, `kaeudomt/anilist-mcp` was created as **private** with `main` as default and Pages disabled. The first manual Actions run succeeded without a commit because data was unchanged. A small summary-rendering change then caused the second manual run to commit and push all three refreshed exports as `github-actions[bot]` (`d0b5724`). The remote full JSON had 170 entries and 170 distinct media IDs, with refresh timestamp `2026-10-27T15:36:06Z`. Scheduled execution at a future six-hour interval has not yet been observed.

## Not established by documentation or local tests

| Question | Current result |
| --- | --- |
| Can this Plus account authorize the GitHub plugin for this specific private repository? | **Requires account-side authorization and test.** Plugin availability alone is insufficient. |
| Can the plugin read Markdown and JSON file contents? | **Not confirmed for these exact files.** Generic plugin documentation does not specify this GitHub plugin's file-read behavior. |
| Will ChatGPT retrieve the latest committed file rather than stale or indexed content? | **Not guaranteed.** Compare the file's UTC timestamp and a newly changed value after a scheduled run. |
| Can a regular ChatGPT conversation read all 170 entries from the roughly 287 KB JSON file? | **Not confirmed.** Tool output or context limits may truncate the file. A summary-only success is insufficient for full-list questions. |

The repository and GitHub Actions route is now **deployed and tested**, but ChatGPT file access remains **plausible and conditional**, not a verified end-to-end integration. The ChatGPT success criterion must be tested separately before declaring the project complete.

## Exact ChatGPT Plus test after private deployment

1. In ChatGPT's plugin directory, open GitHub, connect the correct GitHub account, and grant the plugin access to **only** the chosen private repository if GitHub offers that choice. Inspect the requested permissions. Start a new **ordinary Chat** conversation, rather than Codex or Work.
2. Ask: “Use the connected GitHub plugin to read `data/summary.md` from `kaeudomt/anilist-mcp` on its `main` branch. Give its exact UTC refresh timestamp, total, completed count, and currently watching count. Cite the repository file or show the tool source.” Confirm those values against GitHub's private file view.
3. Ask: “Read `data/anime-list.json` from the same repository. Count the entries and distinct `media_id` values from the entire JSON. Report the first and last `media_id`, and the status counts. State plainly if your tool returned only a preview or truncated content.” Compare with the committed JSON and AniList. **All entries must be counted**, not inferred from `summary.json`.
4. Ask about a specific title absent from `summary.md` and confirm its original score and progress from `anime-list.json`. This checks detail access beyond the summary.
5. After a future genuine AniList change and a successful workflow run, repeat the file read and compare the new timestamp/value with GitHub's latest commit. If ChatGPT cannot access the repository, only finds summaries, truncates the JSON, or returns stale data, the full ChatGPT goal remains unmet.

GitHub's private repository prevents anonymous public access. The connected service still sends requested file content to ChatGPT under the user's authorized connection; see OpenAI's [connected-service data-flow description](https://learn.chatgpt.com/docs/enterprise/apps-and-connectors). AniList's [API terms](https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/terms-of-use) discourage using the API as a backup or bulk store. This design retains one active snapshot per commit, but Git history preserves earlier versions; treating this limited personal analytics use as acceptable is an inference, not AniList approval.
