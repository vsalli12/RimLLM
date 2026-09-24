using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using RimWorld;
using Verse;
using static RimChronicle.ChronicleData;

namespace RimChronicle
{
    public sealed class ChronicleGameComponent : GameComponent
    {
        private string playthroughId;
        private string sessionId;
        private string lastEventId;
        private string carrierId;
        private int sequence;
        private int lastDay = -1;
        private bool started;
        private readonly Dictionary<string, string> profiles = new Dictionary<string, string>();
        private readonly Dictionary<string, Pawn> present = new Dictionary<string, Pawn>();
        private readonly Dictionary<string, string> conditions = new Dictionary<string, string>();
        private readonly Dictionary<string, int?> locations = new Dictionary<string, int?>();
        private readonly Dictionary<string, int?> jobIds = new Dictionary<string, int?>();
        private readonly Dictionary<string, object> jobStates = new Dictionary<string, object>();
        private readonly Dictionary<int, string> environments = new Dictionary<int, string>();
        private static int lastErrorTick = -60000;

        public ChronicleGameComponent(Game game) { }

        public override void ExposeData()
        {
            Scribe_Values.Look(ref playthroughId, "chroniclePlaythroughId");
            Scribe_Values.Look(ref sessionId, "chronicleSessionId");
            Scribe_Values.Look(ref lastEventId, "chronicleCheckpointEventId");
        }

        public static void Safely(Action<ChronicleGameComponent> action)
        {
            if (Current.ProgramState != ProgramState.Playing) return;
            ChronicleGameComponent recorder = Current.Game?.GetComponent<ChronicleGameComponent>();
            if (recorder == null || !recorder.started) return;
            try { action(recorder); }
            catch (Exception ex)
            {
                int tick = Find.TickManager.TicksGame;
                if (tick < lastErrorTick || tick - lastErrorTick >= 60000)
                {
                    lastErrorTick = tick;
                    Log.Warning("[RimChronicle] Could not capture an event: " + ex);
                }
            }
        }

        public override void GameComponentTick()
        {
            if (!started)
            {
                EventDelivery.Start(Path.Combine(GenFilePaths.SaveDataFolderPath, "RimChronicle", "outbox"));
                string parentSession = sessionId;
                string checkpoint = lastEventId;
                playthroughId = playthroughId ?? Guid.NewGuid().ToString("N");
                sessionId = Guid.NewGuid().ToString("N");
                started = true;
                Safely(r =>
                {
                    carrierId = Current.Game.GetComponent<NotebookGameComponent>()?.Carrier?.GetUniqueLoadID();
                    Emit("session.started", Object("parent_session_id", parentSession, "parent_event_id", checkpoint,
                        "scenario", ScenarioInfo()));
                    Snapshot("session.snapshot");
                    lastDay = Find.TickManager.TicksGame / 60000;
                });
            }
            Safely(r =>
            {
                Pawn carrier = Current.Game.GetComponent<NotebookGameComponent>()?.Carrier;
                string current = carrier?.GetUniqueLoadID();
                if (current != carrierId)
                {
                    string previous = carrierId;
                    carrierId = current;
                    if (carrier != null) SendProfile(carrier);
                    Emit("diary.owner_changed", Object("previous_carrier_id", previous, "new_carrier_id", current));
                }
                if (Find.TickManager.TicksGame % 60 == 0)
                {
                    RefreshPawns();
                    RecordEnvironment();
                }
                int day = Find.TickManager.TicksGame / 60000;
                if (day != lastDay)
                {
                    Snapshot("colony.daily_snapshot");
                    lastDay = day;
                }
            });
        }

        public override void GameComponentUpdate()
        {
            while (EventDelivery.Notices.TryDequeue(out string notice)) Log.Warning("[RimChronicle] " + notice);
        }

        public void Emit(string type, object data, Map map = null, object participants = null)
        {
            lastEventId = Guid.NewGuid().ToString("N");
            int tick = Find.TickManager.TicksGame;
            EventDelivery.Enqueue(EventJson.Encode(Object("schema_version", 1, "event_id", lastEventId,
                "playthrough_id", playthroughId, "session_id", sessionId, "sequence", ++sequence,
                "tick", tick, "game_day", tick / 60000 + 1, "tick_of_day", tick % 60000,
                "map_id", map?.uniqueID, "diary_carrier_id", Current.Game.GetComponent<NotebookGameComponent>()?.Carrier?.GetUniqueLoadID(), "type", type,
                "participants", participants ?? new object[0], "data", data)));
        }

        public void PawnEvent(string type, Pawn pawn, Pawn other = null, object details = null, string otherRole = "other")
        {
            if (!Visible(pawn)) return;
            SendProfile(pawn);
            var participants = new List<object> { Object("pawn_id", pawn.GetUniqueLoadID(), "role", "subject") };
            if (Visible(other))
            {
                SendProfile(other);
                participants.Add(Object("pawn_id", other.GetUniqueLoadID(), "role", otherRole));
            }
            Emit(type, Object("details", details, "subject_state", State(pawn),
                "other_state", Visible(other) ? State(other) : null), pawn.MapHeld, participants);
        }

