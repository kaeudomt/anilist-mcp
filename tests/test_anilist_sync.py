import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import anilist_sync as sync


def raw_entry(entry_id=1, media_id=101, score=8.5, status="COMPLETED", completed_year=2024):
    return {
        "id": entry_id,
        "mediaId": media_id,
        "status": status,
        "score": score,
        "progress": 12,
        "repeat": 0,
        "hiddenFromStatusLists": False,
        "customLists": {"Favorites": True, "Other": False},
        "startedAt": {"year": 2023, "month": None, "day": None},
        "completedAt": {"year": completed_year, "month": 2, "day": 3} if completed_year else None,
        "createdAt": 1_700_000_000,
        "updatedAt": 1_710_000_000,
        "media": {
            "id": media_id,
            "siteUrl": f"https://anilist.co/anime/{media_id}",
            "format": "TV",
            "episodes": 12,
            "seasonYear": 2022,
            "updatedAt": 1_720_000_000,
            "title": {"english": f"Show {media_id}", "romaji": None, "native": None},
            "startDate": {"year": 2022, "month": 4, "day": 1},
            "genres": ["Drama", "Drama"],
            "studios": {"edges": [
                {"isMain": True, "node": {"id": 5, "name": "Studio A", "isAnimationStudio": True}},
                {"isMain": False, "node": {"id": 5, "name": "Studio A", "isAnimationStudio": True}},
            ]},
        },
    }


class FakeClient:
    def __init__(self, pages, collection=None):
        self.pages = pages
        self.collection = collection
        self.calls = []

    def query(self, query, variables):
        self.calls.append(variables)
        if "UserScoreFormat" in query:
            return {"User": {"id": 9, "name": variables["username"], "mediaListOptions": {"scoreFormat": "POINT_10_DECIMAL"}}}
        if "AnimeListPage" in query:
            number = variables["page"]
            return {"Page": {"pageInfo": {"currentPage": number, "hasNextPage": number < len(self.pages)}, "mediaList": self.pages[number - 1]}}
        if self.collection is not None:
            return {"MediaListCollection": self.collection}
        ids = {item["id"]: item["mediaId"] for page in self.pages for item in page}
        return {"MediaListCollection": {"lists": [{"name": "Completed", "isCustomList": False, "entries": [{"id": key, "mediaId": value} for key, value in ids.items()]}]}}


class ParsingTests(unittest.TestCase):
    def test_missing_metadata_and_partial_date(self):
        raw = raw_entry()
        raw["media"].update({"title": {"romaji": "Only Romaji"}, "genres": None, "studios": None, "startDate": None, "seasonYear": 2021, "episodes": None})
        entry = sync.normalize_entry(raw)
        self.assertEqual(entry["title"], {"english": None, "romaji": "Only Romaji", "native": None})
        self.assertEqual(entry["release_year"], 2021)
        self.assertEqual(entry["genres"], [])
        self.assertEqual(entry["studios"], [])
        self.assertEqual(entry["started_at"], {"year": 2023, "month": None, "day": None})
        self.assertEqual(entry["custom_lists"], ["Favorites"])

    def test_invalid_date_rejected(self):
        raw = raw_entry()
        raw["startedAt"]["month"] = 15
        with self.assertRaises(sync.SyncError):
            sync.normalize_entry(raw)

    def test_studios_deduplicated(self):
        entry = sync.normalize_entry(raw_entry())
        self.assertEqual(entry["genres"], ["Drama"])
        self.assertEqual(entry["studios"], [{"id": 5, "name": "Studio A", "is_main": True, "is_animation_studio": True}])


class FetchTests(unittest.TestCase):
    def test_pages_duplicates_and_custom_only_membership(self):
        first = raw_entry()
        duplicate = raw_entry()
        second = raw_entry(2, 102, score=0, status="CURRENT", completed_year=None)
        client = FakeClient(
            pages=[[first], [duplicate, second]],
            collection={"lists": [
                {"name": "Completed", "isCustomList": False, "entries": [{"id": 1, "mediaId": 101}]},
                {"name": "Favorites", "isCustomList": True, "entries": [{"id": 1, "mediaId": 101}, {"id": 2, "mediaId": 102}]},
            ]},
        )
        snapshot = sync.fetch_snapshot(client)
        self.assertEqual(snapshot["total_entries"], 2)
        self.assertEqual([entry["media_id"] for entry in snapshot["entries"]], [101, 102])
        self.assertEqual(snapshot["entries"][1]["custom_lists"], ["Favorites"])
        self.assertEqual(len([call for call in client.calls if "page" in call]), 2)

    def test_collection_mismatch_fails(self):
        client = FakeClient(
            pages=[[raw_entry()]],
            collection={"lists": [{"name": "Completed", "isCustomList": False, "entries": [{"id": 77, "mediaId": 177}]}]},
        )
        with self.assertRaisesRegex(sync.SyncError, "disagree"):
            sync.fetch_snapshot(client)

    def test_missing_page_fails(self):
        class BrokenClient(FakeClient):
            def query(self, query, variables):
                if "AnimeListPage" in query:
                    return {"Page": None}
                return super().query(query, variables)

        with self.assertRaisesRegex(sync.SyncError, "Missing AniList page"):
            sync.fetch_snapshot(BrokenClient([[raw_entry()]]))


