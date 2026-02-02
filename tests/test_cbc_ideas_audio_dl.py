import importlib.util
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from contextlib import ExitStack
import sys

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "cbc_ideas_audio_dl.py"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

spec = importlib.util.spec_from_file_location("cbc_ideas_audio_dl", SCRIPT_PATH)
cbc = importlib.util.module_from_spec(spec)
sys.modules["cbc_ideas_audio_dl"] = cbc
spec.loader.exec_module(cbc)


class TestCbcIdeasDl(unittest.TestCase):
    def test_extract_initial_state(self):
        html = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        state = cbc.extract_initial_state(html)
        self.assertIn("detail", state)

    def test_find_audio_block(self):
        html = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        state = cbc.extract_initial_state(html)
        audio = cbc.find_audio_block(state)
        self.assertEqual(audio.get("type"), "audio")
        self.assertIn("Injustice", audio.get("title"))

    def test_collect_feed_items_and_best_match(self):
        html = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        state = cbc.extract_initial_state(html)
        audio = cbc.find_audio_block(state)
        target_ts = cbc.extract_target_timestamp_ms(audio, state)
        items = cbc.collect_feed_items(feed, audio.get("title"), audio.get("description"), target_ts)
        best = cbc.best_rss_match(items)
        self.assertEqual(best.enclosure_url, "https://example.com/pt1.mp3")

    def test_json_list_output(self):
        html = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        state = cbc.extract_initial_state(html)
        audio = cbc.find_audio_block(state)
        target_ts = cbc.extract_target_timestamp_ms(audio, state)
        items = cbc.collect_feed_items(feed, audio.get("title"), audio.get("description"), target_ts)
        payload = json.dumps([item.__dict__ for item in items])
        self.assertTrue(payload.startswith("["))

    def test_is_story_url_variants(self):
        self.assertTrue(cbc.is_story_url("https://www.cbc.ca/radio/ideas/example-story-1.2345"))
        self.assertTrue(cbc.is_story_url("https://www.cbc.ca/radio/ideas/example-story-9.7052937"))
        self.assertTrue(cbc.is_story_url("https://www.cbc.ca/radio/ideas/example-story-9.7052937?cmp=rss"))
        self.assertFalse(cbc.is_story_url("https://www.cbc.ca/radio/ideas/"))

    def test_requirements_web_includes_multipart(self):
        req_path = Path(__file__).resolve().parents[1] / "requirements-web.txt"
        reqs = req_path.read_text(encoding="utf-8")
        self.assertIn("python-multipart", reqs)

    def test_python_version_check(self):
        class DummyVer:
            major = 3
            minor = 10
            micro = 9

            def __lt__(self, other):
                return (self.major, self.minor) < other

        with mock.patch.object(cbc.sys, "version_info", DummyVer()):
            self.assertFalse(cbc.ensure_python_version())

    def test_web_grouping_contains_basic(self):
        import sys
        import types

        class DummyApp:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                def decorator(fn):
                    return fn
                return decorator

            def post(self, *args, **kwargs):
                def decorator(fn):
                    return fn
                return decorator

        fastapi = types.SimpleNamespace(FastAPI=DummyApp, Request=object)
        responses = types.SimpleNamespace(JSONResponse=object, RedirectResponse=object)
        templating = types.SimpleNamespace(Jinja2Templates=lambda **kwargs: object())
        sys.modules["fastapi"] = fastapi
        sys.modules["fastapi.responses"] = responses
        sys.modules["fastapi.templating"] = templating
        spec = importlib.util.spec_from_file_location(
            "cbc_radio_web",
            Path(__file__).resolve().parents[1] / "cbc_radio_web.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["cbc_radio_web"] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)
        fields = module._parser_fields()
        grouped = module._group_fields(fields)
        self.assertIn("basic", grouped)
        self.assertTrue(grouped["basic"])
        for key in ("fastapi", "fastapi.responses", "fastapi.templating", "cbc_radio_web"):
            sys.modules.pop(key, None)

    def test_web_validate_section_requires_list(self):
        import sys
        import types

        class DummyApp:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                def decorator(fn):
                    return fn
                return decorator

            def post(self, *args, **kwargs):
                def decorator(fn):
                    return fn
                return decorator

        fastapi = types.SimpleNamespace(FastAPI=DummyApp, Request=object)
        responses = types.SimpleNamespace(JSONResponse=object, RedirectResponse=object)
        templating = types.SimpleNamespace(Jinja2Templates=lambda **kwargs: object())
        sys.modules["fastapi"] = fastapi
        sys.modules["fastapi.responses"] = responses
        sys.modules["fastapi.templating"] = templating
        spec = importlib.util.spec_from_file_location(
            "cbc_radio_web",
            Path(__file__).resolve().parents[1] / "cbc_radio_web.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["cbc_radio_web"] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)

        error = module._validate_request("https://www.cbc.ca/radio/", {})
        self.assertIn("Section URLs", error)
        error = module._validate_request(
            "https://www.cbc.ca/radio/",
            {"story_list": "5"},
        )
        self.assertIsNone(error)
        error = module._validate_request(
            "https://www.cbc.ca/radio/",
            {"browse_stories": "1"},
        )
        self.assertIn("Browse stories", error)
        error = module._validate_request(
            "https://www.cbc.ca/radio/ideas/some-story-1.12345",
            {},
        )
        self.assertIsNone(error)

        for key in ("fastapi", "fastapi.responses", "fastapi.templating", "cbc_radio_web"):
            sys.modules.pop(key, None)


class TestCliFlags(unittest.TestCase):
    def run_main(self, argv, fetch_map, input_values=None, force_story=False):
        out = []
        err = []
        input_values = input_values or []

        def fake_fetch(url, cache=None, ignore_cache=False):
            return fetch_map[url]

        def fake_print(*args, **kwargs):
            target = err if kwargs.get("file") else out
            target.append(" ".join(str(a) for a in args))

        patches = [
            mock.patch.object(cbc, "fetch_text", side_effect=fake_fetch),
            mock.patch.object(cbc, "ensure_yt_dlp", return_value=True),
            mock.patch.object(cbc, "print", side_effect=fake_print),
            mock.patch.object(cbc, "input", side_effect=input_values),
            mock.patch.object(cbc.sys, "argv", argv),
        ]
        if force_story:
            patches.append(mock.patch.object(cbc, "is_story_url", return_value=True))
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            rc = cbc.main()
        return rc, "\n".join(out), "\n".join(err)

    def test_dry_run_and_print_url(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--dry-run"],
            {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("https://example.com/pt1.mp3", out)

        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--print-url", "--json"],
            {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("\"enclosure_url\"", out)

    def test_list_and_summary(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--list", "1", "--json"],
            {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("PT 1", out)

        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--summary", "1", "--json"],
            {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("PT 1", out)

    def test_rss_discover_only(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        story = story.replace("</script>", "https://www.cbc.ca/podcasting/includes/ideas.xml</script>")
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--rss-discover-only"],
            {"https://example.com/story-1.123": story},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("ideas.xml", out)

    def test_no_download(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--no-download"],
            {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("Resolved URL", out)

    def test_completion(self):
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story", "--completion", "bash"],
            {"https://example.com/story": (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")},
        )
        self.assertEqual(rc, 0)
        self.assertIn("complete -F", out)

    def test_interactive_section_feed(self):
        section_html = "<a href=\"/radio/thecurrent/\">The Current</a>"
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        fetch_map = {
            "https://example.com/section": section_html,
            "https://www.cbc.ca/podcasting/": "",
            "https://www.cbc.ca/radio/thecurrent/": "",
            "https://www.cbc.ca/podcasting/includes/thecurrent.xml": feed,
        }
        with mock.patch.object(cbc, "resolve_feed_for_slug", return_value=("https://www.cbc.ca/podcasting/includes/thecurrent.xml", feed)):
            rc, out, _err = self.run_main(
                ["cbc_ideas_audio_dl.py", "https://example.com/section", "--interactive", "--dry-run"],
                fetch_map,
                input_values=["1", "2"],
            )
        self.assertEqual(rc, 0)
        self.assertIn("https://example.com/pt1.mp3", out)

    def test_transcribe_flags(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        fetch_map = {
            "https://example.com/story": story,
            "https://www.cbc.ca/podcasting/includes/ideas.xml": feed,
        }
        with mock.patch.object(cbc, "transcribe_audio", return_value=True) as tr, \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"), \
             mock.patch.object(cbc, "run_ytdlp", return_value=0):
            rc, _out, _err = self.run_main(
                ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--transcribe", "--transcribe-dir", "/tmp/t", "--transcribe-model", "small"],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
        self.assertEqual(rc, 0)
        tr.assert_called_with("/tmp/fake.mp3", "/tmp/t", "small", None, None, None)

    def test_show_override_uses_slug(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--show", "customshow", "--dry-run"],
            {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/customshow.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("https://example.com/pt1.mp3", out)

    def test_provider_override_uses_slug(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--provider", "thecurrent", "--dry-run"],
            {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/thecurrent.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("https://example.com/pt1.mp3", out)

    def test_rss_url_override(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        rc, out, _err = self.run_main(
            [
                "cbc_ideas_audio_dl.py",
                "https://example.com/story-1.123",
                "--rss-url",
                "https://example.com/custom.xml",
                "--dry-run",
            ],
            {"https://example.com/story-1.123": story, "https://example.com/custom.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("https://example.com/pt1.mp3", out)

    def test_title_override_affects_match(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        rc, out, _err = self.run_main(
            [
                "cbc_ideas_audio_dl.py",
                "https://example.com/story-1.123",
                "--title",
                "PT 2 | An injustice system where 'you can buy your way out'",
                "--print-url",
            ],
            {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("https://example.com/pt2.mp3", out)

    def test_non_interactive_requires_list_or_summary(self):
        section_html = "https://www.cbc.ca/podcasting/includes/ideas.xml"
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        rc, _out, err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/section", "--non-interactive"],
            {"https://example.com/section": section_html, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
        )
        self.assertEqual(rc, 2)
        self.assertIn("non-interactive", err.lower())

    def test_output_flags_build_cmd(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        captured = {}

        def fake_run(cmd, use_live=True):
            captured["cmd"] = cmd
            return 0

        with mock.patch.object(cbc, "run_ytdlp", side_effect=fake_run), \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"):
            rc, _out, _err = self.run_main(
                [
                    "cbc_ideas_audio_dl.py",
                    "https://example.com/story-1.123",
                    "--audio-format",
                    "flac",
                    "--format",
                    "bestaudio",
                    "--output",
                    "%(title)s.%(ext)s",
                    "--output-dir",
                    "/tmp/out",
                ],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
        self.assertEqual(rc, 0)
        cmd = captured.get("cmd", [])
        self.assertIn("--audio-format", cmd)
        self.assertIn("flac", cmd)
        self.assertIn("-f", cmd)
        self.assertIn("bestaudio", cmd)
        self.assertIn("-o", cmd)
        self.assertIn("%(title)s.%(ext)s", cmd)
        self.assertIn("-P", cmd)
        self.assertIn("/tmp/out", cmd)
        self.assertTrue(cmd[-1].endswith(".mp3"))

    def test_tag_and_no_tag_flags(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        with mock.patch.object(cbc, "run_ytdlp", return_value=0), \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"), \
             mock.patch.object(cbc, "tag_audio_file") as tag:
            rc, _out, _err = self.run_main(
                ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--tag"],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
            self.assertEqual(rc, 0)
            tag.assert_called_once()

        with mock.patch.object(cbc, "run_ytdlp", return_value=0), \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"), \
             mock.patch.object(cbc, "tag_audio_file") as tag:
            rc, _out, _err = self.run_main(
                ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--tag", "--no-tag"],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
            self.assertEqual(rc, 0)
            tag.assert_not_called()

    def test_cache_ttl_sets_cache(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        captured = {}

        class FakeCache:
            def __init__(self, base_dir, ttl_seconds=0):
                captured["ttl"] = ttl_seconds

        with mock.patch.object(cbc, "Cache", FakeCache):
            rc, _out, _err = self.run_main(
                ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--cache-ttl", "123", "--dry-run"],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(captured.get("ttl"), 123)

    def test_verbose_outputs_details(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--verbose", "--dry-run"],
            {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
            force_story=True,
        )
        self.assertEqual(rc, 0)
        self.assertIn("Resolved title:", out)
        self.assertIn("Resolved show slug:", out)

    def test_debug_dir_writes_files(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmpdir:
            rc, _out, _err = self.run_main(
                ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--debug-dir", tmpdir, "--dry-run"],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
            self.assertEqual(rc, 0)
            self.assertTrue((Path(tmpdir) / "story.html").exists())
            self.assertTrue((Path(tmpdir) / "feed.xml").exists())
            self.assertTrue((Path(tmpdir) / "scores.json").exists())

    def test_record_writes_fixtures(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.object(cbc, "run_ytdlp", return_value=0), \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"):
            rc, _out, _err = self.run_main(
                ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--record", tmpdir],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
            self.assertEqual(rc, 0)
            self.assertTrue((Path(tmpdir) / "story.html").exists())
            self.assertTrue((Path(tmpdir) / "feed.xml").exists())

    def test_repair_retries_download(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        with mock.patch.object(cbc, "run_ytdlp", side_effect=[1, 0]) as runner, \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"):
            rc, _out, _err = self.run_main(
                ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--repair"],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(runner.call_count, 2)

    def test_browse_stories_interactive(self):
        section_html = (
            '<a href="/radio/ideas/story-one-1.111">Story One</a>'
            '<a href="/radio/ideas/story-two-1.222">Story Two</a>'
        )
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        fetch_map = {
            "https://example.com/section": section_html,
            "https://www.cbc.ca/podcasting/": "",
            "https://www.cbc.ca/radio/ideas/story-one-1.111": story,
            "https://www.cbc.ca/podcasting/includes/ideas.xml": feed,
        }
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/section", "--browse-stories", "--interactive", "--dry-run"],
            fetch_map,
            input_values=["1"],
        )
        self.assertEqual(rc, 0)
        self.assertIn("https://example.com/pt1.mp3", out)

    def test_story_list(self):
        section_html = (
            '<a href="/radio/ideas/story-one-1.111">Story One</a>'
            '<a href="/radio/ideas/story-two-1.222">Story Two</a>'
        )
        fetch_map = {"https://example.com/section": section_html, "https://www.cbc.ca/podcasting/": ""}
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/section", "--story-list", "2", "--json"],
            fetch_map,
        )
        self.assertEqual(rc, 0)
        self.assertIn("story-one-1.111", out)
        self.assertIn("story-two-1.222", out)

    def test_show_list(self):
        section_html = '<a href="/radio/ideas/">Ideas</a>'
        fetch_map = {"https://example.com/section": section_html, "https://www.cbc.ca/podcasting/": ""}
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/section", "--show-list", "1", "--json"],
            fetch_map,
        )
        self.assertEqual(rc, 0)
        self.assertIn("ideas", out)

    def test_parse_timestamp_variants(self):
        self.assertAlmostEqual(cbc.parse_timestamp("30"), 30.0)
        self.assertAlmostEqual(cbc.parse_timestamp("01:30"), 90.0)
        self.assertAlmostEqual(cbc.parse_timestamp("1:02:03"), 3723.0)
        with self.assertRaises(ValueError):
            cbc.parse_timestamp("")
        with self.assertRaises(ValueError):
            cbc.parse_timestamp("bad")
        with self.assertRaises(ValueError):
            cbc.parse_timestamp("1:2:3:4")

    def test_transcribe_clip_requires_ffmpeg(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        with mock.patch.object(cbc, "run_ytdlp", return_value=0), \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"), \
             mock.patch.object(cbc, "transcribe_audio", return_value=True), \
             mock.patch.object(cbc.shutil, "which", side_effect=lambda name: None if name == "ffmpeg" else "/usr/bin/whisper"):
            rc, _out, err = self.run_main(
                [
                    "cbc_ideas_audio_dl.py",
                    "https://example.com/story-1.123",
                    "--transcribe",
                    "--transcribe-duration",
                    "30",
                ],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
        self.assertEqual(rc, 2)
        self.assertIn("ffmpeg", err.lower())

    def test_transcribe_clip_passes_times(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        with mock.patch.object(cbc, "run_ytdlp", return_value=0), \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"), \
             mock.patch.object(cbc.shutil, "which", return_value="/usr/bin/ffmpeg"), \
             mock.patch.object(cbc, "transcribe_audio", return_value=True) as tr:
            rc, _out, _err = self.run_main(
                [
                    "cbc_ideas_audio_dl.py",
                    "https://example.com/story-1.123",
                    "--transcribe",
                    "--transcribe-start",
                    "25:31",
                    "--transcribe-end",
                    "35:00",
                ],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
        self.assertEqual(rc, 0)
        _filepath, _outdir, _model, clip_start, clip_end, clip_duration = tr.call_args.args
        self.assertAlmostEqual(clip_start, 25 * 60 + 31)
        self.assertAlmostEqual(clip_end, 35 * 60)
        self.assertIsNone(clip_duration)

    def test_transcribe_end_and_duration_conflict(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        with mock.patch.object(cbc, "run_ytdlp", return_value=0), \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"), \
             mock.patch.object(cbc, "transcribe_audio", return_value=True):
            rc, _out, err = self.run_main(
                [
                    "cbc_ideas_audio_dl.py",
                    "https://example.com/story-1.123",
                    "--transcribe",
                    "--transcribe-start",
                    "10",
                    "--transcribe-end",
                    "20",
                    "--transcribe-duration",
                    "5",
                ],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
        self.assertEqual(rc, 2)
        self.assertIn("end", err.lower())

    def test_transcribe_end_before_start(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        with mock.patch.object(cbc, "run_ytdlp", return_value=0), \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"), \
             mock.patch.object(cbc, "transcribe_audio", return_value=True):
            rc, _out, err = self.run_main(
                [
                    "cbc_ideas_audio_dl.py",
                    "https://example.com/story-1.123",
                    "--transcribe",
                    "--transcribe-start",
                    "10",
                    "--transcribe-end",
                    "5",
                ],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
        self.assertEqual(rc, 2)
        self.assertIn("after", err.lower())

    def test_web_missing_deps_error_hint(self):
        with mock.patch("importlib.import_module", side_effect=ImportError()):
            rc, _out, err = self.run_main(
                ["cbc_ideas_audio_dl.py", "--web"],
                {"https://example.com/story-1.123": (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")},
            )
        self.assertEqual(rc, 2)
        self.assertIn("requirements-web.txt", err)
        self.assertIn("venv", err.lower())

    def test_web_missing_module_error(self):
        def fake_import(name):
            return object()

        with mock.patch("importlib.import_module", side_effect=fake_import), \
             mock.patch.object(cbc.Path, "exists", return_value=False):
            rc, _out, err = self.run_main(
                ["cbc_ideas_audio_dl.py", "--web"],
                {"https://example.com/story-1.123": (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")},
            )
        self.assertEqual(rc, 2)
        self.assertIn("web ui module not found", err.lower())

    def test_transcribe_failure_is_error(self):
        story = (FIXTURE_DIR / "story.html").read_text(encoding="utf-8")
        feed = (FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
        with mock.patch.object(cbc, "run_ytdlp", return_value=0), \
             mock.patch.object(cbc, "get_expected_filepath", return_value="/tmp/fake.mp3"), \
             mock.patch.object(cbc, "transcribe_audio", return_value=False):
            rc, _out, err = self.run_main(
                ["cbc_ideas_audio_dl.py", "https://example.com/story-1.123", "--transcribe"],
                {"https://example.com/story-1.123": story, "https://www.cbc.ca/podcasting/includes/ideas.xml": feed},
                force_story=True,
            )
        self.assertEqual(rc, 2)
        self.assertIn("transcription failed", err.lower())

    def test_story_list_handles_single_quotes(self):
        section_html = "<a href='/radio/ideas/story-one-1.111'>Story One</a>"
        fetch_map = {"https://example.com/section": section_html, "https://www.cbc.ca/podcasting/": ""}
        rc, out, _err = self.run_main(
            ["cbc_ideas_audio_dl.py", "https://example.com/section", "--story-list", "1", "--json"],
            fetch_map,
        )
        self.assertEqual(rc, 0)
        self.assertIn("story-one-1.111", out)


if __name__ == "__main__":
    unittest.main()
