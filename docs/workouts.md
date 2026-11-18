# Workout tools

The full tool list is in [tools.md](tools.md). This page explains the workout builders and the raw workout format in detail.


These builder tools let an LLM create and schedule workouts without writing raw Garmin JSON.

## `create_walk_run_workout`

Creates a walk/run interval workout with optional heart-rate zone target.

```json
{
  "name": "W3 Mié 2:2",
  "run_seconds": 120,
  "walk_seconds": 120,
  "repeats": 9,
  "warmup_min": 10,
  "cooldown_min": 8,
  "hr_zone": "Z3"
}
```

Returns: `{"status": "success", "workout_id": 1234567890, ...}`

## `create_z2_walk_workout`

Creates a steady Z2 walking workout.

```json
{
  "name": "Z2 Walk 45m",
  "duration_min": 45,
  "hr_min": 110,
  "hr_max": 130
}
```

Returns: `{"status": "success", "workout_id": 1234567890, ...}`

## `create_strength_workout`

Creates a strength workout from a list of exercises. Each becomes a reps-based step, with the
name kept in the step description. The name is also sent as `exerciseName`, but Garmin only
retains that when it matches one of its own exercise keys (e.g. `FARMERS_CARRY`) — any other
value is accepted and then stored empty.

`category` is optional and passed straight through. Omit it and the key is left out of the
payload entirely, which Garmin accepts. Supply it and it must be one of Garmin's exercise
categories — anything else, including `OTHER` and `UNASSIGNED`, is rejected with
`400 - Invalid category`. The full list is published at
[`Exercises.json`](https://connect.garmin.com/web-data/exercises/Exercises.json).

```json
{
  "name": "Full Body A",
  "exercises": [
    {"name": "Sentadillas", "sets": 3, "reps": 12, "rest_seconds": 90},
    {"name": "Flexiones",   "sets": 3, "reps": 15, "rest_seconds": 60},
    {"name": "Peso muerto", "sets": 3, "reps": 10, "rest_seconds": 90},
    {"name": "Farmers Carry 40m", "sets": 3, "reps": 1, "rest_seconds": 90, "category": "CARRY"}
  ]
}
```

Returns: `{"status": "success", "workout_id": 1234567890, ...}`

## `schedule_week`

Schedules multiple workouts in one call.

```json
{
  "week": [
    {"date": "2026-05-12", "workout_id": 1234567890},
    {"date": "2026-05-14", "workout_id": 1234567891}
  ]
}
```

Returns: `{"status": "complete", "scheduled": [...]}`

## Full flow example

```text
create_walk_run_workout(name="W3 Mié 2:2", run_seconds=120, walk_seconds=120,
                        repeats=9, warmup_min=10, cooldown_min=8)
  → workout_id = 1560092011

schedule_workout(workout_id=1560092011, date="2026-05-06")
  → OK
```

After syncing your watch, the workout appears on the Forerunner 965 calendar.

## Raw `upload_workout` end conditions

When building custom workout JSON for `upload_workout` or `upload_workouts`, the
`endCondition.conditionTypeId` and `endCondition.conditionTypeKey` must match
Garmin's canonical mapping. Garmin treats the numeric `conditionTypeId` as the
source of truth; if the key and ID conflict, Garmin stores the condition that
matches the ID.

For example, this is invalid for a heart-rate end condition because ID `4` is
`calories`, not `heart.rate`:

```json
{
  "endCondition": {
    "conditionTypeId": 4,
    "conditionTypeKey": "heart.rate"
  },
  "endConditionValue": 145
}
```

Use ID `6` for heart rate:

```json
{
  "endCondition": {
    "conditionTypeId": 6,
    "conditionTypeKey": "heart.rate"
  },
  "endConditionValue": 145
}
```

For a zone-based heart-rate end condition, use `endConditionZone` (1-5) on the
same `endCondition` object and omit `endConditionValue`. If both are sent,
Garmin keeps the zone and drops the value (verified against the production API
on 2026-09-01):

```json
{
  "endCondition": {
    "conditionTypeId": 6,
    "conditionTypeKey": "heart.rate",
    "endConditionZone": 2
  }
}
```


Common end-condition IDs:

| ID | Key |
|---:|---|
| 1 | `lap.button` |
| 2 | `time` |
| 3 | `distance` |
| 4 | `calories` |
| 5 | `power` |
| 6 | `heart.rate` |
| 7 | `iterations` |
| 8 | `fixed.rest` |
| 9 | `fixed.repetition` |
| 10 | `reps` |
| 11 | `training.peaks.tss` |

## Raw `upload_workout` target types

When building raw Garmin workout JSON, `targetType.workoutTargetTypeId` and
`targetType.workoutTargetTypeKey` must use Garmin's canonical mapping. Garmin
treats the numeric ID as authoritative: a mismatched payload such as
`{"workoutTargetTypeId": 6, "workoutTargetTypeKey": "heart.rate"}` is stored as
`pace.zone`, because ID `6` means `pace.zone`.

For a custom heart-rate range, use target type ID `4` with `heart.rate.zone` and
put the bpm range in `targetValueOne` / `targetValueTwo`. These value fields
belong on the workout step, alongside `targetType`; do not nest them inside the
`targetType` object:

```json
{
  "targetType": {
    "workoutTargetTypeId": 4,
    "workoutTargetTypeKey": "heart.rate.zone"
  },
  "targetValueOne": 143,
  "targetValueTwo": 157
}
```

The same shape applies to a custom running pace range. Pace bounds use meters
per second:

```json
{
  "targetType": {
    "workoutTargetTypeId": 6,
    "workoutTargetTypeKey": "pace.zone"
  },
  "targetValueOne": 1.9607843,
  "targetValueTwo": 2.0833333
}
```

That example represents `8:00–8:30 min/km`. The lower numeric bound is listed
first for consistency with the heart-rate example; Garmin normalizes either
bound order. Garmin silently discards values nested inside `targetType`, leaving
a pace target with no active range. The upload tools repair that unambiguous
nesting mistake, but reject the request if nested and step-level values conflict.

For a named Garmin HR zone, use the same target type with `zoneNumber` instead:

```json
{
  "targetType": {
    "workoutTargetTypeId": 4,
    "workoutTargetTypeKey": "heart.rate.zone"
  },
  "zoneNumber": 3
}
```

Use either `zoneNumber` or `targetValueOne` / `targetValueTwo` on a target, not
both. Garmin treats the named zone as authoritative and silently discards a
coexisting custom range, so the upload tools reject that ambiguous shape.
