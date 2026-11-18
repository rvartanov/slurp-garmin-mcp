# Tool notes

Background on a few tools whose behaviour needs more than one line. The full list is in [tools.md](tools.md).

## Gear Notes

Each item in the `gear` array returned by `get_gear` includes a `notes` field
containing the free-text Notes value shown in Garmin Connect. Gear without a
Notes value returns `null`; all existing gear fields remain unchanged.

## Activity File Downloads

Two tools let you download a raw activity file to disk:

- **`download_activity_file(activity_id, format="fit", output_dir=None)`** — downloads the activity and saves it to the configured directory. `format` accepts `fit` (default), `gpx`, `tcx`, or `csv`.
- **`set_fit_download_dir(path)`** — sets and persists the default download directory (written to the config file).

**Where files are saved (precedence):**

1. `output_dir` argument — one-off override, not persisted.
2. `GARMIN_FIT_DOWNLOAD_DIR` environment variable.
3. Persisted config set via `set_fit_download_dir`.

**First-run behavior:** if no directory is configured, `download_activity_file` returns `status: "needs_setup"`. The assistant will ask where you want to save files (suggesting the current directory as default), call `set_fit_download_dir` to persist your choice, and then retry the download automatically.

## Strength Exercise Sets

`set_activity_exercise_sets(activity_id, sets)` writes structured sets onto a recorded
strength activity, the same per-set grid the Garmin Connect "Edit sets" screen saves, so
they appear in Garmin's exercise history and volume charts. It **replaces every existing
set**, including watch-detected ones; read them first with `get_activity_exercise_sets`
if you want to keep any.

Each set takes a `category` and optional `exercise_name` using Garmin's keys from
[`Exercises.json`](https://connect.garmin.com/web-data/exercises/Exercises.json), plus
optional `reps`, `weight_kg` or `weight_lb` (omit for bodyweight), `duration_seconds` and
`rest_seconds`. Garmin rejects unknown keys and leaves the activity unchanged.

If the watch recorded the right sets but misidentified the exercises, pass
`keep_timing: true`: the recorded start times, durations and rest periods are kept and only
the exercise, reps and weight are replaced, in order. The number of sets must match the
activity's recorded active sets.

```json
{
  "activity_id": 12345678901,
  "sets": [
    {"category": "DEADLIFT", "exercise_name": "BARBELL_DEADLIFT", "reps": 5, "weight_kg": 150, "rest_seconds": 180},
    {"category": "PULL_UP", "reps": 8}
  ]
}
```

## Intentionally Skipped Endpoints

Some endpoints are not implemented due to performance or complexity considerations:

**High Data Volume:**
- `get_activity_details()` - Returns large GPS tracks and chart data (50KB-500KB). Use `get_activity()` for summaries instead.

**Specialized Workout Formats:**
- `upload_running_workout()`, `upload_cycling_workout()`, `upload_swimming_workout()` - Sport-specific workout uploads. Use `upload_workout()` for general workouts.

**Maintenance & Destructive Operations:**
- `delete_blood_pressure()` - Destructive operations require careful consideration.
- `delete_activity()` is implemented with a confirmation gate: call once to
  preview, then again with `confirm=true` to delete. Deletions are logged to
  stderr. There is no undo.
- Internal/Auth methods: `login()`, `resume_login()`, `connectapi()`, `download()` - Handled automatically by the library.

If you need any of these endpoints, please [open an issue](https://github.com/rvartanov/slurp-garmin-mcp/issues).