        public void Social(Pawn initiator, Pawn recipient, InteractionDef interaction, PlayLogEntry_Interaction logEntry)
        {
            if (!Visible(initiator) || !Visible(recipient)) return;
            SendProfile(initiator);
            SendProfile(recipient);
            Emit("social.interaction", Object("interaction", interaction.defName, "label", interaction.label,
                "social_log_text", logEntry.ToGameStringFromPOV(initiator),
                "social_log_pov_pawn_id", initiator.GetUniqueLoadID(),
                "initiator_opinion", initiator.relations?.OpinionOf(recipient),
                "recipient_opinion", recipient.relations?.OpinionOf(initiator),
                "initiator_state", State(initiator), "recipient_state", State(recipient)), initiator.MapHeld,
                new[] { Object("pawn_id", initiator.GetUniqueLoadID(), "role", "initiator"),
                    Object("pawn_id", recipient.GetUniqueLoadID(), "role", "recipient") });
        }

        private void SendProfile(Pawn pawn)
        {
            object profile = Profile(pawn);
            string encoded = EventJson.Encode(profile);
            string id = pawn.GetUniqueLoadID();
            if (!profiles.TryGetValue(id, out string previous) || previous != encoded)
            {
                profiles[id] = encoded;
                Emit("pawn.profile", profile, pawn.MapHeld);
            }
        }

        public void RecordJob(Pawn pawn)
        {
            if (!Visible(pawn) || !pawn.RaceProps.Humanlike) return;
            string id = pawn.GetUniqueLoadID();
            int? currentId = pawn.CurJob?.loadID;
            bool known = jobIds.TryGetValue(id, out int? previousId);
            if (known && previousId == currentId) return;

            object current = JobState(pawn);
            jobStates.TryGetValue(id, out object previous);
            SendProfile(pawn);
            Emit("pawn.job_changed", Object("pawn_id", id, "initial_observation", !known,
                "previous_job", previous, "current_job", current), pawn.MapHeld,
                new[] { Object("pawn_id", id, "role", "worker") });
            jobIds[id] = currentId;
            jobStates[id] = current;
        }

        private void RefreshPawns()
        {
            List<Pawn> pawns = KnownPawns();
            var ids = new HashSet<string>(pawns.Select(p => p.GetUniqueLoadID()));
            foreach (Pawn pawn in pawns)
            {
                string id = pawn.GetUniqueLoadID();
                SendProfile(pawn);
                RecordJob(pawn);
                if (!present.ContainsKey(id)) Emit("pawn.observed", Object("pawn_id", id), pawn.MapHeld);
                if (locations.TryGetValue(id, out int? previousMap) && previousMap != pawn.MapHeld?.uniqueID)
                    Emit("pawn.map_changed", Object("pawn_id", id, "previous_map_id", previousMap, "new_map_id", pawn.MapHeld?.uniqueID), pawn.MapHeld);
                locations[id] = pawn.MapHeld?.uniqueID;
                // Changes in visible conditions, relationships and mental state, without every severity tick.
                string condition = EventJson.Encode(Object("health", pawn.health.hediffSet.hediffs.Where(h => h.Visible)
                    .Select(h => h.def.defName + ":" + h.Part?.Label).OrderBy(s => s).ToList(),
                    "mental_state", pawn.MentalStateDef?.defName, "is_prisoner", pawn.IsPrisonerOfColony,
                    "is_slave", pawn.IsSlaveOfColony, "relationships", Relationships(pawn)));
                if (conditions.TryGetValue(id, out string previousCondition) && previousCondition != condition)
                    PawnEvent("pawn.condition_changed", pawn);
                conditions[id] = condition;
                present[id] = pawn;
            }
            foreach (string id in present.Keys.Where(id => !ids.Contains(id)).ToList())
            {
                Emit("pawn.no_longer_observed", Object("pawn_id", id));
                present.Remove(id);
            }
        }

        private void Snapshot(string type)
        {
            RefreshPawns();
            RecordEnvironment();
            Emit(type, Object("pawns", KnownPawns().Select(p => State(p)).ToList(),
                "maps", Find.Maps.Where(m => m.IsPlayerHome).Select(m => Object("map_id", m.uniqueID,
                    "colonist_count", m.mapPawns.FreeColonistsSpawned.Count,
                    "wealth", m.wealthWatcher.WealthTotal)).ToList()));
        }

        private void RecordEnvironment()
        {
            // Hourly samples plus weather/biome changes, checked once per real-time second
            // at normal game speed. Keep each loaded map separate, including away maps.
            int hour = Find.TickManager.TicksGame / 2500;
            foreach (Map map in Find.Maps)
            {
                string signature = hour + ":" + map.Biome?.defName + ":" + map.weatherManager.curWeather?.defName;
                if (environments.TryGetValue(map.uniqueID, out string previous) && previous == signature) continue;
                Emit("map.environment", EnvironmentInfo(map), map);
                environments[map.uniqueID] = signature;
            }
        }
    }
}
