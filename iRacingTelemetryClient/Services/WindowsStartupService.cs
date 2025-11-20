using Microsoft.Win32;

namespace iRacingTelemetryClient.Services;

public static class WindowsStartupService
{
    private const string StartupRegistryKey = @"SOFTWARE\Microsoft\Windows\CurrentVersion\Run";
    private const string AppName = "RidgwayGarageAgent";

    public static void SetStartupWithWindows(bool enable)
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(StartupRegistryKey, true);
            if (key == null) return;

            if (enable)
            {
                string exePath = Application.ExecutablePath;
                key.SetValue(AppName, $"\"{exePath}\"");
                LoggingService.Log("Auto-start with Windows enabled");
            }
            else
            {
                key.DeleteValue(AppName, false);
                LoggingService.Log("Auto-start with Windows disabled");
            }
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Error setting startup registry: {ex.Message}", "ERROR");
        }
    }

    public static bool IsStartupWithWindowsEnabled()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(StartupRegistryKey, false);
            return key?.GetValue(AppName) != null;
        }
        catch
        {
            return false;
        }
    }
}
