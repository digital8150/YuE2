"""SQLite repository contract tests using an isolated temporary database."""

from __future__ import annotations

import tempfile
import unittest
import sqlite3
from pathlib import Path

from yue2_app.repository import Repository


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        # SQLite connections in the current repository are short-lived but
        # deliberately not exposed as a public handle.  Ignore Windows' brief
        # file-lock race while the interpreter releases the last connection.
        self._tempdir = tempfile.TemporaryDirectory(prefix="yue2-repository-", ignore_cleanup_errors=True)
        self.repo = Repository(Path(self._tempdir.name) / "library.sqlite3")

    def tearDown(self) -> None:
        self.repo.close()
        self._tempdir.cleanup()

    def _create(
        self,
        job_id: str,
        *,
        mode: str = "original",
        title: str | None = "Test song",
        style: str = "ambient",
        lyrics: str = "test lyrics",
        seed: int = 1,
        settings: dict | None = None,
        status: str = "completed",
        created_at: str = "2026-01-01T00:00:00+00:00",
        updated_at: str | None = None,
    ):
        return self.repo.create_job(
            job_id=job_id,
            prompt_id=f"prompt-{job_id}",
            mode=mode,
            title=title,
            style=style,
            lyrics=lyrics,
            seed=seed,
            settings=settings or {},
            status=status,
            created_at=created_at,
            updated_at=updated_at or created_at,
        )

    def test_create_get_and_update_round_trip_with_defaults(self) -> None:
        job = self.repo.create_job(
            job_id="crud-1",
            prompt_id=None,
            mode="original",
            title=None,
            style="piano",
            lyrics="",
            seed=42,
            settings={"top_p": 0.8},
        )
        self.assertEqual(job.id, "crud-1")
        self.assertEqual(job.status, "queued")
        self.assertIsNone(job.source_filename)
        self.assertEqual(job.settings, {"top_p": 0.8})

        fetched = self.repo.get_job("crud-1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, job.id)
        self.assertEqual(fetched.prompt_id, job.prompt_id)
        self.assertEqual(fetched.lyrics, "")
        self.assertIsNone(self.repo.get_job("does-not-exist"))

        self.repo.set_prompt_id("crud-1", "prompt-42")
        self.repo.set_status("crud-1", "running")
        self.repo.set_output("crud-1", filename="song.mp3", subfolder="yue2", output_type="output")
        updated = self.repo.get_job("crud-1")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.prompt_id, "prompt-42")
        self.assertEqual(updated.status, "completed")
        self.assertEqual(updated.output_filename, "song.mp3")
        self.assertEqual(updated.output_subfolder, "yue2")
        self.assertEqual(updated.output_type, "output")
        self.assertIsNone(updated.error)
        self.assertGreaterEqual(updated.updated_at, updated.created_at)

    def test_library_query_is_case_insensitive_and_filters_mode(self) -> None:
        self._create(
            "old-original",
            mode="original",
            title="Morning Sketch",
            style="Ambient Piano",
            lyrics="Blue horizon",
            created_at="2026-01-01T01:00:00+00:00",
            updated_at="2026-01-01T01:00:00+00:00",
        )
        self._create(
            "new-original",
            mode="original",
            title="Night Drive",
            style="Synthwave",
            lyrics="AMBIENT lights",
            created_at="2026-01-02T01:00:00+00:00",
            updated_at="2026-01-03T01:00:00+00:00",
        )
        self._create(
            "cover",
            mode="cover",
            title="Cover Take",
            style="Jazz",
            lyrics="reference vocal",
            created_at="2026-01-03T01:00:00+00:00",
            updated_at="2026-01-04T01:00:00+00:00",
        )
        self._create(
            "queued",
            mode="original",
            title="Ambient Pending",
            style="Ambient",
            status="queued",
            created_at="2026-01-05T01:00:00+00:00",
            updated_at="2026-01-05T01:00:00+00:00",
        )

        all_completed = self.repo.list_library()
        self.assertEqual([item.id for item in all_completed], ["cover", "new-original", "old-original"])
        self.assertTrue(all(item.status == "completed" for item in all_completed))

        query_matches = self.repo.list_library(query="aMbIeNt")
        self.assertEqual([item.id for item in query_matches], ["new-original", "old-original"])

        original_matches = self.repo.list_library(query="", mode="original")
        self.assertEqual([item.id for item in original_matches], ["new-original", "old-original"])
        cover_matches = self.repo.list_library(mode="cover")
        self.assertEqual([item.id for item in cover_matches], ["cover"])

    def test_latest_list_has_descending_created_order_and_limit_default(self) -> None:
        for index in range(10):
            self._create(
                f"job-{index:02d}",
                title=f"Song {index}",
                created_at=f"2026-02-{index + 1:02d}T00:00:00+00:00",
            )

        latest = self.repo.list_latest()
        self.assertEqual(len(latest), 8)
        self.assertEqual([item.id for item in latest], [f"job-{i:02d}" for i in range(9, 1, -1)])

        limited = self.repo.list_library(limit=2)
        self.assertEqual(len(limited), 2)
        self.assertEqual([item.id for item in limited], ["job-09", "job-08"])

    def test_existing_library_adds_creator_fields_without_losing_tracks(self) -> None:
        old_db = Path(self._tempdir.name) / "old.sqlite3"
        with sqlite3.connect(old_db) as db:
            db.execute("""CREATE TABLE jobs (
                id TEXT PRIMARY KEY, prompt_id TEXT UNIQUE, mode TEXT, title TEXT,
                style TEXT, lyrics TEXT, created_at TEXT, updated_at TEXT,
                status TEXT, seed INTEGER, settings TEXT, source_filename TEXT,
                output_filename TEXT, output_subfolder TEXT, output_type TEXT, error TEXT)""")
            db.execute("""INSERT INTO jobs VALUES
                ('old-song', NULL, 'original', 'Old song', 'ambient', '',
                 '2026-01-01', '2026-01-01', 'completed', 1, '{}', NULL,
                 'old.mp3', '', 'output', NULL)""")
        migrated = Repository(old_db)
        job = migrated.get_job("old-song")
        self.assertEqual(job.title, "Old song")
        self.assertIsNone(job.creator_name)
        self.assertEqual(job.output_filename, "old.mp3")
        migrated.set_status("old-song", "cancelled")
        self.assertEqual(migrated.get_job("old-song").status, "cancelled")

if __name__ == "__main__":
    unittest.main()
