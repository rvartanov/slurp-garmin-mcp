# Changelog

All notable changes to Slurp garmin-mcp. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `get_calendar_events` returns `event_id`, Garmin's id for the calendar
  event, in preparation for tools that change and delete events.
- `GARMIN_MCP_ALLOWED_HOSTS` and `GARMIN_MCP_ALLOWED_ORIGINS`: host names and
  origins to accept next to loopback in the MCP SDK's DNS-rebinding check.
- Race and calendar event tools (`race_events` module): `get_calendar_event`,
  `get_upcoming_events`, `get_primary_event`, `update_calendar_event`
  (merges changes into the full event, keeps its id), `delete_calendar_event`
  (asks for confirmation first) and `update_workout` (replaces a workout in
  place, keeping its id and schedules; upstream #523).
- `create_race_event`: add a race or goal event to the Garmin calendar, with
  distance, local start time, goal time and note.
- Extended health tools (`health_extra` module), covering 47 more
  garminconnect methods. Read series are bundled: `get_health_stats`
  (19 daily series over a date range), `get_health_trend` (weekly and
  monthly totals), `get_health_day` (9 single-day details),
  `get_account_stats` (lifetime totals, per-sport statistics, last sync,
  nutrition status), plus `get_health_snapshot`, `get_ecg_recordings`,
  `get_ecg` and `get_jetlag_trips`. Writes: `set_steps_goal`,
  `create_jetlag_trip`, `update_jetlag_trip`, `delete_jetlag_trip`.
- `get_health_stats`, `get_health_trend`, `get_health_day` and
  `get_health_snapshot` shorten series longer than 60 items to their length,
  first and last item; `detail=true` returns everything. A day's sleep data
  went from about 270 KB to a few KB.
- Extended performance-metric tools (`metrics_extra` module), covering 35
  more garminconnect methods: `get_performance_metric` (14 latest values:
  VO2 max, training status, load balance, heat/altitude and SpO2
  acclimation, Cycling Ability, Running Economy, Critical Swim Speed,
  stamina, Fitness Age, one-rep max, glucose, biometrics),
  `get_performance_history` (15 histories incl. FTP, readiness, power
  curves for cycling and rowing), `get_training_zones`, `set_power_zones`,
  `get_one_rep_max_history` and `get_activity_power_curve`.
- Training plan, calendar and course tools (`training_extra` module),
  covering 22 more garminconnect methods: `get_training_plans` (yours,
  active, catalogue), `get_training_plan`, `schedule_training_plan`,
  `delete_training_plan`, `get_calendar_overview` (week or year),
  `move_calendar_item`, `create_calendar_note`, `update_calendar_note`,
  `delete_calendar_note`, `create_course_from_activity`, `update_course`,
  `get_course_favorites`, `set_course_favorite` and `get_pace_bands`.
- Extended activity tools (`activities_extra` module), covering 25 more
  garminconnect methods: `get_activity_data` (12 parts: details, laps,
  rounds, workout steps, jumps, sub-second data, swim lengths, map,
  polyline, photos, segments, previous/next), `find_activities` (search
  with the web app's filters, favourites, last activity, training load per
  activity), `get_activity_aggregates` (weekly totals, fastest splits,
  available metrics), `get_activity_event_types`, `set_activity_favorite`,
  `update_activity` (several fields at once), `create_activity_from_json`
  and `upload_activity_file` (FIT/GPX/TCX as base64, optionally as an
  import that is not forwarded to Strava).
- `find_activities` returns 23 key fields per activity unless `detail=true`
  (a search of 20 activities went from ~127 KB). `get_activity_data`
  explains Garmin's HTTP 500 for parts an activity does not have (workout
  steps, sub-second data, swim lengths, rounds, jumps).
- Workout library, body and gear tools (`equipment_extra` module), covering
  33 more garminconnect methods: `get_workout_library`,
  `get_upcoming_workouts`, `copy_workout`; `get_weight_data`,
  `get_blood_pressure_data`, `delete_weigh_in`,
  `update_blood_pressure_note`, `delete_blood_pressure`; `get_gear_data`
  (gear v2: list, details, activities, types, catalogue search),
  `create_gear`, `update_gear`, `set_gear_status`, `set_gear_default` and
  `delete_gear`.
- `get_upcoming_workouts` lists each scheduled workout's name, sport,
  duration and distance unless `detail=true` (two weeks of a training
  plan went from ~350 KB).
