import contextlib
import datetime
import io
import json
import tempfile
import unittest
from zoneinfo import ZoneInfo
from unittest.mock import patch

import bot


class RetryCallTests(unittest.TestCase):
    def test_retry_call_retries_until_success(self):
        attempts = []
        sleeps = []

        def flaky_action():
            attempts.append("called")
            if len(attempts) < 3:
                raise RuntimeError("temporary failure")
            return "ok"

        with contextlib.redirect_stdout(io.StringIO()):
            result = bot.retry_call(
                flaky_action,
                "flaky action",
                retries=3,
                delay=1,
                sleep=sleeps.append,
            )

        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleeps, [1, 2])

    def test_retry_call_raises_last_error_after_retries(self):
        attempts = []
        sleeps = []

        def failing_action():
            attempts.append("called")
            raise RuntimeError(f"failure {len(attempts)}")

        with self.assertRaisesRegex(RuntimeError, "failure 3"):
            with contextlib.redirect_stdout(io.StringIO()):
                bot.retry_call(
                    failing_action,
                    "failing action",
                    retries=3,
                    delay=1,
                    sleep=sleeps.append,
                )

        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleeps, [1, 2])


class BotRetryIntegrationTests(unittest.TestCase):
    def test_get_tweet_content_wraps_gemini_generation_in_retry(self):
        retry_calls = []

        class FakeClient:
            def __init__(self, *, api_key):
                self.models = object()

        def fake_retry(action, name, **kwargs):
            retry_calls.append((name, kwargs))
            return type("Response", (), {"text": "steady as she goes"})()

        with patch.dict(bot.os.environ, {"GEMINI_API_KEY": "gemini-key"}), \
                patch.object(bot.genai, "Client", FakeClient), \
                patch.object(bot, "retry_call", fake_retry):
            with contextlib.redirect_stdout(io.StringIO()):
                tweet = bot.get_tweet_content()

        self.assertEqual(tweet, "steady as she goes")
        self.assertEqual(retry_calls[0][0], "Gemini generation")

    def test_post_to_x_wraps_tweet_creation_in_retry_without_media(self):
        retry_calls = []

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def create_tweet(self, *, text):
                return type("Tweet", (), {"data": {"id": "tweet-123"}})()

        def fake_retry(action, name, **kwargs):
            retry_calls.append((name, kwargs))
            return action()

        env = {
            "X_API_KEY": "api-key",
            "X_API_SECRET": "api-secret",
            "X_ACCESS_TOKEN": "access-token",
            "X_ACCESS_TOKEN_SECRET": "access-token-secret",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            sent_path = f"{temp_dir}/sent.json"

            with patch.object(bot, "SENT_FILE", sent_path), \
                    patch.object(bot, "get_slot", return_value="morning"), \
                    patch.object(bot, "get_today", return_value="2026-06-10"), \
                    patch.object(
                        bot,
                        "now",
                        return_value=datetime.datetime(2026, 6, 10, 8, 17, tzinfo=ZoneInfo("Europe/London")),
                    ), \
                    patch.dict(bot.os.environ, env), \
                    patch.object(bot, "get_tweet_content", return_value="test tweet"), \
                    patch.object(bot.tweepy, "Client", FakeClient), \
                    patch.object(bot, "retry_call", fake_retry):
                with contextlib.redirect_stdout(io.StringIO()):
                    bot.post_to_x()

        self.assertEqual([call[0] for call in retry_calls], ["Tweet creation"])
        self.assertEqual(retry_calls[0][1]["retries"], 2)


class ScheduleSlotTests(unittest.TestCase):
    def test_get_slot_returns_morning_only_during_morning_window(self):
        with patch.object(
            bot,
            "now",
            return_value=datetime.datetime(2026, 6, 10, 8, 17, tzinfo=ZoneInfo("Europe/London")),
        ):
            self.assertEqual(bot.get_slot(), "morning")

    def test_get_slot_returns_evening_only_during_evening_window(self):
        with patch.object(
            bot,
            "now",
            return_value=datetime.datetime(2026, 6, 10, 20, 17, tzinfo=ZoneInfo("Europe/London")),
        ):
            self.assertEqual(bot.get_slot(), "evening")

    def test_get_slot_returns_none_outside_posting_windows(self):
        with patch.object(
            bot,
            "now",
            return_value=datetime.datetime(2026, 6, 10, 14, 17, tzinfo=ZoneInfo("Europe/London")),
        ):
            self.assertIsNone(bot.get_slot())


class SentStateTests(unittest.TestCase):
    def test_load_sent_returns_empty_dict_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sent_path = f"{temp_dir}/sent.json"

            with patch.object(bot, "SENT_FILE", sent_path):
                self.assertEqual(bot.load_sent(), {})

    def test_save_sent_writes_pretty_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sent_path = f"{temp_dir}/sent.json"
            sent = {
                "2026-06-10": {
                    "morning": {
                        "tweetId": "123",
                        "text": "hello",
                        "createdAt": "2026-06-10T08:17:00+01:00",
                    }
                }
            }

            with patch.object(bot, "SENT_FILE", sent_path):
                bot.save_sent(sent)

            with open(sent_path, encoding="utf-8") as file:
                self.assertEqual(json.load(file), sent)


class PostLogTests(unittest.TestCase):
    def test_append_post_log_creates_log_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = f"{temp_dir}/post_log.json"
            entry = {
                "createdAt": "2026-06-10T08:17:00+01:00",
                "status": "failed",
                "stage": "Tweet creation",
                "error": "rate limited",
                "slot": "morning",
                "date": "2026-06-10",
            }

            with patch.object(bot, "POST_LOG_FILE", log_path):
                bot.append_post_log(entry)

            with open(log_path, encoding="utf-8") as file:
                self.assertEqual(json.load(file), [entry])

    def test_post_to_x_records_failed_tweet_creation(self):
        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def create_tweet(self, *, text):
                raise RuntimeError("x api unavailable")

        def fake_retry(action, name, **kwargs):
            return action()

        env = {
            "X_API_KEY": "api-key",
            "X_API_SECRET": "api-secret",
            "X_ACCESS_TOKEN": "access-token",
            "X_ACCESS_TOKEN_SECRET": "access-token-secret",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            sent_path = f"{temp_dir}/sent.json"
            log_path = f"{temp_dir}/post_log.json"

            with patch.object(bot, "SENT_FILE", sent_path), \
                    patch.object(bot, "POST_LOG_FILE", log_path), \
                    patch.object(bot, "get_slot", return_value="morning"), \
                    patch.object(bot, "get_today", return_value="2026-06-10"), \
                    patch.object(
                        bot,
                        "now",
                        return_value=datetime.datetime(2026, 6, 10, 8, 17, tzinfo=ZoneInfo("Europe/London")),
                    ), \
                    patch.dict(bot.os.environ, env), \
                    patch.object(bot, "get_tweet_content", return_value="test tweet"), \
                    patch.object(bot.tweepy, "Client", FakeClient), \
                    patch.object(bot, "retry_call", fake_retry):
                with self.assertRaisesRegex(RuntimeError, "x api unavailable"):
                    with contextlib.redirect_stdout(io.StringIO()):
                        bot.post_to_x()

            with open(log_path, encoding="utf-8") as file:
                logs = json.load(file)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["status"], "failed")
        self.assertEqual(logs[0]["stage"], "Tweet creation")
        self.assertEqual(logs[0]["error"], "x api unavailable")
        self.assertEqual(logs[0]["slot"], "morning")
        self.assertEqual(logs[0]["date"], "2026-06-10")
        self.assertEqual(logs[0]["text"], "test tweet")


class ScheduledPostTests(unittest.TestCase):
    def test_post_to_x_skips_outside_posting_window(self):
        with patch.object(bot, "get_slot", return_value=None), \
                patch.object(bot, "get_tweet_content") as get_tweet_content:
            with contextlib.redirect_stdout(io.StringIO()):
                bot.post_to_x()

        get_tweet_content.assert_not_called()

    def test_post_to_x_force_post_bypasses_time_window(self):
        retry_calls = []

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def create_tweet(self, *, text):
                return type("Tweet", (), {"data": {"id": "tweet-123"}})()

        def fake_retry(action, name, **kwargs):
            retry_calls.append((name, kwargs))
            return action()

        env = {
            "FORCE_POST": "true",
            "X_API_KEY": "api-key",
            "X_API_SECRET": "api-secret",
            "X_ACCESS_TOKEN": "access-token",
            "X_ACCESS_TOKEN_SECRET": "access-token-secret",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            sent_path = f"{temp_dir}/sent.json"

            with patch.object(bot, "SENT_FILE", sent_path), \
                    patch.object(bot, "get_slot", return_value=None), \
                    patch.object(bot, "get_today", return_value="2026-06-10"), \
                    patch.object(
                        bot,
                        "now",
                        return_value=datetime.datetime(2026, 6, 10, 14, 17, tzinfo=ZoneInfo("Europe/London")),
                    ), \
                    patch.dict(bot.os.environ, env, clear=False), \
                    patch.object(bot, "get_tweet_content", return_value="manual test tweet"), \
                    patch.object(bot.tweepy, "Client", FakeClient), \
                    patch.object(bot, "retry_call", fake_retry):
                with contextlib.redirect_stdout(io.StringIO()):
                    bot.post_to_x()

            with open(sent_path, encoding="utf-8") as file:
                sent = json.load(file)

        self.assertEqual([call[0] for call in retry_calls], ["Tweet creation"])
        self.assertEqual(sent["2026-06-10"]["manual"]["tweetId"], "tweet-123")
        self.assertEqual(sent["2026-06-10"]["manual"]["text"], "manual test tweet")

    def test_post_to_x_skips_when_slot_was_already_sent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sent_path = f"{temp_dir}/sent.json"
            with open(sent_path, "w", encoding="utf-8") as file:
                json.dump({"2026-06-10": {"morning": {"tweetId": "old", "text": "old"}}}, file)

            with patch.object(bot, "SENT_FILE", sent_path), \
                    patch.object(bot, "get_slot", return_value="morning"), \
                    patch.object(bot, "get_today", return_value="2026-06-10"), \
                    patch.object(bot, "get_tweet_content") as get_tweet_content:
                with contextlib.redirect_stdout(io.StringIO()):
                    bot.post_to_x()

        get_tweet_content.assert_not_called()

    def test_post_to_x_force_post_bypasses_existing_slot_record(self):
        retry_calls = []

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def create_tweet(self, *, text):
                return type("Tweet", (), {"data": {"id": "tweet-456"}})()

        def fake_retry(action, name, **kwargs):
            retry_calls.append((name, kwargs))
            return action()

        env = {
            "FORCE_POST": "true",
            "X_API_KEY": "api-key",
            "X_API_SECRET": "api-secret",
            "X_ACCESS_TOKEN": "access-token",
            "X_ACCESS_TOKEN_SECRET": "access-token-secret",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            sent_path = f"{temp_dir}/sent.json"
            with open(sent_path, "w", encoding="utf-8") as file:
                json.dump({"2026-06-10": {"morning": {"tweetId": "old", "text": "old"}}}, file)

            with patch.object(bot, "SENT_FILE", sent_path), \
                    patch.object(bot, "get_slot", return_value="morning"), \
                    patch.object(bot, "get_today", return_value="2026-06-10"), \
                    patch.object(
                        bot,
                        "now",
                        return_value=datetime.datetime(2026, 6, 10, 8, 17, tzinfo=ZoneInfo("Europe/London")),
                    ), \
                    patch.dict(bot.os.environ, env, clear=False), \
                    patch.object(bot, "get_tweet_content", return_value="forced tweet"), \
                    patch.object(bot.tweepy, "Client", FakeClient), \
                    patch.object(bot, "retry_call", fake_retry):
                with contextlib.redirect_stdout(io.StringIO()):
                    bot.post_to_x()

            with open(sent_path, encoding="utf-8") as file:
                sent = json.load(file)

        self.assertEqual([call[0] for call in retry_calls], ["Tweet creation"])
        self.assertEqual(sent["2026-06-10"]["morning"]["tweetId"], "tweet-456")
        self.assertEqual(sent["2026-06-10"]["morning"]["text"], "forced tweet")

    def test_post_to_x_records_successful_slot(self):
        retry_calls = []

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.tweet_call = None

            def create_tweet(self, *, text):
                self.tweet_call = {"text": text}
                return type("Tweet", (), {"data": {"id": "tweet-123"}})()

        def fake_retry(action, name, **kwargs):
            retry_calls.append((name, kwargs))
            return action()

        env = {
            "X_API_KEY": "api-key",
            "X_API_SECRET": "api-secret",
            "X_ACCESS_TOKEN": "access-token",
            "X_ACCESS_TOKEN_SECRET": "access-token-secret",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            sent_path = f"{temp_dir}/sent.json"

            with patch.object(bot, "SENT_FILE", sent_path), \
                    patch.object(bot, "get_slot", return_value="morning"), \
                    patch.object(bot, "get_today", return_value="2026-06-10"), \
                    patch.object(
                        bot,
                        "now",
                        return_value=datetime.datetime(2026, 6, 10, 8, 17, tzinfo=ZoneInfo("Europe/London")),
                    ), \
                    patch.dict(bot.os.environ, env), \
                    patch.object(bot, "get_tweet_content", return_value="test tweet"), \
                    patch.object(bot.tweepy, "Client", FakeClient), \
                    patch.object(bot, "retry_call", fake_retry):
                with contextlib.redirect_stdout(io.StringIO()):
                    bot.post_to_x()

            with open(sent_path, encoding="utf-8") as file:
                sent = json.load(file)

        self.assertEqual(sent["2026-06-10"]["morning"]["tweetId"], "tweet-123")
        self.assertEqual(sent["2026-06-10"]["morning"]["text"], "test tweet")
        self.assertEqual(sent["2026-06-10"]["morning"]["createdAt"], "2026-06-10T08:17:00+01:00")


if __name__ == "__main__":
    unittest.main()
