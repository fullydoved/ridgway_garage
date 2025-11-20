using System.Text.Json;
using iRacingTelemetryClient.Models;

namespace iRacingTelemetryClient.Services;

public static class SettingsService
{
    public static AppSettings LoadSettings()
    {
        try
        {
            string settingsPath = Path.Combine(
                AppDomain.CurrentDomain.BaseDirectory,
                "appsettings.json"
            );

            string defaultSettingsPath = Path.Combine(
                AppDomain.CurrentDomain.BaseDirectory,
                "appsettings.default.json"
            );

            // First-run scenario: Create user's appsettings.json from default
            if (!File.Exists(settingsPath) && File.Exists(defaultSettingsPath))
            {
                LoggingService.Log("First run detected - creating appsettings.json from defaults");
                File.Copy(defaultSettingsPath, settingsPath);
            }

            // Load user settings
            if (File.Exists(settingsPath))
            {
                string json = File.ReadAllText(settingsPath);
                var settings = JsonSerializer.Deserialize<AppSettings>(json, new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true
                });

                if (settings != null)
                {
                    LoggingService.Log("Settings loaded successfully");
                    return settings;
                }
            }
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Error loading settings: {ex.Message}", "ERROR");
        }

        LoggingService.Log("Using hardcoded default settings");
        return new AppSettings
        {
            ServerUrl = "https://garage.mapleleafmakers.com",
            ApiToken = "",
            TelemetryFolder = ""
        };
    }

    public static void SaveSettings(AppSettings settings, string telemetryFolder)
    {
        try
        {
            settings.TelemetryFolder = telemetryFolder;

            string settingsPath = Path.Combine(
                AppDomain.CurrentDomain.BaseDirectory,
                "appsettings.json"
            );

            string json = JsonSerializer.Serialize(settings, new JsonSerializerOptions
            {
                WriteIndented = true
            });

            File.WriteAllText(settingsPath, json);
            LoggingService.Log("Settings saved");
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Error saving settings: {ex.Message}", "ERROR");
        }
    }
}
