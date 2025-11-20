namespace iRacingTelemetryClient.Services;

public static class LoggingService
{
    private static readonly object lockObj = new object();
    private static readonly List<string> logMessages = new List<string>();
    private const int MaxMessages = 1000;

    public static event Action<string>? LogAdded;

    public static void Log(string message, string level = "INFO")
    {
        var timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
        var logEntry = $"[{timestamp}] [{level}] {message}";

        lock (lockObj)
        {
            logMessages.Add(logEntry);
            if (logMessages.Count > MaxMessages)
            {
                logMessages.RemoveAt(0);
            }
        }

        LogAdded?.Invoke(logEntry);
    }

    public static string[] GetAllLogs()
    {
        lock (lockObj)
        {
            return logMessages.ToArray();
        }
    }

    public static void Clear()
    {
        lock (lockObj)
        {
            logMessages.Clear();
        }
    }
}
