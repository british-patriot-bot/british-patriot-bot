# British Patriot Bot

A Python bot that uses Gemini to generate short text posts and publishes them to X/Twitter through the X API.

The current version publishes text only. Image upload is intentionally disabled.

## Features

- Generates a short post with Gemini.
- Publishes the generated text to X using Tweepy.
- Posts at most twice per day using UK time:
  - `morning`: 06:00 - 11:59
  - `evening`: 18:00 - 22:59
- Uses `sent.json` to record which daily slots have already posted.
- Runs every 10 minutes through GitHub Actions and posts only when the current UK time is inside a valid slot.
- Retries external API calls before failing.

## Project Structure

```text
.
|-- bot.py                     # Main bot script
|-- test_bot.py                # Unit tests
|-- requirements.txt           # Python dependencies
|-- sent.json                  # Sent-post history
|-- post_log.json              # Failed-post log
`-- .github/workflows/main.yml # GitHub Actions schedule
```

## Environment Variables

For local development, create a `.env` file:

```env
GEMINI_API_KEY=your_gemini_api_key
X_API_KEY=your_x_api_key
X_API_SECRET=your_x_api_secret
X_ACCESS_TOKEN=your_x_access_token
X_ACCESS_TOKEN_SECRET=your_x_access_token_secret
```

For GitHub Actions, add the same values as repository secrets:

```text
GEMINI_API_KEY
X_API_KEY
X_API_SECRET
X_ACCESS_TOKEN
X_ACCESS_TOKEN_SECRET
```

GitHub path:

```text
Repository -> Settings -> Secrets and variables -> Actions
```

## Local Usage

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the bot:

```bash
python3 bot.py
```

The script checks the current UK time before doing any API work.

If the current time is outside the posting windows, it exits with:

```text
Outside posting window, exiting
```

If the current time is inside a valid slot and that slot has not posted yet today, the bot generates and publishes a post.

## Posting Schedule

The bot uses UK time:

```python
TIMEZONE = ZoneInfo("Europe/London")
```

Posting slots:

```text
06:00 - 11:59 -> morning
18:00 - 22:59 -> evening
All other times -> no post
```

After a successful post, `sent.json` is updated:

```json
{
  "2026-06-10": {
    "morning": {
      "tweetId": "xxx",
      "text": "...",
      "createdAt": "2026-06-10T08:17:00+01:00"
    }
  }
}
```

If the same date and slot already exist in `sent.json`, the bot exits without posting again.

## Failure Logs

If tweet creation fails after retries, the bot appends a record to `post_log.json` before raising the error:

```json
[
  {
    "createdAt": "2026-06-10T08:17:00+01:00",
    "status": "failed",
    "stage": "Tweet creation",
    "error": "rate limited",
    "slot": "morning",
    "date": "2026-06-10",
    "text": "..."
  }
]
```

GitHub Actions commits `post_log.json` back to the repository together with `sent.json`.

## GitHub Actions

The workflow in `.github/workflows/main.yml` runs every 10 minutes:

```yaml
schedule:
  - cron: "*/10 * * * *"
```

You can also run the workflow manually from the GitHub Actions page. Manual runs set `FORCE_POST=true`, which bypasses the posting window and the existing `sent.json` slot guard so the bot posts immediately.

Workflow steps:

1. Check out the repository.
2. Install Python dependencies.
3. Run `python3 bot.py`.
4. If `sent.json` changed, commit and push it back to the repository.

Because the workflow writes `sent.json` back to the repo, enable write permissions:

```text
Repository -> Settings -> Actions -> General -> Workflow permissions
```

Select:

```text
Read and write permissions
```

## Tests

Run the unit tests:

```bash
python3 -m unittest discover -v
```

Check Python syntax:

```bash
python3 -m py_compile bot.py test_bot.py
```

Check imports:

```bash
python3 -c 'import bot; print("import ok")'
```

## Retry Behavior

`retry_call()` retries external calls:

- Gemini generation: 3 attempts by default.
- X post creation: 2 attempts.

Backoff schedule:

```text
2 seconds -> 4 seconds
```

If the final attempt fails, the exception is raised and GitHub Actions shows the failure in the run logs.

## Notes

- The current bot posts text only.
- `sent.json` should be committed to the repository so GitHub Actions can remember what has already been posted.
- GitHub Actions cron schedules are evaluated in UTC, but the bot itself decides whether to post using UK time.
- If X returns `403`, `429`, or other API errors, check the app permissions and access token permissions in the X Developer Portal.
