using System.Collections.Generic;
using System.Linq;
using RimWorld;
using RimWorld.Planet;
using Verse;

namespace RimLLM
{
    internal static class ChronicleData
    {
        public static Dictionary<string, object> Object(params object[] pairs)
        {
            var result = new Dictionary<string, object>();
            for (int i = 0; i < pairs.Length; i += 2) result[(string)pairs[i]] = pairs[i + 1];
            return result;
        }

        public static bool Visible(Pawn pawn)
        {
            return pawn != null && (pawn.Faction == Faction.OfPlayer ||
                (pawn.MapHeld != null && pawn.SpawnedOrAnyParentSpawned && !pawn.PositionHeld.Fogged(pawn.MapHeld)));
        }

        public static object ScenarioInfo()
        {
            var scenario = Find.Scenario;
            return scenario == null ? null : Object("name", scenario.name,
                "summary", scenario.summary, "description", scenario.description,
                "full_information", scenario.GetFullInformationText());
        }

        public static object EnvironmentInfo(Map map)
        {
            return Object("biome", map.Biome?.defName, "biome_label", map.Biome?.label,
                "weather", map.weatherManager.curWeather?.defName,
                "weather_label", map.weatherManager.curWeather?.label,
                "outdoor_temperature_c", map.mapTemperature.OutdoorTemp);
        }

        public static object Profile(Pawn pawn)
        {
            return Object("pawn_id", pawn.GetUniqueLoadID(), "name", pawn.LabelShort,
                "gender", pawn.gender.ToString(), "species", pawn.def.label,
                "age_biological", pawn.ageTracker.AgeBiologicalYears,
                "age_chronological", pawn.ageTracker.AgeChronologicalYears,
                "faction", pawn.Faction?.Name, "is_colonist", pawn.IsColonist,
                "is_humanlike", pawn.RaceProps.Humanlike, "is_animal", pawn.RaceProps.Animal,
                "hostile_to_player", pawn.HostileTo(Faction.OfPlayer),
                "is_colony_animal", pawn.RaceProps.Animal && pawn.Faction == Faction.OfPlayer,
                "dead", pawn.Dead, "spawned", pawn.Spawned, "map_id", pawn.MapHeld?.uniqueID,
                "in_caravan", pawn.GetCaravan() != null,
                "is_prisoner", pawn.IsPrisonerOfColony, "is_slave", pawn.IsSlaveOfColony,
                "childhood", pawn.story?.Childhood?.title,
                "adulthood", pawn.story?.Adulthood?.title,
                "traits", pawn.story?.traits.allTraits.Select(t => Object("def", t.def.defName, "label", t.Label, "degree", t.Degree, "suppressed", t.Suppressed)).ToList(),
                "skills", pawn.skills?.skills.Select(s => Object("def", s.def.defName, "level", s.Level, "passion", s.passion.ToString())).ToList(),
                "relationships", Relationships(pawn));
        }

        public static object Relationships(Pawn pawn)
        {
            return pawn.relations?.DirectRelations.Select(r => Object("type", r.def.defName,
                "pawn_id", r.otherPawn.GetUniqueLoadID(), "name", r.otherPawn.LabelShort)).ToList();
        }

        public static object State(Pawn pawn)
        {
            var thoughts = new List<Thought>();
            if (!pawn.Dead) pawn.needs?.mood?.thoughts.GetAllMoodThoughts(thoughts);
            return Object("pawn_id", pawn.GetUniqueLoadID(), "dead", pawn.Dead, "downed", pawn.Downed,
                "current_job", JobState(pawn),
                "is_prisoner", pawn.IsPrisonerOfColony, "is_slave", pawn.IsSlaveOfColony,
                "map_id", pawn.MapHeld?.uniqueID, "mood", pawn.needs?.mood?.CurLevel,
                "mental_state", pawn.MentalStateDef?.defName,
                "mood_contributors", thoughts.Where(t => t.VisibleInNeedsTab).Select(t => Object("def", t.def.defName,
                    "label", t.LabelCap.ToString(), "mood_offset", t.MoodOffset())).ToList(),
                "health", pawn.health.hediffSet.hediffs.Where(h => h.Visible).Select(h => Object("def", h.def.defName,
                    "label", h.LabelCap.ToString(), "severity", h.Severity, "part", h.Part?.Label)).ToList(),
                "relationships", Relationships(pawn));
        }

        public static List<Pawn> KnownPawns()
        {
            return Find.Maps.SelectMany(m => m.mapPawns.AllPawnsSpawned)
                .Concat(Find.WorldPawns.AllPawnsAlive.Where(p => p.Faction == Faction.OfPlayer &&
                    (p.MapHeld != null || p.GetCaravan() != null)))
                .Where(p => !p.Dead && (p.RaceProps.Humanlike ||
                    (p.RaceProps.Animal && p.Faction == Faction.OfPlayer)) && Visible(p)).Distinct().ToList();
        }

        public static object JobState(Pawn pawn)
        {
            var job = pawn.CurJob;
            if (job == null) return null;
            return Object("job_id", job.GetUniqueLoadID(), "def", job.def.defName,
                "player_forced", job.playerForced, "start_tick", job.startTick,
                "target_a", JobTarget(job.targetA, pawn.MapHeld),
                "target_b", JobTarget(job.targetB, pawn.MapHeld),
                "target_c", JobTarget(job.targetC, pawn.MapHeld));
        }

        private static object JobTarget(LocalTargetInfo target, Map map)
        {
            if (!target.IsValid) return null;
            Thing thing = target.Thing;
            if (thing != null)
            {
                if (thing.MapHeld == null || !thing.PositionHeld.InBounds(thing.MapHeld) ||
                    thing.PositionHeld.Fogged(thing.MapHeld))
                    return Object("kind", "unobserved");
                return Object("kind", thing is Pawn ? "pawn" : "thing", "thing_id", thing.GetUniqueLoadID(),
                    "def", thing.def.defName, "label", thing.LabelShort,
                    "map_id", thing.MapHeld.uniqueID);
            }
            return Object("kind", "cell", "map_id", map?.uniqueID, "x", target.Cell.x, "z", target.Cell.z);
        }
    }
}
