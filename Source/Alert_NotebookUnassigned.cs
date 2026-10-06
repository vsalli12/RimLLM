using System.Collections.Generic;
using RimWorld;
using Verse;

namespace RimLLM
{
    public sealed class Alert_NotebookUnassigned : Alert
    {
        public Alert_NotebookUnassigned()
        {
            defaultLabel = "Diary not assigned";
            defaultExplanation = "Select a colonist and right-click the Diary to pick it up. Whoever carries it will be the chronicler.";
            defaultPriority = AlertPriority.Medium;
        }

        public override AlertReport GetReport()
        {
            var notebooks = new List<Thing>();
            foreach (Map map in Find.Maps)
            {
                if (!map.IsPlayerHome)
                    continue;
                foreach (Thing thing in map.listerThings.ThingsOfDef(NotebookDefOf.RimLLM_Notebook))
                    if (!thing.Fogged())
                        notebooks.Add(thing);
            }
            return AlertReport.CulpritsAre(notebooks);
        }
    }
}
