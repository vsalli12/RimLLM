# Event protocol, version 1

POST JSON to `http://127.0.0.1:8765/events`:

```json
{
  "schema_version": 1,
  "batch_id": "unique-batch-id",
  "events": [
    {
      "schema_version": 1,
      "event_id": "unique-event-id",
      "playthrough_id": "persisted-in-save",
      "session_id": "new-for-each-load",
      "sequence": 1,
      "tick": 90000,
      "game_day": 2,
      "tick_of_day": 30000,
      "map_id": 0,
      "diary_carrier_id": null,
      "type": "diary.owner_changed",
      "participants": [],
      "data": {"previous_carrier_id": "Thing_Human123", "new_carrier_id": null}
    }
  ]
}
```

The response is HTTP 200 with the batch ID as plain text, after committing events
to SQLite. The mod deletes an outbox file only after that exact acknowledgement.
Duplicate event IDs are ignored. Narrator state is maintained per playthrough and
session; an older sequence cannot overwrite a newer narrator. Every event carries
the current narrator ID, allowing recovery even without an ownership-change event.

## Current coverage

| Event | Meaning |
| --- | --- |
| `session.started` | Parent session and last event ID recorded in the loaded save. |
| `session.snapshot` | Initial pawn conditions and colony map summary. |
| `pawn.profile` | First observation or changed name, age, traits, skills, faction or relationships. |
| `pawn.job_changed` | Previous/current job, job ID, definition, start tick, player-forced flag and targets. |
| `diary.owner_changed` | Previous/new carrier; null means neutral narration. |
| `social.interaction` | Actual social-log entry, initiator/recipient, opinions and contextual states. |
| `pawn.injured` | First visible injury of a type on a body part, with attacker when known/visible. |
| `pawn.downed`, `pawn.recovered_from_downing`, `pawn.died` | Major health transitions. |
| `pawn.mental_state_started` | Mental-state type, reason, target and mood context. |
| `pawn.faction_changed` | Faction transition and recruiter where available. |
| `pawn.condition_changed` | Visible health condition types, mental state, relationships or prisoner/slave status changed. |
| `pawn.observed`, `pawn.no_longer_observed` | Entered/left the observed pawn set, not proof of arrival/death. |
| `pawn.map_changed` | Observed pawn moved between maps or off-map. |
| `colony.letter` | Letter actually shown to the player, including its displayed text. |
| `colony.daily_snapshot` | Current pawn states, colonist counts and colony wealth at a game-day boundary. |

Pawn state includes visible health conditions, mood thoughts and relationships.
Mood offsets describe individual thoughts, not a precomputed sum of the mood UI.
Profiles use whole-year ages to avoid resending them every few ticks.
Profiles also include `dead`, `spawned`, `map_id`, `in_caravan`, `is_prisoner`, and
`is_slave`. New profiles also include `is_humanlike`, `is_animal`, and
`hostile_to_player`, so prompt selection does not need to guess race or hostility.
The routine roster only includes living map pawns and player pawns
held on maps or travelling in caravans, not every player-faction world pawn.
Death events still carry profiles of their subjects. Older profiles lack these
presence fields; the prompt builder uses snapshot/map/activity evidence and keeps
unplaced profiles outside the active cast instead of assuming `is_colonist` proves
colony membership. It does not label uncertain records as skeletons.

Social events include `social_log_text`: RimWorld's generated social-log sentence,
including the chitchat topic and additional outcome sentences when present. It is
rendered from `social_log_pov_pawn_id` (the initiator), in the game's active language,
and may contain rich-text tags. This comes from the original log entry, not a new
randomly generated conversation. A standalone structured topic is not supplied;
the backend can extract one from the sentence. Previously received events will
not acquire this field retroactively.

