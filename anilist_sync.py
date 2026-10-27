"""Fetch a public AniList anime list and build private repository exports."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import email.utils
import json
import math
import os
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


API_URL = "https://graphql.anilist.co"
USERNAME = "kaeudomt"
PAGE_SIZE = 50
MAX_PAGES = 100  # AniList Page queries have a 5,000-entry depth limit.
STATUSES = {"CURRENT", "COMPLETED", "PAUSED", "DROPPED", "PLANNING", "REPEATING"}
EXPORT_FILES = ("anime-list.json", "summary.json", "summary.md")

USER_QUERY = """
query UserScoreFormat($username: String!) {
  User(name: $username) { id name mediaListOptions { scoreFormat } }
}
"""

PAGE_QUERY = """
query AnimeListPage($username: String!, $page: Int!) {
  Page(page: $page, perPage: 50) {
    pageInfo { currentPage hasNextPage }
    mediaList(userName: $username, type: ANIME, sort: [MEDIA_ID]) {
      id mediaId status score progress repeat
      hiddenFromStatusLists customLists
      startedAt { year month day }
      completedAt { year month day }
      createdAt updatedAt
      media {
        id siteUrl format episodes seasonYear updatedAt
        title { english romaji native }
        startDate { year month day }
        genres
        studios { edges { isMain node { id name isAnimationStudio } } }
      }
    }
  }
}
"""

COLLECTION_QUERY = """
query AnimeListCollection($username: String!) {
  MediaListCollection(userName: $username, type: ANIME) {
    lists { name isCustomList entries { id mediaId } }
  }
}
"""


class SyncError(RuntimeError):
    """An incomplete or invalid fetch must never be committed."""


class AniListClient:
    def __init__(
        self,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval: float = 2.1,
        max_retries: int = 3,
    ) -> None:
        self.opener = opener
        self.sleeper = sleeper
        self.clock = clock
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_request: float | None = None

    def _pace(self) -> None:
        now = self.clock()
        if self._last_request is not None:
            remaining = self.min_interval - (now - self._last_request)
            if remaining > 0:
                self.sleeper(remaining)
        self._last_request = self.clock()

    @staticmethod
    def _retry_delay(header: str | None, attempt: int) -> float:
        if header:
            try:
                return max(0.0, float(header))
            except ValueError:
                try:
                    target = email.utils.parsedate_to_datetime(header)
                    return max(0.0, (target - dt.datetime.now(dt.timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        return min(2.0 ** attempt, 30.0)

    def query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        request = urllib.request.Request(
            API_URL,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "kaeudomt-anime-snapshot-for-AniList/1.0",
            },
            method="POST",
        )
        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                with self.opener(request, timeout=25) as response:
                    body = response.read()
            except urllib.error.HTTPError as exc:
                code, reason = exc.code, exc.reason
                retry_after = exc.headers.get("Retry-After")
                exc.close()
                if code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    self.sleeper(self._retry_delay(retry_after, attempt))
                    continue
                raise SyncError(f"AniList HTTP {code}: {reason}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.max_retries:
                    self.sleeper(self._retry_delay(None, attempt))
                    continue
                raise SyncError(f"AniList connection failed: {exc}") from exc
            try:
                result = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SyncError("AniList returned invalid JSON") from exc
            if not isinstance(result, dict):
                raise SyncError("AniList returned a non-object response")
            if result.get("errors"):
                errors = result["errors"]
                is_throttled = any(
                    isinstance(error, dict) and error.get("status") == 429
                    for error in errors
                ) if isinstance(errors, list) else False
                if is_throttled and attempt < self.max_retries:
                    self.sleeper(self._retry_delay(None, attempt))
                    continue
                raise SyncError(f"AniList GraphQL errors: {errors}")
            if not isinstance(result.get("data"), dict):
                raise SyncError("AniList returned no GraphQL data")
            return result["data"]
        raise SyncError("AniList retries exhausted")


def _fuzzy_date(value: Any) -> dict[str, int | None] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SyncError("Invalid AniList date")
    result = {part: value.get(part) for part in ("year", "month", "day")}
    for part, number in result.items():
        if number is not None and (not isinstance(number, int) or isinstance(number, bool)):
            raise SyncError(f"Invalid AniList date {part}")
    if result["month"] is not None and not 1 <= result["month"] <= 12:
        raise SyncError("Invalid AniList date month")
    if result["day"] is not None and not 1 <= result["day"] <= 31:
        raise SyncError("Invalid AniList date day")
    if not any(number is not None for number in result.values()):
        return None
    return result


def _custom_lists(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        return sorted(name for name, included in value.items() if included is True)
    if isinstance(value, list):
        return sorted(item["name"] for item in value if isinstance(item, dict) and item.get("enabled") is True and isinstance(item.get("name"), str))
    raise SyncError("Unexpected customLists shape")


def normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SyncError("Invalid media-list entry")
    media = raw.get("media")
    if not isinstance(media, dict):
        raise SyncError("Media-list entry has no media")
    entry_id, media_id = raw.get("id"), raw.get("mediaId")
    if (not isinstance(entry_id, int) or isinstance(entry_id, bool) or entry_id <= 0
            or not isinstance(media_id, int) or isinstance(media_id, bool) or media_id <= 0):
        raise SyncError("Media-list entry has invalid IDs")
    if media.get("id") != media_id:
        raise SyncError(f"Media ID mismatch for list entry {entry_id}")
    status = raw.get("status")
    if status not in STATUSES:
        raise SyncError(f"Unknown status for list entry {entry_id}: {status}")
    score = raw.get("score")
    if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or score < 0):
        raise SyncError(f"Invalid score for list entry {entry_id}")
    progress = raw.get("progress")
    if not isinstance(progress, int) or isinstance(progress, bool) or progress < 0:
        raise SyncError(f"Invalid progress for list entry {entry_id}")
    titles = media.get("title")
    if not isinstance(titles, dict):
        titles = {}
    studio_edges = (media.get("studios") or {}).get("edges") or []
    studios: dict[int, dict[str, Any]] = {}
    for edge in studio_edges:
        node = (edge or {}).get("node") or {}
        studio_id = node.get("id")
        if isinstance(studio_id, int) and studio_id > 0:
            previous = studios.get(studio_id)
            studios[studio_id] = {
                "id": studio_id,
                "name": node.get("name"),
                "is_main": bool((edge or {}).get("isMain")) or bool(previous and previous["is_main"]),
                "is_animation_studio": bool(node.get("isAnimationStudio")),
            }
    start_date = _fuzzy_date(media.get("startDate"))
    release_year = (start_date or {}).get("year") or media.get("seasonYear")
    return {
        "list_entry_id": entry_id,
        "media_id": media_id,
        "title": {language: titles.get(language) for language in ("english", "romaji", "native")},
        "status": status,
        "progress": progress,
        "score": score,
        "started_at": _fuzzy_date(raw.get("startedAt")),
        "completed_at": _fuzzy_date(raw.get("completedAt")),
        "genres": sorted(set(media.get("genres") or [])),
        "studios": sorted(studios.values(), key=lambda studio: studio["name"] or ""),
        "release_year": release_year,
        "release_date": start_date,
        "episode_count": media.get("episodes"),
        "format": media.get("format"),
        "site_url": media.get("siteUrl"),
        "custom_lists": _custom_lists(raw.get("customLists")),
        "hidden_from_status_lists": bool(raw.get("hiddenFromStatusLists")),
        "repeat_count": raw.get("repeat"),
        "list_created_at_unix": raw.get("createdAt"),
        "list_updated_at_unix": raw.get("updatedAt"),
        "media_updated_at_unix": media.get("updatedAt"),
    }


def fetch_snapshot(client: AniListClient, username: str = USERNAME) -> dict[str, Any]:
    user = client.query(USER_QUERY, {"username": username}).get("User")
    if not isinstance(user, dict) or user.get("name", "").casefold() != username.casefold():
        raise SyncError(f"AniList user {username!r} was not found")
    score_format = (user.get("mediaListOptions") or {}).get("scoreFormat")
    if not isinstance(score_format, str):
        raise SyncError("AniList did not return the user's score format")

    by_media: dict[int, dict[str, Any]] = {}
    by_entry: dict[int, int] = {}
    for page_number in range(1, MAX_PAGES + 1):
        page = client.query(PAGE_QUERY, {"username": username, "page": page_number}).get("Page")
        if not isinstance(page, dict) or not isinstance(page.get("pageInfo"), dict):
            raise SyncError(f"Missing AniList page {page_number}")
        page_info = page["pageInfo"]
        if page_info.get("currentPage") != page_number or not isinstance(page_info.get("hasNextPage"), bool):
            raise SyncError(f"Invalid pagination metadata on page {page_number}")
        items = page.get("mediaList")
        if not isinstance(items, list) or len(items) > PAGE_SIZE or (page_info["hasNextPage"] and not items):
            raise SyncError(f"Incomplete AniList page {page_number}")
        for raw in items:
            entry = normalize_entry(raw)
            old_media = by_entry.get(entry["list_entry_id"])
            if old_media is not None and old_media != entry["media_id"]:
                raise SyncError("Conflicting AniList list-entry IDs")
            by_entry[entry["list_entry_id"]] = entry["media_id"]
            previous = by_media.get(entry["media_id"])
            if previous is None or (entry["list_updated_at_unix"] or 0) >= (previous["list_updated_at_unix"] or 0):
                entry["custom_lists"] = sorted(set(entry["custom_lists"]) | set((previous or {}).get("custom_lists", [])))
                by_media[entry["media_id"]] = entry
        if not page_info["hasNextPage"]:
            break
    else:
        raise SyncError("AniList's 5,000-entry Page depth limit was reached; refusing an incomplete export")

    collection = client.query(COLLECTION_QUERY, {"username": username}).get("MediaListCollection")
    if not isinstance(collection, dict) or not isinstance(collection.get("lists"), list):
        raise SyncError("AniList returned no list collection for verification")
    collection_ids: set[int] = set()
    custom_by_id: dict[int, set[str]] = collections.defaultdict(set)
    for group in collection["lists"]:
        if not isinstance(group, dict) or not isinstance(group.get("entries"), list):
            raise SyncError("Invalid AniList collection group")
        for item in group["entries"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                raise SyncError("Invalid AniList collection entry")
            collection_ids.add(item["id"])
            if group.get("isCustomList") is True and isinstance(group.get("name"), str):
                custom_by_id[item["id"]].add(group["name"])
    if set(by_entry) != collection_ids:
        raise SyncError(
            f"Paginated list and collection disagree: pages={len(by_entry)}, collection={len(collection_ids)}; refusing an incomplete export"
        )
    if not by_media:
        raise SyncError("AniList returned an empty anime list; refusing to replace a valid export")
    for entry in by_media.values():
        entry["custom_lists"] = sorted(set(entry["custom_lists"]) | custom_by_id[entry["list_entry_id"]])
    entries = sorted(by_media.values(), key=lambda entry: entry["media_id"])
    snapshot = {
        "schema_version": 1,
        "username": user["name"],
        "anilist_user_id": user["id"],
        "score_format": score_format,
        "refreshed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "total_entries": len(entries),
        "entries": entries,
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    entries = snapshot.get("entries")
    if not isinstance(entries, list) or not entries or snapshot.get("total_entries") != len(entries):
        raise SyncError("Invalid snapshot entry count")
    media_ids = [entry.get("media_id") for entry in entries]
    entry_ids = [entry.get("list_entry_id") for entry in entries]
    if len(set(media_ids)) != len(entries) or len(set(entry_ids)) != len(entries):
        raise SyncError("Duplicate IDs in snapshot")
    for entry in entries:
        if (not isinstance(entry.get("media_id"), int) or entry["media_id"] <= 0
                or not isinstance(entry.get("list_entry_id"), int) or entry["list_entry_id"] <= 0
                or entry.get("status") not in STATUSES
                or not isinstance(entry.get("title"), dict)):
            raise SyncError("Invalid entry in snapshot")
    if not isinstance(snapshot.get("score_format"), str) or not snapshot.get("refreshed_at_utc", "").endswith("Z"):
        raise SyncError("Missing snapshot metadata")


def _display_title(entry: dict[str, Any]) -> str:
    title = entry["title"]
    return title.get("english") or title.get("romaji") or title.get("native") or f"AniList #{entry['media_id']}"


def _date_key(value: dict[str, int | None] | None) -> tuple[int, int, int]:
    value = value or {}
    return (value.get("year") or 0, value.get("month") or 0, value.get("day") or 0)


def _date_text(value: dict[str, int | None] | None) -> str:
    if not value or not value.get("year"):
        return "Unknown"
    parts = [str(value["year"])]
    if value.get("month"):
        parts.append(f"{value['month']:02d}")
        if value.get("day"):
            parts.append(f"{value['day']:02d}")
    return "-".join(parts)


def _brief(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "media_id": entry["media_id"],
        "title": _display_title(entry),
        "status": entry["status"],
        "score": entry["score"],
        "progress": entry["progress"],
        "episode_count": entry["episode_count"],
        "completed_at": entry["completed_at"],
        "site_url": entry["site_url"],
    }


def build_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    validate_snapshot(snapshot)
    entries = snapshot["entries"]
    rated = [entry for entry in entries if entry["score"] is not None and entry["score"] > 0]
    scores = [entry["score"] for entry in rated]
    statuses = collections.Counter(entry["status"] for entry in entries)
    distribution = collections.Counter(scores)
    top_rated = sorted(rated, key=lambda entry: (-entry["score"], _display_title(entry).casefold(), entry["media_id"]))[:10]
    recent = sorted(
        (entry for entry in entries if entry["status"] == "COMPLETED" and _date_key(entry["completed_at"])[0]),
        key=lambda entry: (_date_key(entry["completed_at"]), entry["media_id"]),
        reverse=True,
    )[:10]
    watching = sorted((entry for entry in entries if entry["status"] == "CURRENT"), key=lambda entry: _display_title(entry).casefold())
    viewing: dict[int, dict[str, int]] = collections.defaultdict(lambda: {"started": 0, "completed": 0})
    for entry in entries:
        for field, label in (("started_at", "started"), ("completed_at", "completed")):
            year = (entry[field] or {}).get("year")
            if year:
                viewing[year][label] += 1
    by_release: dict[int, list[float]] = collections.defaultdict(list)
    for entry in rated:
        if isinstance(entry["release_year"], int):
            by_release[entry["release_year"]].append(entry["score"])
    return {
        "schema_version": 1,
        "username": snapshot["username"],
        "refreshed_at_utc": snapshot["refreshed_at_utc"],
        "score_format": snapshot["score_format"],
        "score_scope": "All entries with a personal score greater than zero; zero means unrated.",
        "total_entries": len(entries),
        "completed_count": statuses["COMPLETED"],
        "currently_watching_count": statuses["CURRENT"],
        "status_counts": {status: statuses[status] for status in sorted(STATUSES)},
        "rated_entries": len(rated),
        "mean_score": round(statistics.mean(scores), 3) if scores else None,
        "median_score": statistics.median(scores) if scores else None,
        "score_distribution": [{"score": score, "count": distribution[score]} for score in sorted(distribution)],
        "top_rated": [_brief(entry) for entry in top_rated],
        "recently_completed": [_brief(entry) for entry in recent],
        "currently_watching": [_brief(entry) for entry in watching],
        "viewing_statistics_by_year": [{"year": year, **viewing[year]} for year in sorted(viewing)],
        "ratings_by_release_year": [
            {"year": year, "rated_entries": len(year_scores), "mean_score": round(statistics.mean(year_scores), 3), "median_score": statistics.median(year_scores)}
            for year, year_scores in sorted(by_release.items())
        ],
    }


def render_summary_markdown(summary: dict[str, Any]) -> str:
    def safe(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    def score_text(value: Any) -> str:
        return "unrated" if value is None or value == 0 else str(value)

    lines = [
        f"# {safe(summary['username'])}'s anime summary (for AniList, unofficial)",
        "",
        f"Last refreshed (UTC): **{summary['refreshed_at_utc']}**. This scheduled snapshot of public AniList data is stored in a private GitHub repository.",
        "",
        "For questions about every title or detailed metadata, see [anime-list.json](anime-list.json). For compact machine-readable totals, see [summary.json](summary.json).",
        "",
        "## Counts and scores",
        "",
        f"- Total entries: **{summary['total_entries']}**",
        f"- Completed: **{summary['completed_count']}**",
        f"- Currently watching: **{summary['currently_watching_count']}**",
        f"- Rated entries: **{summary['rated_entries']}**",
        f"- Score format: **{summary['score_format']}** (original AniList values)",
        f"- Mean / median of positive personal scores: **{summary['mean_score']} / {summary['median_score']}**",
        "- Zero or missing scores are excluded from score statistics.",
        "",
        "Status counts: " + ", ".join(f"{status} {count}" for status, count in summary["status_counts"].items()) + ".",
        "",
        "## Ten highest-rated anime",
        "",
        "| Anime | Score | Status |",
        "| --- | ---: | --- |",
    ]
    for entry in summary["top_rated"]:
        title = safe(entry["title"])
        if entry["site_url"]:
            title = f"[{title}]({entry['site_url']})"
        lines.append(f"| {title} | {entry['score']} | {entry['status']} |")
    lines += ["", "## Currently watching", ""]
    if summary["currently_watching"]:
        for entry in summary["currently_watching"]:
            episode_count = entry["episode_count"] if entry["episode_count"] is not None else "?"
            lines.append(f"- {safe(entry['title'])}: episode {entry['progress']}/{episode_count}; {score_text(entry['score'])}.")
    else:
        lines.append("- None.")
    lines += ["", "## Recently completed", ""]
    if summary["recently_completed"]:
        for entry in summary["recently_completed"]:
            lines.append(f"- {_date_text(entry['completed_at'])}: {safe(entry['title'])} ({score_text(entry['score'])}).")
    else:
        lines.append("- No entries have a completion date.")
    lines += ["", "## Score distribution", "", "| Score | Entries |", "| ---: | ---: |"]
    for item in summary["score_distribution"]:
        lines.append(f"| {item['score']} | {item['count']} |")
    lines += ["", "## Viewing dates by year", "", "These counts use the dates recorded on AniList entries, not an episode-by-episode viewing history.", "", "| Year | Started | Completed |", "| ---: | ---: | ---: |"]
    for item in summary["viewing_statistics_by_year"]:
        lines.append(f"| {item['year']} | {item['started']} | {item['completed']} |")
    lines += ["", "## Ratings by release year", "", "| Release year | Rated entries | Mean | Median |", "| ---: | ---: | ---: | ---: |"]
    for item in summary["ratings_by_release_year"]:
        lines.append(f"| {item['year']} | {item['rated_entries']} | {item['mean_score']} | {item['median_score']} |")
    return "\n".join(lines) + "\n"


def write_exports(output: Path, snapshot: dict[str, Any]) -> None:
    validate_snapshot(snapshot)
    summary = build_summary(snapshot)
    markdown = render_summary_markdown(summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="anilist-export-", dir=output.parent) as temporary:
        staging = Path(temporary)
        (staging / "anime-list.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (staging / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (staging / "summary.md").write_text(markdown, encoding="utf-8")
        validate_output(staging)
        if output.exists() and {path.name for path in output.iterdir()} - set(EXPORT_FILES):
            raise SyncError("Output directory contains unrelated files; refusing to copy over them")
        output.mkdir(parents=True, exist_ok=True)
        for filename in EXPORT_FILES:
            os.replace(staging / filename, output / filename)


def validate_output(output: Path) -> None:
    try:
        if {path.name for path in output.iterdir()} != set(EXPORT_FILES):
            raise SyncError("Export directory must contain exactly three files")
        snapshot = json.loads((output / "anime-list.json").read_text(encoding="utf-8"))
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        markdown = (output / "summary.md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"Export validation failed: {exc}") from exc
    validate_snapshot(snapshot)
    if summary.get("total_entries") != snapshot["total_entries"] or summary.get("refreshed_at_utc") != snapshot["refreshed_at_utc"]:
        raise SyncError("Summary and full list disagree")
    if snapshot["refreshed_at_utc"] not in markdown:
        raise SyncError("Readable exports lack the current timestamp")


def sync_exports(output: Path, snapshot: dict[str, Any]) -> bool:
    """Update tracked files only when AniList content differs from the last snapshot."""
    validate_snapshot(snapshot)
    if output.exists() and {path.name for path in output.iterdir()} == set(EXPORT_FILES):
        validate_output(output)
        previous = json.loads((output / "anime-list.json").read_text(encoding="utf-8"))
        comparable = {**snapshot, "refreshed_at_utc": previous["refreshed_at_utc"]}
        expected_summary = build_summary(comparable)
        saved_summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        saved_markdown = (output / "summary.md").read_text(encoding="utf-8")
        if (previous == comparable and saved_summary == expected_summary
                and saved_markdown == render_summary_markdown(expected_summary)):
            return False
    write_exports(output, snapshot)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data"), help="Directory for the three private repository exports")
    parser.add_argument("--validate-output", type=Path, help="Validate an existing export directory without contacting AniList")
    parser.add_argument("--skip-unchanged", action="store_true", help="Keep existing files and timestamp when AniList data has not changed")
    args = parser.parse_args(argv)
    try:
        if args.validate_output:
            validate_output(args.validate_output)
            print(f"Validated {args.validate_output}")
        else:
            snapshot = fetch_snapshot(AniListClient())
            if args.skip_unchanged:
                changed = sync_exports(args.output, snapshot)
            else:
                write_exports(args.output, snapshot)
                changed = True
            state = "Updated" if changed else "Unchanged"
            print(f"{state}: {snapshot['total_entries']} anime for {snapshot['username']} at {args.output}")
        return 0
    except SyncError as exc:
        print(f"AniList sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
