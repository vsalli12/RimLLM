using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using System.Threading;

namespace RimLLM
{
    internal static class EventDelivery
    {
        private static readonly ConcurrentQueue<string> Pending = new ConcurrentQueue<string>();
        internal static readonly ConcurrentQueue<string> Notices = new ConcurrentQueue<string>();
        private static bool started;
        private static int overflowReported;
        private static Thread worker;
        private static volatile bool stopping;
        private static readonly AutoResetEvent Wake = new AutoResetEvent(false);

        public static void Start(string directory)
        {
            if (started) return;
            started = true;
            worker = new Thread(() => Run(directory)) { IsBackground = true, Name = "RimLLM delivery" };
            AppDomain.CurrentDomain.ProcessExit += (sender, args) => FlushOnExit();
            worker.Start();
        }

        public static void FlushOnExit()
        {
            if (!started) return;
            stopping = true;
            Wake.Set();
            worker.Join(4000);
        }

        public static void Enqueue(string json)
        {
            // A broken disk must not consume unlimited game memory.
            if (Pending.Count >= 20000)
            {
                if (Interlocked.Exchange(ref overflowReported, 1) == 0)
                    Notices.Enqueue("Event buffer full; new events are being lost. Check free disk space and the outbox.");
                return;
            }
            Pending.Enqueue(json);
        }

        private static void Run(string directory)
        {
            var batch = new List<string>();
            bool diskErrorReported = false;
            bool offlineReported = false;
            long lastFileStamp = 0;
            while (true)
            {
                try
                {
                    Directory.CreateDirectory(directory);
                    int batchesWritten = 0;
                    do
                    {
                    if (batch.Count == 0)
                        while (batch.Count < 100 && Pending.TryDequeue(out string item)) batch.Add(item);
                    if (batch.Count > 0)
                    {
                        string id = Guid.NewGuid().ToString("N");
                        lastFileStamp = Math.Max(DateTime.UtcNow.Ticks, lastFileStamp + 1);
                        string path = Path.Combine(directory, lastFileStamp.ToString("D19") + "_" + id + ".json");
                        string body = "{\"schema_version\":1,\"batch_id\":\"" + id + "\",\"events\":[" + string.Join(",", batch) + "]}";
                        // Rename only after the complete batch has reached disk.
                        using (var file = new FileStream(path + ".tmp", FileMode.Create, FileAccess.Write, FileShare.None))
                        {
                            byte[] bytes = Encoding.UTF8.GetBytes(body);
                            file.Write(bytes, 0, bytes.Length);
                            file.Flush(true);
                        }
                        File.Move(path + ".tmp", path);
                        batch.Clear();
                    }
                    batchesWritten++;
                    } while (!Pending.IsEmpty && batchesWritten < 20);
                    diskErrorReported = false;
                    if (stopping)
                    {
                        if (Pending.IsEmpty) return;
                        continue;
                    }
                    // Drain multiple queued batches after reconnecting, without touching game objects.
                    foreach (string path in Directory.GetFiles(directory, "*.json").OrderBy(p => p).Take(20))
                    {
                        if (stopping) break;
                        try
                        {
                            string id = Path.GetFileNameWithoutExtension(path).Split('_').Last();
                            byte[] body = File.ReadAllBytes(path);
                            var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:8765/events");
                            request.Proxy = null;
                            request.Method = "POST";
                            request.ContentType = "application/json; charset=utf-8";
                            request.Timeout = 2000;
                            request.ReadWriteTimeout = 2000;
                            request.ContentLength = body.Length;
                            using (Stream stream = request.GetRequestStream()) stream.Write(body, 0, body.Length);
                            using (var response = (HttpWebResponse)request.GetResponse())
                            using (var reader = new StreamReader(response.GetResponseStream()))
                                if (response.StatusCode != HttpStatusCode.OK || reader.ReadToEnd().Trim() != id)
                                    throw new IOException("Receiver did not acknowledge the batch ID.");
                            File.Delete(path);
                            if (offlineReported) Notices.Enqueue("Local receiver connected; delivering buffered events.");
                            offlineReported = false;
                        }
                        catch (Exception ex)
                        {
                            if (!offlineReported) Notices.Enqueue("Local receiver unavailable; events are buffered in " + directory + ". " + ex.Message);
                            offlineReported = true;
                            break;
                        }
                    }
                }
                catch (Exception ex)
                {
                    if (!diskErrorReported) Notices.Enqueue("Cannot write event outbox: " + ex.Message);
                    diskErrorReported = true;
                }
                Wake.WaitOne(1000);
            }
        }
    }
}