class SummaryAndExportTests(unittest.TestCase):
    def snapshot(self):
        entries = [
            sync.normalize_entry(raw_entry(1, 101, score=8.5, completed_year=2024)),
            sync.normalize_entry(raw_entry(2, 102, score=7.5, completed_year=2023)),
            sync.normalize_entry(raw_entry(3, 103, score=0, status="CURRENT", completed_year=None)),
        ]
        return {"schema_version": 1, "username": "kaeudomt", "anilist_user_id": 9, "score_format": "POINT_10_DECIMAL", "refreshed_at_utc": "2026-10-27T00:00:00Z", "total_entries": 3, "entries": entries}

    def test_score_dates_and_release_year(self):
        summary = sync.build_summary(self.snapshot())
        self.assertEqual(summary["rated_entries"], 2)
        self.assertEqual(summary["mean_score"], 8)
        self.assertEqual(summary["median_score"], 8)
        self.assertEqual(summary["score_distribution"], [{"score": 7.5, "count": 1}, {"score": 8.5, "count": 1}])
        self.assertEqual(summary["completed_count"], 2)
        self.assertEqual(summary["currently_watching_count"], 1)
        self.assertEqual(summary["viewing_statistics_by_year"], [
            {"year": 2023, "started": 3, "completed": 1},
            {"year": 2024, "started": 0, "completed": 1},
        ])
        self.assertEqual(summary["ratings_by_release_year"], [{"year": 2022, "rated_entries": 2, "mean_score": 8, "median_score": 8}])

    def test_export_generation_and_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "public"
            sync.write_exports(output, self.snapshot())
            sync.validate_output(output)
            self.assertEqual({path.name for path in output.iterdir()}, set(sync.EXPORT_FILES))
            self.assertEqual(json.loads((output / "anime-list.json").read_text())["entries"][0]["score"], 8.5)
            self.assertIn("2026-10-27T00:00:00Z", (output / "summary.md").read_text())

    def test_unchanged_data_preserves_files_and_retrieval_timestamp(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "data"
            original_snapshot = self.snapshot()
            self.assertTrue(sync.sync_exports(output, original_snapshot))
            before = {name: (output / name).read_bytes() for name in sync.EXPORT_FILES}
            fresh_snapshot = self.snapshot()
            fresh_snapshot["refreshed_at_utc"] = "2026-10-27T06:00:00Z"
            self.assertFalse(sync.sync_exports(output, fresh_snapshot))
            self.assertEqual(before, {name: (output / name).read_bytes() for name in sync.EXPORT_FILES})

    def test_changed_data_updates_all_exports(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "data"
            self.assertTrue(sync.sync_exports(output, self.snapshot()))
            changed = self.snapshot()
            changed["refreshed_at_utc"] = "2026-10-27T06:00:00Z"
            changed["entries"][0]["progress"] = 10
            self.assertTrue(sync.sync_exports(output, changed))
            sync.validate_output(output)
            saved = json.loads((output / "anime-list.json").read_text())
            self.assertEqual(saved["entries"][0]["progress"], 10)
            self.assertEqual(saved["refreshed_at_utc"], "2026-10-27T06:00:00Z")

    def test_changed_summary_rendering_creates_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "data"
            self.assertTrue(sync.sync_exports(output, self.snapshot()))
            markdown = output / "summary.md"
            markdown.write_text(markdown.read_text() + "Stale extra line\n")
            fresh = self.snapshot()
            fresh["refreshed_at_utc"] = "2026-10-27T06:00:00Z"
            self.assertTrue(sync.sync_exports(output, fresh))
            self.assertNotIn("Stale extra line", markdown.read_text())
            self.assertIn("2026-10-27T06:00:00Z", markdown.read_text())

    def test_fetch_failure_preserves_existing_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "public"
            sync.write_exports(output, self.snapshot())
            original = (output / "anime-list.json").read_bytes()
            with patch.object(sync, "fetch_snapshot", side_effect=sync.SyncError("API unavailable")):
                self.assertEqual(sync.main(["--output", str(output)]), 1)
            self.assertEqual((output / "anime-list.json").read_bytes(), original)

    def test_unrelated_output_file_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "public"
            sync.write_exports(output, self.snapshot())
            (output / "secret.txt").write_text("do not publish")
            with self.assertRaisesRegex(sync.SyncError, "unrelated files"):
                sync.write_exports(output, self.snapshot())


class ClientTests(unittest.TestCase):
    def test_rate_limit_retry_after(self):
        calls = []
        waits = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return b'{"data":{"ok":true}}'

        def opener(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise urllib.error.HTTPError(sync.API_URL, 429, "Too Many Requests", {"Retry-After": "3"}, io.BytesIO(b""))
            return Response()

        client = sync.AniListClient(opener=opener, sleeper=waits.append, clock=lambda: 0.0, min_interval=0)
        self.assertEqual(client.query("query { ok }", {})["ok"], True)
        self.assertEqual(waits, [3.0])
        self.assertEqual(calls[0].get_method(), "POST")

    def test_api_failure_does_not_return_partial_data(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(sync.API_URL, 403, "Forbidden", {}, io.BytesIO(b""))

        with self.assertRaisesRegex(sync.SyncError, "HTTP 403"):
            sync.AniListClient(opener=opener, min_interval=0).query("query { ok }", {})

    def test_graphql_error_does_not_return_partial_data(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return b'{"data":{"Page":{}},"errors":[{"message":"Invalid query"}]}'

        with self.assertRaisesRegex(sync.SyncError, "GraphQL errors"):
            sync.AniListClient(opener=lambda request, timeout: Response(), min_interval=0).query("query { Page }", {})


if __name__ == "__main__":
    unittest.main()
