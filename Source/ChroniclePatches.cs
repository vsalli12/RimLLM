using HarmonyLib;
using RimWorld;
using Verse;
using Verse.AI;
using static RimLLM.ChronicleData;

namespace RimLLM
{
    [HarmonyPatch(typeof(PlayLog), nameof(PlayLog.Add))]
    internal static class RecordInteraction
    {
        private static readonly System.Reflection.FieldInfo Initiator = AccessTools.Field(typeof(PlayLogEntry_Interaction), "initiator");
        private static readonly System.Reflection.FieldInfo Recipient = AccessTools.Field(typeof(PlayLogEntry_Interaction), "recipient");
        private static readonly System.Reflection.FieldInfo Interaction = AccessTools.Field(typeof(PlayLogEntry_Interaction), "intDef");

        private static void Postfix(LogEntry entry)
        {
            if (entry is PlayLogEntry_Interaction social)
                ChronicleGameComponent.Safely(r => r.Social((Pawn)Initiator.GetValue(social),
                    (Pawn)Recipient.GetValue(social), (InteractionDef)Interaction.GetValue(social), social));
        }
    }

    [HarmonyPatch(typeof(Pawn), nameof(Pawn.Kill))]
    internal static class RecordDeath
    {
        private static void Prefix(Pawn __instance, out bool __state) { __state = __instance.Dead; }
        private static void Postfix(Pawn __instance, DamageInfo? dinfo, bool __state)
        {
            if (!__state && __instance.Dead)
                ChronicleGameComponent.Safely(r => r.PawnEvent("pawn.died", __instance, dinfo?.Instigator as Pawn,
                    Object("damage_type", dinfo?.Def?.defName), "attacker"));
        }
    }

    [HarmonyPatch(typeof(Pawn_HealthTracker), "MakeDowned")]
    internal static class RecordDowned
    {
        private static void Postfix(Pawn ___pawn, DamageInfo? dinfo)
        {
            ChronicleGameComponent.Safely(r => r.PawnEvent("pawn.downed", ___pawn, dinfo?.Instigator as Pawn, otherRole: "attacker"));
        }
    }

    [HarmonyPatch(typeof(Pawn_HealthTracker), "MakeUndowned")]
    internal static class RecordRecovered
    {
        private static void Postfix(Pawn ___pawn)
        {
            ChronicleGameComponent.Safely(r => r.PawnEvent("pawn.recovered_from_downing", ___pawn));
        }
    }

    [HarmonyPatch(typeof(MentalStateHandler), nameof(MentalStateHandler.TryStartMentalState))]
    internal static class RecordMentalBreak
    {
        private static void Postfix(Pawn ___pawn, MentalStateDef stateDef, Pawn otherPawn, string reason, bool causedByMood, bool __result)
        {
            if (__result) ChronicleGameComponent.Safely(r => r.PawnEvent("pawn.mental_state_started", ___pawn, otherPawn,
                Object("mental_state", stateDef.defName, "reason", reason, "caused_by_mood", causedByMood), "target"));
        }
    }

    [HarmonyPatch(typeof(LetterStack), nameof(LetterStack.ReceiveLetter),
        new[] { typeof(Letter), typeof(string), typeof(int), typeof(bool) })]
    internal static class RecordLetter
    {
        private static void Postfix(Letter let, int delayTicks)
        {
            if (delayTicks == 0 && Find.LetterStack.LettersListForReading.Contains(let))
                ChronicleGameComponent.Safely(r => r.Emit("colony.letter", Object("letter_id", let.ID,
                    "letter_type", let.def.defName, "label", let.Label.ToString(),
                    "text", ((IArchivable)let).ArchivedTooltip)));
        }
    }

    [HarmonyPatch(typeof(Pawn), nameof(Pawn.SetFaction))]
    internal static class RecordFactionChange
    {
        private static void Prefix(Pawn __instance, out string __state) { __state = __instance.Faction?.Name; }
        private static void Postfix(Pawn __instance, Pawn recruiter, string __state)
        {
            if (__state != __instance.Faction?.Name)
                ChronicleGameComponent.Safely(r => r.PawnEvent("pawn.faction_changed", __instance, recruiter,
                    Object("previous_faction", __state, "new_faction", __instance.Faction?.Name)));
        }
    }

    [HarmonyPatch(typeof(Pawn_HealthTracker), nameof(Pawn_HealthTracker.AddHediff),
        new[] { typeof(Hediff), typeof(BodyPartRecord), typeof(DamageInfo?), typeof(DamageWorker.DamageResult) })]
    internal static class RecordInjury
    {
        private static void Prefix(Pawn ___pawn, Hediff hediff, BodyPartRecord part, out bool __state)
        {
            __state = false;
            if (!(hediff is Hediff_Injury)) return;
            BodyPartRecord targetPart = part ?? hediff.Part;
            __state = !___pawn.health.hediffSet.hediffs.Exists(h => h.def == hediff.def && h.Part == targetPart);
        }

        private static void Postfix(Pawn ___pawn, Hediff hediff, DamageInfo? dinfo, bool __state)
        {
            if (__state && hediff.Visible)
                ChronicleGameComponent.Safely(r => r.PawnEvent("pawn.injured", ___pawn, dinfo?.Instigator as Pawn,
                    Object("injury", hediff.def.defName, "part", hediff.Part?.Label, "damage_type", dinfo?.Def?.defName), "attacker"));
        }
    }
}
