using HarmonyLib;
using Verse;

namespace RimLLM
{
    public sealed class RimLLMMod : Mod
    {
        public RimLLMMod(ModContentPack content) : base(content)
        {
            new Harmony("RimLLM.RimLLM").PatchAll();
            UnityEngine.Application.quitting += EventDelivery.FlushOnExit;
            Log.Message("[RimLLM] Mod loaded successfully.");
        }
    }
}
