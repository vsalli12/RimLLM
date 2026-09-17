using System.Collections.Generic;
using RimWorld;
using Verse;
using Verse.AI;

namespace RimChronicle
{
    [DefOf]
    public static class NotebookDefOf
    {
        public static ThingDef RimChronicle_Notebook;

        static NotebookDefOf()
        {
            DefOfHelper.EnsureInitializedInCtor(typeof(NotebookDefOf));
        }
    }

    public sealed class Notebook : ThingWithComps
    {
        public override void PreApplyDamage(ref DamageInfo dinfo, out bool absorbed)
        {
            absorbed = true;
        }

        public override IEnumerable<FloatMenuOption> GetFloatMenuOptions(Pawn pawn)
        {
            foreach (FloatMenuOption option in base.GetFloatMenuOptions(pawn))
                yield return option;

            if (!Spawned || !pawn.IsColonistPlayerControlled || pawn.Downed || pawn.inventory == null)
                yield break;

            if (!pawn.health.capacities.CapableOf(PawnCapacityDefOf.Manipulation))
            {
                yield return new FloatMenuOption("Cannot pick up Diary: incapable of manipulation", null);
                yield break;
            }

            if (!pawn.CanReserveAndReach(this, PathEndMode.ClosestTouch, Danger.Deadly))
            {
                yield return new FloatMenuOption("Cannot pick up Diary: unreachable or reserved", null);
                yield break;
            }

            yield return new FloatMenuOption("Pick up Diary", delegate
            {
                this.SetForbidden(false);
                Job job = JobMaker.MakeJob(JobDefOf.TakeInventory, this);
                job.count = 1;
                pawn.jobs.TryTakeOrderedJob(job);
            });
        }
    }
}
