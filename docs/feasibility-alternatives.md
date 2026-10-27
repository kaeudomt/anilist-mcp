# Historical AniList access alternatives (superseded)

**This report predates the [private GitHub repository proposal](feasibility-private-github.md). It does not assess the current workflow or establish private GitHub access in ChatGPT.**

Checked on **2026-10-27** for the public AniList user `kaeudomt`. This is a feasibility report, not an integration implementation. No ChatGPT Plus account-side test was performed.

## Result

**No no-hosting approach has been verified to meet all requirements.** AniList's GraphQL endpoint returned public list data through POST, but it rejected a correctly encoded GET query. That removes the proposed direct-link route. OpenAI currently says personal Plus accounts cannot create new custom GPTs, so a new GPT Action is not an available setup path. An existing published ChatGPT plugin is the remaining plausible no-hosting option, but I did not find or test an AniList plugin available to this account.

## 1. Direct GraphQL GET and browsing

AniList's [current GraphQL getting-started guide](https://docs.anilist.co/guide/graphql/) says all GraphQL requests must use **POST** to `https://graphql.anilist.co`. Its [media-list guide](https://docs.anilist.co/guide/graphql/queries/media-list) recommends `MediaListCollection` for a complete list, requires `type` and either `userName` or `userId`, and warns that entries hidden from standard status lists can appear in custom lists. It also documents an 11,000 most-recently-updated unique-entry ceiling for that query.

This is a syntactically valid **GraphQL-over-HTTP GET URL** for the public anime list, but it is **not a working AniList request**:

```text
https://graphql.anilist.co/?query=query%7BMediaListCollection%28userName%3A%22kaeudomt%22%2Ctype%3AANIME%29%7Blists%7Bname+entries%7Bid+media%7Bid+title%7Bromaji%7D%7D%7D%7D%7D%7D
```

It is only 179 characters long, so this failure is unrelated to a long URL. A richer query would make the URL longer, but I found no published AniList or ChatGPT browsing URL-length guarantee to rely on. `MediaListCollection` avoids client pagination for this user's observed list size; a paginated query would require multiple POST calls. AniList public data does not require OAuth, per its [API v2 migration guide](https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/migration/version-1/index).

**Actual API tests, 2026-10-27 around 15:00 UTC, without AniList credentials:**

| Test | Observed result |
| --- | --- |
| `GET https://graphql.anilist.co` with the URL-encoded `query` parameter above | HTTP **404**, JSON `data: null`, error `Not Found.`, hint `Use POST request to access graphql subdomain.` |
| `POST https://graphql.anilist.co` with JSON body containing a read-only `MediaListCollection(userName:"kaeudomt",type:ANIME)` query | HTTP **200**, 22,456-byte JSON body, no GraphQL errors; **170 entries with 170 distinct entry IDs** across Completed 65, Dropped 6, Planning 95, Paused 1, Watching 3. All returned `isCustomList: false` in this snapshot. |
| POST response rate headers | `X-RateLimit-Limit: 30`, `X-RateLimit-Remaining: 29`. |

The GET test used `curl --get --data-urlencode 'query=…'`; the POST test used `Content-Type: application/json` and no Authorization header. The POST output establishes that the public account is accessible through the documented method **at the time of testing**. These counts can change as the account changes. AniList's [rate-limit guide](https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/rate-limiting) documents a temporary 30-request-per-minute degraded limit, `429` responses, `Retry-After`, and a burst limiter.

**ChatGPT browsing:** OpenAI's [web-search documentation](https://developers.openai.com/api/docs/guides/tools-web-search) describes searching and opening pages, but does not establish a way for an ordinary ChatGPT browsing request to issue an arbitrary JSON POST to AniList. My research browsing tool could not open the encoded GET URL; it reported the URL inaccessible. That tool is **not a test of your ChatGPT Plus browser**. Regardless of browsing access, AniList itself rejected the GET request. Browsing AniList's human-facing profile might help with a single visible title, but complete, fresh list extraction and statistics are **unverified** through that route.

## 2. Custom GPT Actions

OpenAI's [current GPT availability guidance](https://help.openai.com/en/articles/8554407-gpts-in-chatgpt) and [troubleshooting guidance](https://help.openai.com/en/articles/11325361-troubleshooting-gpts) say personal ChatGPT Plus accounts **cannot create new custom GPTs**. Existing GPTs may remain usable and editable where account permissions allow. This blocks creating a new GPT Action for this project on the stated subscription.

