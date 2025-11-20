namespace iRacingTelemetryClient.Models;

public class AppSettings
{
    public string ServerUrl { get; set; } = "https://garage.mapleleafmakers.com";
    public string ApiToken { get; set; } = "";
    public string? TelemetryFolder { get; set; }
    public bool AutoUpload { get; set; } = true;
    public bool StartWithWindows { get; set; } = false;
}
