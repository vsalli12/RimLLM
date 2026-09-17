using HarmonyLib;
using Verse;
using Verse.AI;

namespace RimChronicle
{
    [HarmonyPatch(typeof(Pawn_JobTracker), nameof(Pawn_JobTracker.StartJob))]
    internal static class RecordJobStarted
    {
        private static void Postfix(Pawn ___pawn)
        {
            // Read the actual current job: an attempted job may fail or start another job.
            ChronicleGameComponent.Safely(r => r.RecordJob(___pawn));
        }
    }

    [HarmonyPatch(typeof(Pawn_JobTracker), nameof(Pawn_JobTracker.EndCurrentJob))]
    internal static class RecordJobEnded
    {
        private static void Postfix(Pawn ___pawn)
        {
            // StartJob may already have recorded a replacement. The recorder deduplicates it.
            ChronicleGameComponent.Safely(r => r.RecordJob(___pawn));
        }
    }
}