For an account that already has an editable GPT, [OpenAI's Actions guide](https://help.openai.com/en/articles/9442513-configuring-actions-in-gpts) requires an OpenAPI JSON/YAML schema and permits **None** as the authentication method. An OpenAPI `POST /` operation with an `application/json` body containing GraphQL `query` and optional `variables` is technically expressible. AniList public reads need no AniList OAuth. **Inference:** a direct Action might avoid middleware if the GPT editor accepts that schema and sends the body as specified. I did not test the GPT editor or an Action call, so direct GraphQL compatibility and complete-response handling remain **unverified**. OpenAI describes GPT Actions primarily as calls to RESTful APIs in its [Actions introduction](https://developers.openai.com/api/docs/actions/introduction), not as a tested AniList GraphQL integration.

An existing custom GPT can be [@-mentioned from a regular ChatGPT web conversation](https://help.openai.com/en/articles/8554407-gpts-in-chatgpt), retaining that conversation's context, but the next message is routed to that GPT. It is not an ambient AniList connection in every ordinary message. New GPT creation is unavailable on this Plus account, and custom GPTs are being [retired in favor of plugins](https://help.openai.com/en/articles/20001519), so this is not a reliable new setup route.

## 3. Existing integrations

The [ChatGPT plugin directory](https://help.openai.com/en/articles/20001256-plugins-in-chatgpt) is available across plans, but an individual plugin's installation and tools depend on the plan and its capabilities. Installed plugins can be used in ChatGPT conversations. A directory search through the available plugin discovery tool for **AniList** and **AniBridge** returned no match on 2026-10-27; that search is **not exhaustive** and does not prove no such plugin exists in your ChatGPT directory.

Open-source projects do exist, including [Grinv's AniList MCP server](https://github.com/Grinv/anilist-mcp-server) and [yuna0x0's AniList MCP server](https://github.com/yuna0x0/anilist-mcp). Their project documentation describes public AniList read access; the first uses local stdio, and the second documents local/hosted HTTP transport. Neither was verified as a published, Plus-accessible ChatGPT plugin. Some expose account mutation tools or optional authentication, so they should not be assumed read-only. Using either directly would bring back local runtime or hosting setup.

## Comparison and recommendation

| Rank | Approach | Setup and maintenance | Complete fresh list in ordinary Plus Chat | Finding |
| --- | --- | --- | --- | --- |
| 1, conditional | Install an existing **published AniList ChatGPT plugin**, if one is available to your account and has full-list read tools | No hosting; possible app connection | Potentially, but **unverified** | Best route to test next |
| 2, limited | Ask ChatGPT to browse the public AniList profile | No setup | **Unverified** for complete list and reliable statistics | Useful only for exploratory individual-title questions |
| 3 | Direct GraphQL GET link | No setup | **No** | AniList returned HTTP 404 and requires POST |
| 4 | New custom GPT with a direct GraphQL Action | Would need schema setup; no hosting if direct POST works | **Unavailable** for new GPT creation on personal Plus; direct GraphQL Action untested | Do not build around it |

**Recommendation:** Search the plugin directory in your own ChatGPT Plus account before doing any implementation. If no suitable plugin is available, there is currently no verified zero-hosting route that supplies the complete current anime list on demand in ordinary Plus chats. A custom hosted or tunneled integration would remain a separate, conditional project, with plan access to custom MCP connections requiring account-side verification.

### Exact account-side test for a promising plugin

1. In **ChatGPT web → Plugins**, search `AniList`, `anime list`, and `AniBridge`. Inspect any candidate's included app, required sign-in, and tool descriptions. Look specifically for a tool that retrieves **all** public anime list entries, including custom lists. Prefer one that exposes only read tools or lets you disable write tools.
2. If a suitable candidate is available on Plus, install it and open a **new regular Chat** conversation. Select or `@`-mention the plugin and ask: “Read the complete public anime list for `kaeudomt` from AniList now. Report the total and counts by status, including custom-list-only entries, and show the source/tool calls used.”
3. Check that a live plugin tool call occurred and that the result includes all statuses. Compare the answer with the AniList website at that moment; this report's **170 total / 65 completed** is only a 2026-10-27 snapshot, not a permanent expected value.
4. Ask again after a visible AniList change to verify freshness. Then test a title lookup and a statistics question. If the plugin omits custom lists, uses cached data without a refresh path, requires OAuth you do not want, or cannot run in regular Chat, it does not meet the goal.

No plugin was installed and no user-account ChatGPT compatibility test was performed for this report.
