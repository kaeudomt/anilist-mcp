# Private anime snapshot for AniList (unofficial)

This project reads the public anime list for AniList user `kaeudomt` and writes three files to `data/` in the [private `kaeudomt/anilist-mcp` repository](https://github.com/kaeudomt/anilist-mcp). GitHub Actions is configured to check AniList every six hours and commit only when the list data changes. No AniList credentials, local server, database, or GitHub Pages site is required.

## Local use

Requires Python 3.12 or newer. There are no third-party Python dependencies.

```bash
python3 -m unittest discover -s tests -v
python3 anilist_sync.py --output data --skip-unchanged
python3 anilist_sync.py --validate-output data
```

| Tracked file | Contents |
| --- | --- |
| `data/anime-list.json` | All public anime entries, original AniList scores and metadata |
| `data/summary.json` | Counts, scores, recent activity, and year statistics |
| `data/summary.md` | Compact human-readable summary |

The exporter uses GraphQL POST requests, follows paginated results, and checks list-entry IDs against `MediaListCollection` to catch missing custom-list entries. It retries transient failures and rate limits. An API or validation failure stops the workflow before a commit. The `refreshed_at_utc` timestamp in committed files records when **that committed snapshot** was fetched. If a later check finds identical data, the workflow makes no commit, so the timestamp stays the same; the Actions run history shows when it last checked.

The account's AniList score format is stored with the original score values. Zero, which AniList uses for an unrated entry, remains zero in the complete file and is excluded from score statistics. Viewing-by-year statistics count recorded start and completion dates.

## Private deployment

The workflow is [`.github/workflows/sync.yml`](.github/workflows/sync.yml). It runs at 00:17, 06:17, 12:17, and 18:17 UTC, and can be run manually. It uses the repository-scoped `GITHUB_TOKEN` with only `contents: write`; it commits and pushes the three export files when they change. GitHub Pages must remain disabled. The [private deployment plan](docs/deployment-plan.md) lists the exact permissions and approval gate.

After an approved deployment, connect the GitHub plugin in ChatGPT and authorize this **specific private repository**. The [compatibility report](docs/feasibility-private-github.md) gives an exact test for normal ChatGPT Plus conversations. We have **not** verified that ChatGPT can retrieve the full JSON file or its latest commit through that connection.

## Confirm scheduled checks

Open the private repository's **Actions → Sync private AniList snapshot** page. Confirm that scheduled runs appear after 00:17, 06:17, 12:17, and 18:17 UTC and complete successfully; GitHub may delay or occasionally drop a scheduled run. A successful run logs either `Updated` or `Unchanged`. On `Updated`, inspect the newest commit and matching timestamps in all three `data/` files. On `Unchanged`, the files keep the previous retrieval timestamp and no commit is expected. Enable GitHub Actions failure notifications for the repository so a stopped or failing schedule is noticed.
