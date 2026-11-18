# Clever sandbox activity simulator

Keeps one Clever sandbox district looking alive, every school day, with no human in the loop.

| What | How | Where it shows up |
|---|---|---|
| **Roster drift** | Each weekday at ~5am PT, a few students enroll or withdraw, a teacher leaves or is hired, families move, guardians update a phone number. The full roster is re-uploaded over SFTP. | Events API (`users.*`, `sections.*`), Data API |
| **Logins** | Each weekday between 8am and 2pm PT, 60–80% of students and some teachers log in through Clever and launch an app tile in a headless browser. | Clever login analytics, the apps' own usage data |

Everything runs on GitHub Actions. Nothing is paid. The roster lives in this repo
(`state/roster.json`), so every day's changes are a commit you can read.

## How it works

```
config/sandbox.yaml    district shape, drift rates, login schedule, app tiles
state/roster.json      the district as it is now (source of truth, committed daily)
state/changelog/       what changed each day + the events we expect it to produce
state/events/          what the Events API actually reported (counted each morning)
state/runs/<date>/     the day's login plan and per-batch results
sim/                   the code (python -m sim -h)
```

**Data.** Two schools: Cedar Ridge Elementary (K–5, 19 per grade, one homeroom teacher per grade)
and Juniper Valley Middle (6–8, 29 per grade, one teacher per subject). That's about 200 students,
12 teachers, 30 sections and about 240 guardian contacts. Students come in families: siblings share
a surname, address and guardians, and siblings can be at different schools. Most guardians share the
children's surname. Some don't (a mother who kept her name, a grandparent raising the kids, a stepparent).
Surnames are frequency-weighted from US data and capped at four families each. Every email uses a
reserved `.example` or `example.com` domain, and every phone number is a fictional 555-01XX.

**Drift stays balanced.** Daily adds and removals lean toward each total's target. If students
drift low, adds become more likely the next day. Hard limits keep students within ±5% and
teachers within ±1. When a teacher leaves, a colleague covers their sections until a new hire
takes them over. Extra hires run new intervention groups. A retried run reproduces the same day
exactly, because each day's changes are seeded by its date.

**Logins.** Every user's username and password is their own ID (`Student_number` / `Teacher_number`),
written into the CSVs. Each simulated user gets a fresh browser context. They log in, click
the app tile, wait for the app's URL, optionally click through a screen, and leave. Users created
today are skipped until tomorrow so Clever has time to sync them.

**Safety.** Before any upload, the token's district must match `CLEVER_DISTRICT_ID` and its name
must start with `#DEMO`, or the upload is refused. Uploads go out at most once an hour (Clever's rule).
The roster must pass integrity checks before it is uploaded.

## Setup

### 1. In Clever
1. Create the custom sandbox district, then **Configure data sync**: pick a SIS option, then **SFTP**.
2. **Configure login method** → Clever Authentication (username and password). Turn off password
   changes, first-login resets and MFA for students and teachers.
3. Connect the app(s), and under **Data Sharing** share **by district** (all students and teachers),
   so newly added students see the tiles without anyone touching sharing rules.
4. In the dev app's settings, **Settings > Integrations > Enable events** *before* the first upload.

### 2. In GitHub
Add these under **Settings > Secrets and variables > Actions** (see `.env.example`):

| Secret | Used by |
|---|---|
| `CLEVER_DISTRICT_ID` | safety check |
| `CLEVER_DISTRICT_TOKEN` | safety check, Events API report |
| `CLEVER_SFTP_USERNAME`, `CLEVER_SFTP_PASSWORD` | uploads |
| `CLEVER_SFTP_HOST_KEY` (optional) | pins the SFTP server key: one full line from `ssh-keyscan sftp2.clever.com 2>/dev/null` |
| `CLEVER_LOGIN_URL` | logins, probe |

### 3. First run, in order (Actions tab → workflow → Run workflow)
Scheduled logins start **paused** (`logins.enabled: false` in `config/sandbox.yaml`), because app
tiles can only be added once the first sync has created the users. Drift runs on schedule from day one.

1. **Tests**: should pass.
2. **Bootstrap (first load)**: type `LOAD`. Uploads the district and commits `state/roster.json`.
   Check the district dashboard's sync page about 10 minutes later.
3. **In Clever**: once the sync shows the users, add the app tiles.
4. **Probe login page**: screenshots the login page and portal, and lists the form fields and tile
   names. If login fails, adjust `logins:` selectors in `config/sandbox.yaml` using what it found.
5. **Simulated logins** with `batch: 0` and `limit: 3`: a three-user test. Check the job summary, and the
   `login-failures-*` artifact if anything failed. Manual runs don't count as the day's scheduled batch.
6. **Daily roster drift** with `force: true`: one drift cycle (wait an hour after the bootstrap upload).
   The next morning's run reports the resulting events in its job summary and in `state/events/`.
7. **Unpause logins**: set `logins.enabled: true` in `config/sandbox.yaml` and commit (the GitHub web
   editor is fine). The next batch hour picks it up.

After that, it runs on its own. Set it back to `false` any time to pause logins without touching drift.

## Configuring

All knobs live in `config/sandbox.yaml`: grade sizes, demographics, drift rates and bands, login
fraction, batch hours and weights, concurrency, and the apps. To add an app or a click-through:

```yaml
apps:
  - key: lantern
    tile: "Lantern"            # the tile's visible name on the portal
    weight: 2                  # relative share of launches
    expect_url: "lantern"      # regex the app's URL must match to count as launched
    steps:                     # optional, run after the app loads
      - {action: click_text, text: "Get started"}
      - {action: wait_ms, ms: 2000}
  - key: coworker
    tile: "Coworker App"
    weight: 1
    expect_url: "coworkerapp\\.com"
```

Step actions: `click_text`, `click_selector`, `wait_for_selector`, `wait_ms`, `screenshot`.

## GitHub Actions minutes

A private repo on the free plan includes 2,000 minutes a month. Expected use is about 22 weekdays ×
(4 login batches × ~8–12 min, plus 4 idle checks × ~1 min, plus drift ~2 min), roughly
1,000–1,250 min a month. To use fewer, reduce `student_fraction`, raise `concurrency`, or use fewer
`batch_hours_pt`.

Two GitHub behaviors to know about. Scheduled runs can start late when GitHub is busy; the
jobs catch up rather than skip. GitHub also pauses schedules on repos with no commits for 60 days,
but the daily state commits prevent that.

## Local use

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env   # fill in
python -m pytest -q
python -m sim status
python -m sim daily --dry-run --force   # see tomorrow's kind of drift, uploads nothing
python -m sim plan                       # who would log in today
python -m sim logins --batch 0 --limit 2 --headed
```
