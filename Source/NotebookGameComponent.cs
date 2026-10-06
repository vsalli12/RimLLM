using System.Collections.Generic;
using RimWorld;
using Verse;

namespace RimLLM
{
    // One notebook per save, including when its owner travels to another map or caravan.
    public sealed class NotebookGameComponent : GameComponent
    {
        private Thing notebook;
        private int nextCheckTick;
        private readonly List<Thing> searchResults = new List<Thing>();

        public NotebookGameComponent(Game game) { }

        public Pawn Carrier
        {
            get
            {
                Pawn pawn = (notebook?.ParentHolder as Pawn_InventoryTracker)?.pawn;
                return pawn != null && !pawn.Dead ? pawn : null;
            }
        }

        public override void ExposeData()
        {
            Scribe_References.Look(ref notebook, "RimLLMNotebook");
        }

        public override void GameComponentTick()
        {
            if (Find.TickManager.TicksGame < nextCheckTick)
                return;

            nextCheckTick = Find.TickManager.TicksGame + 60;
            if (notebook != null && !notebook.Destroyed &&
                (notebook.Spawned || notebook.ParentHolder != null))
                return;

            notebook = FindExistingNotebook();
            if (notebook != null)
                return;

            // Wait for starting colonists to leave their arrival pods before placing the notebook.
            foreach (Map map in Find.Maps)
            {
                if (!map.IsPlayerHome || map.mapPawns.FreeColonistsSpawned.Count == 0)
                    continue;

                Pawn colonist = map.mapPawns.FreeColonistsSpawned[0];
                Thing created = ThingMaker.MakeThing(NotebookDefOf.RimLLM_Notebook);
                if (GenPlace.TryPlaceThing(created, colonist.Position, map, ThingPlaceMode.Near))
                {
                    notebook = created;
                    Messages.Message("A diary is waiting for a chronicler.", notebook, MessageTypeDefOf.NeutralEvent);
                }
                return;
            }
        }

        private Thing FindExistingNotebook()
        {
            foreach (Map map in Find.Maps)
            {
                // Includes inventory, corpses, shelves and containers, not just loose items.
                ThingOwnerUtility.GetAllThingsRecursively(map,
                    ThingRequest.ForDef(NotebookDefOf.RimLLM_Notebook), searchResults);
                if (searchResults.Count > 0)
                    return searchResults[0];
            }

            foreach (var worldObject in Find.WorldObjects.AllWorldObjects)
            {
                if (worldObject is IThingHolder holder)
                {
                    Thing found = FindInHolder(holder);
                    if (found != null)
                        return found;
                }
            }

            foreach (Pawn pawn in Find.WorldPawns.AllPawnsAliveOrDead)
            {
                Thing found = FindInHolder(pawn);
                if (found != null)
                    return found;
            }
            return null;
        }

        private Thing FindInHolder(IThingHolder holder)
        {
            searchResults.Clear();
            ThingOwnerUtility.GetAllThingsRecursively(holder, searchResults);
            foreach (Thing thing in searchResults)
                if (thing is Notebook && !thing.Destroyed)
                    return thing;
            return null;
        }
    }
}
