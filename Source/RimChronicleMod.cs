using HarmonyLib;
using Verse;

namespace RimChronicle
{
    public sealed class RimChronicleMod : Mod
    {
        public RimChronicleMod(ModContentPack content) : base(content)
        {
            new Harmony("RimChronicle.RimChronicle").PatchAll();
            UnityEngine.Application.quitting += EventDelivery.FlushOnExit;
            Log.Message("[RimChronicle] Mod loaded successfully.");
        }
    }
}
