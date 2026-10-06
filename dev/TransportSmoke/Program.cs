using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Threading;
using RimLLM;

internal static class Program
{
    private static void Main(string[] args)
    {
        CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("fi-FI");
        var sample = new Dictionary<string, object>
        {
            ["schema_version"] = 1, ["event_id"] = "transport-event", ["playthrough_id"] = "transport-colony",
            ["session_id"] = "transport-session", ["sequence"] = 1, ["type"] = "transport.test",
            ["diary_carrier_id"] = null,
            ["data"] = new Dictionary<string, object>
            {
                ["name"] = "Ääni \"Diary\"\n雪😀", ["number"] = 1.25,
                ["values"] = new object[] { true, null, 3, "\\" }
            }
        };
        EventDelivery.Start(args[0]);
        if (args.Length == 1) EventDelivery.Enqueue(EventJson.Encode(sample));
        WaitFor(() => Directory.Exists(args[0]) && Directory.GetFiles(args[0], "*.json").Length > 0,
            "Event did not reach the offline outbox");
        Console.WriteLine("BUFFERED");
        Console.ReadLine(); // The test starts the receiver only after confirming offline persistence.
        WaitFor(() => Directory.GetFiles(args[0], "*.json").Length == 0, "Outbox was not acknowledged");
        Console.WriteLine("DELIVERED");
    }

    private static void WaitFor(Func<bool> condition, string error)
    {
        for (int i = 0; i < 200; i++)
        {
            if (condition()) return;
            Thread.Sleep(100);
        }
        throw new Exception(error);
    }
}