Observation includes player pawns and unfogged spawned pawns. Periodic profiles
cover humanlikes; involved animals can also appear in individual events. It does
not read scheduled incidents, hidden health conditions or hidden map contents.
This is initial vanilla coverage, not every possible DLC/mod event or game action.
Job changes are streamed, but progress within a job, movement each tick, and repeated
damage to the same injury are not. `pawn.job_changed` uses actual job instance IDs:
continuing the same job emits nothing, while starting a new mining job on a different
rock emits a new event even though the job definition is still `Mine`. It records job
assignment, which can include walking to the work site before performing the action.
Ending a job with no replacement emits `current_job: null`. Each session also gets an
initial observation of each known humanlike pawn's current job, marked
`initial_observation: true`. Snapshots contain `current_job` too. No complete mood or
health snapshot is repeated in the lightweight job-change event. Fogged target thing
details are withheld. Work-tab priority changes are not job assignments and are not
captured by this event.
Letters provide many raid/visitor/incident notifications rather than bespoke hooks.

## Daily prompt reduction

The prompt builder replays the selected save history to update profiles, deaths,
and presence. Today's involved actors include enemies and deaths; quiet living
colony residents stay in the cast, while historical deaths and departed pawns do
not. Raid letters identify the attacking faction (`Raid: <faction>` in older
English records); involved members are labeled `RAIDER`, unless current colony
membership, prisoner status, or explicit non-hostility says otherwise. Other
hostile pawns are labeled `HOSTILE`; outsiders are not assumed to be colonists.

Raid letters, deaths, downings, ignition assignments, and grouped firefighting
appear before routine activity. Injury callbacks collapse into short outcomes
per victim, map and bout, including death callbacks that precede the final injury
callback. Lesser injuries become supporting combat notes. Firefighting assignments
merge across hour boundaries when no more than an hour apart; they do not establish
the cause of a fire or whether it was extinguished.

Combat is omitted only when both subject and attacker are confirmed unaffiliated
animals. Colony pets, faction animals, humanlikes, and uncertain participants are
retained. Older packets use a small explicit list of recognized vanilla animal
species; unknown species stay visible until explicit race flags are available.

Mood appears once per involved colony pawn, with an observed start/end range,
any lower observed category, and at most two deduplicated pressures. Condition
events describe health/relationship/status differences rather than repeating
snapshots; routine alcohol condition churn is omitted. Stored events are unchanged.

Diary ownership is checked each game tick; rapid changes within one tick can collapse
into the final holder. Temporary inventory removal by the Diary's retention patch
does not become a false drop event. General condition changes are checked every
60 ticks; snapshots occur every 60,000 ticks. `game_day` is elapsed simulation day,
not a map's longitude-dependent calendar date. A snapshot is boundary state, not
a prewritten summary of the preceding day.

## Saves and delivery

Pawn IDs are scoped by playthrough. A new session starts on each load, with the
saved session/event checkpoint as its parent. The backend must follow this ancestry
when generating stories, excluding abandoned futures after a reload. Files copied
from the same save share a playthrough ID and form separate sessions.

Batches of up to 100 records are written in the background to
`<RimWorld save-data folder>/RimChronicle/outbox`, then sent over loopback. Failed
deliveries retry, including after restarting the game. No game objects are accessed
by the worker. Normal exit attempts a bounded flush; crashes can lose the in-memory
tail before it reaches disk. Disk failure can fill the 20,000-event memory limit,
after which new events are dropped with a warning. Outbox and SQLite storage are
not automatically pruned. There is no cloud destination or LLM call.

The Python receiver is deliberately separate from game code and can move to its
own repo. SQLite provides durable receipt/deduplication, not narrative processing.

## Automated checks

```powershell
dotnet build dev/TransportSmoke/TransportSmoke.csproj -c Release
conda activate default
python -X utf8 -m unittest discover -s dev -p 'test_*.py' -v
```

Checks cover retry deduplication after restart, out-of-order narrator updates,
separate reload sessions, invalid-batch atomicity, Unicode, C# JSON serialization,
and disk-buffer replay through a real loopback HTTP server. RimWorld hooks require
the manual in-game checks in the main README.