- Achievement, goal, device, profile, women's health and golf tools
  (`account_extra` module), covering the remaining 52 garminconnect
  methods: `get_achievements` (14 kinds: badges, challenges, personal-record
  metadata), `get_wellness_goals`, `set_daily_goal`, `get_device_data`
  (9 kinds incl. sensors, device messages, solar gain),
  `update_device_settings`, `send_scheduled_workouts_to_devices`,
  `set_primary_training_device`, `get_profile_data`, `update_user_settings`,
  `get_menstrual_overview`, `log_menstrual_day`, `set_menstrual_periods`,
  `confirm_menstrual_period`, `update_menstrual_settings` and
  `get_golf_data`.
- The compact output of the extended tools also leaves out fields that are
  null, false or empty, and device lists keep 13 key fields per device;
  `detail=true` returns Garmin's full response. `get_device_data`,
  `get_profile_data`, `get_calendar_overview` and `get_pace_bands` gain
  `detail`.
- Download tools (`downloads_extra` module): `download_course_file` (GPX
  or FIT), `download_health_snapshot_file` (a day's ZIP or one session's
  FIT), `request_report` and `download_report` (PDF). Files up to 5 MB come
  back base64-encoded so remote clients get them; `save=true` stores them
  in the server's download directory.
- `download_report` works with Garmin's real report ids (base64 text with
  `=`, `+`, `/`), which garminconnect 0.3.20 rejects; the report status and
  content endpoints are called directly with the id URL-encoded. Report sub
  categories are `Daily`, `SevenDays`, `FourWeeks` and `Yearly`.
- The upstream watch merges clean upstream changes whose tests pass through
  a pull request (`scripts/merge_upstream.sh`); conflicts and failing tests
  still go to the `upstream-sync` issue.
- `deploy/auto-update.sh` with a systemd timer: deploys the newest commit on
  `main` whose CI passed, restarts the service and rolls back when it does
  not become ready.
