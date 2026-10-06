using System.Collections.Generic;
using HarmonyLib;
using Verse;

namespace RimLLM
{
    // Temporarily exclude only notebooks while vanilla processes the rest of the inventory.
    // Finalizers restore them even if another mod throws during the original method.
    internal static class NotebookInventory
    {
        public static List<Thing> HoldAside(Pawn_InventoryTracker inventory)
        {
            List<Thing> notebooks = null;
            if (inventory == null)
                return null;

            for (int i = inventory.innerContainer.Count - 1; i >= 0; i--)
            {
                Thing thing = inventory.innerContainer[i];
                if (!(thing is Notebook))
                    continue;
                if (notebooks == null)
                    notebooks = new List<Thing>();
                notebooks.Add(thing);
                inventory.innerContainer.Remove(thing);
            }
            return notebooks;
        }

        public static void Restore(Pawn_InventoryTracker inventory, List<Thing> notebooks)
        {
            if (notebooks == null)
                return;
            foreach (Thing thing in notebooks)
                inventory.innerContainer.TryAdd(thing, false);
        }
    }

    [HarmonyPatch(typeof(Pawn), nameof(Pawn.DropAndForbidEverything))]
    internal static class KeepNotebookWhenDowned
    {
        private static void Prefix(Pawn __instance, out List<Thing> __state)
        {
            __state = __instance.Downed && !__instance.Dead
                ? NotebookInventory.HoldAside(__instance.inventory) : null;
        }

        private static void Finalizer(Pawn __instance, List<Thing> __state)
        {
            NotebookInventory.Restore(__instance.inventory, __state);
        }
    }

    [HarmonyPatch(typeof(Pawn_InventoryTracker), nameof(Pawn_InventoryTracker.FirstUnloadableThing), MethodType.Getter)]
    internal static class KeepNotebookWhenUnloading
    {
        private static void Prefix(Pawn_InventoryTracker __instance, out List<Thing> __state)
        {
            __state = NotebookInventory.HoldAside(__instance);
        }

        private static void Finalizer(Pawn_InventoryTracker __instance, List<Thing> __state)
        {
            NotebookInventory.Restore(__instance, __state);
        }
    }
}
