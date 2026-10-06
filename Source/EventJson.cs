using System;
using System.Collections;
using System.Globalization;
using System.Text;

namespace RimLLM
{
    // Only plain dictionaries, lists and scalar values cross the worker-thread boundary.
    internal static class EventJson
    {
        public static string Encode(object value)
        {
            var output = new StringBuilder();
            Write(output, value);
            return output.ToString();
        }

        private static void Write(StringBuilder output, object value)
        {
            if (value == null) { output.Append("null"); return; }
            if (value is string text)
            {
                output.Append('"');
                foreach (char c in text)
                {
                    switch (c)
                    {
                        case '"': output.Append("\\\""); break;
                        case '\\': output.Append("\\\\"); break;
                        case '\n': output.Append("\\n"); break;
                        case '\r': output.Append("\\r"); break;
                        case '\t': output.Append("\\t"); break;
                        default:
                            if (c < 32 || char.IsSurrogate(c)) output.Append("\\u" + ((int)c).ToString("x4"));
                            else output.Append(c);
                            break;
                    }
                }
                output.Append('"');
                return;
            }
            if (value is bool flag) { output.Append(flag ? "true" : "false"); return; }
            if (value is IDictionary dictionary)
            {
                output.Append('{');
                bool first = true;
                foreach (DictionaryEntry entry in dictionary)
                {
                    if (!first) output.Append(',');
                    first = false;
                    Write(output, (string)entry.Key);
                    output.Append(':');
                    Write(output, entry.Value);
                }
                output.Append('}');
                return;
            }
            if (value is IEnumerable list)
            {
                output.Append('[');
                bool first = true;
                foreach (object item in list)
                {
                    if (!first) output.Append(',');
                    first = false;
                    Write(output, item);
                }
                output.Append(']');
                return;
            }
            if (value is float f && (float.IsNaN(f) || float.IsInfinity(f)) ||
                value is double d && (double.IsNaN(d) || double.IsInfinity(d)))
            { output.Append("null"); return; }
            if (!(value is IConvertible)) throw new ArgumentException("Unsupported JSON value: " + value.GetType());
            output.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
        }
    }
}