- Release workflow: pushing a tag `v<version>` publishes the Docker image to
  `ghcr.io/rvartanov/slurp-garmin-mcp` (tags `<version>` and `latest`) and
  creates a GitHub release with that version's changelog section
  (upstream #337, #136).

### Changed

- garminconnect 0.3.2 → 0.3.20. Fixes Garmin Connect China login (upstream
  #257, #345) and makes about 200 more library methods available for new
  tools. Requires Python 3.12 or newer; CI tests 3.12, 3.13 and 3.14. The
  token file format is unchanged, so existing logins keep working.

### Fixed

- `create_gear` works: it now sends the payload of the Garmin Connect web
  form (`null` for empty notes, model and activity types). garminconnect
  0.3.20 sends `[]` and `""` there and Garmin answered HTTP 400. `model` is
  now optional, as in the web form.

Taken from open upstream pull requests (authorship kept, `cherry picked from` in each commit):

- Recovery time right after a workout was reported as 0 h when Garmin kept a
  stale `REACHED_ZERO` phrase (upstream #491, PR #495).
- `get_energy_balance` no longer counts today's partial day in mean intake
  (upstream #504, PR #505).
- Activity analysis weights heart-rate drift, grade buckets, climb averages
  and temperature summaries by recorded time instead of sample count, and
  ends climbs at the first flat sample (upstream #493, #494, #498, #499,
  #502; PRs #496, #497, #500, #501, #503).
- `GARMIN_TZ`: write tools read dates and local times in the user's zone;
  `set_blood_pressure` takes an optional timestamp. Without `GARMIN_TZ`,
  times without an offset are read as UTC (upstream #422, PR #444).

- Behind Tailscale Funnel, Caddy or nginx (the documented deployments) the
  server answered every MCP request with `421 Invalid Host header`, because
  the SDK only accepts a loopback `Host` on a loopback bind. The deployment
  examples now set `GARMIN_MCP_ALLOWED_HOSTS`.

### Security

- The upstream watch no longer merges anything: a clean, green upstream
  merge is opened as a pull request that waits for review. Upstream code
  runs in a job with a read-only token; a separate job pushes the branch and
  opens the pull request. Its actions are pinned by commit SHA.
- Locked dependencies: mcp 1.28.1 → 1.30.0, h11 0.14.0 → 0.16.0, httpcore
  1.0.7 → 1.0.9 and certifi 2025.1.31 → 2026.11.20, for known
  vulnerabilities in the older versions. The security workflow now runs
  `pip-audit` against `uv.lock` and fails on a known vulnerability.
- File tools stay inside the download directory. With
  `GARMIN_FIT_DOWNLOAD_DIR` set, `download_activity_file`'s `output_dir`,
  `download_course_gpx`'s `output_path`, `save=true` downloads,
  `set_fit_download_dir` and `upload_course`'s `gpx_path` must resolve
  (symlinks included) inside it. Over HTTP without it, the limit is
  `<state dir>/downloads`, which is now also the default download directory
  there, and `set_fit_download_dir` is not offered. Files are written
  without following a symlink. stdio without `GARMIN_FIT_DOWNLOAD_DIR` is
  unchanged.
- Unpacking a downloaded FIT file (ZIP or gzip) stops at 25 MB, the upload
  limit, so a crafted archive cannot exhaust the server's memory.
- Dates and ids that the nutrition tools and `get_workout_by_id` put into
  a Garmin API path are checked first (`YYYY-MM-DD`; letters, digits and
  dashes), so a crafted argument cannot reach another endpoint.
- The base64 copy of the Garmin tokens (`~/.garminconnect_base64`) is no
  longer written by default: only when `GARMINTOKENS_BASE64` names a file.
  Nothing in the server reads it. It is created owner-only in one step
  (it was created with the default umask and chmod-ed afterwards) and a
  symlink in its place is refused.
- `unschedule_workout`, `unschedule_workouts` and `remove_gear_from_activity`
  ask for confirmation like the delete tools: without `confirm=true` they
  return a preview and change nothing. `delete_workouts` and
  `unschedule_workouts` take at most 25 ids per call.
- The Docker instructions no longer make the URL secret world-readable
  (`chmod 644`): it is owned by the container user (uid 10001) with mode
  0400.

## [1.0.0] - 2026-11-18

First release as Slurp garmin-mcp, forked from
[Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) at commit
`a2ca5fc` (20 October 2026). Everything up to that commit is upstream's work;
its history is preserved in this repository.

### Added

- URL-secret mode: with `GARMIN_MCP_URL_SECRET` or
  `GARMIN_MCP_URL_SECRET_FILE` the MCP endpoints are served under
  `/<secret>/` only and every other path is a 404, except `/healthz` and
  `/readyz`. For clients that take a URL but cannot send an Authorization
  header. The secret is kept out of the server's log.
- `GARMIN_MCP_HTTP_TOKEN_FILE` next to `GARMIN_MCP_HTTP_TOKEN`, for systemd
  credentials and Docker secrets.
- `GARMIN_MCP_REQUIRE_AUTH`: refuse to start an HTTP transport without a
  bearer token or URL secret.
- `garmin-mcp --help` and `garmin-mcp --version`; `slurp-garmin-mcp` as an
  alias for `garmin-mcp`.
- systemd deployment: hardened system unit, user unit, `deploy/install.sh`
  and `deploy/uninstall.sh`, `deploy/env.example`.
- Reverse proxy examples for Caddy and nginx, and for Tailscale Funnel.
- Documentation in `docs/`, with `docs/tools.md` generated from the
  registered tools by `scripts/generate_tools_doc.py`.

### Changed

- Package name is `slurp-garmin-mcp` (was `garmin-mcp`); the Python module
  `garmin_mcp` and the commands `garmin-mcp` and `garmin-mcp-auth` are
  unchanged. The MCP server identifies itself as "Slurp garmin-mcp".
- Docker image: runs as a non-root user, serves streamable HTTP on port 8000
  by default (was stdio), requires a bearer token or URL secret, has a health
  check, keeps tokens in the `/data` volume (was `/root/.garminconnect`) and
  no longer contains the tests. Set `GARMIN_MCP_TRANSPORT=stdio` for the old
  behaviour.
- `docker-compose.yml` uses a URL secret from a Docker secret and publishes
  the port on loopback only.
- Development dependencies moved to `[dependency-groups]`.

### Removed

- The checked-in `garmin-mcp.dxt` bundle; build it with
  `scripts/build_dxt.sh`.
- Upstream maintainer tooling (`.claude/skills/babysit-prs`).

[Unreleased]: https://github.com/rvartanov/slurp-garmin-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/rvartanov/slurp-garmin-mcp/releases/tag/v1.0.0
