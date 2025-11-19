using System.Diagnostics;
using System.Net.Http;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace iRacingTelemetryClient;

/// <summary>
/// Represents a GitHub release asset (downloadable file)
/// </summary>
public class GitHubAsset
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("browser_download_url")]
    public string BrowserDownloadUrl { get; set; } = "";

    [JsonPropertyName("size")]
    public long Size { get; set; }
}

/// <summary>
/// Represents a GitHub release
/// </summary>
public class GitHubRelease
{
    [JsonPropertyName("tag_name")]
    public string TagName { get; set; } = "";

    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("body")]
    public string Body { get; set; } = "";

    [JsonPropertyName("html_url")]
    public string HtmlUrl { get; set; } = "";

    [JsonPropertyName("prerelease")]
    public bool Prerelease { get; set; }

    [JsonPropertyName("published_at")]
    public DateTime PublishedAt { get; set; }

    [JsonPropertyName("assets")]
    public List<GitHubAsset> Assets { get; set; } = new();
}

/// <summary>
/// Checks for application updates from GitHub Releases
/// </summary>
public class UpdateChecker
{
    private const string REPO_OWNER = "fullydoved";
    private const string REPO_NAME = "ridgway_garage";
    private readonly HttpClient _httpClient;

    public UpdateChecker()
    {
        _httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(10)
        };
        _httpClient.DefaultRequestHeaders.Add("User-Agent", "RidgwayGarageAgent");
    }

    /// <summary>
    /// Gets the current version of the application
    /// </summary>
    public Version GetCurrentVersion()
    {
        var assembly = Assembly.GetExecutingAssembly();
        return assembly.GetName().Version ?? new Version(0, 1, 0);
    }

    /// <summary>
    /// Checks if a newer version is available on GitHub
    /// </summary>
    /// <returns>The latest release if newer version available, null otherwise</returns>
    public async Task<GitHubRelease?> CheckForUpdateAsync()
    {
        try
        {
            var url = $"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest";
            var response = await _httpClient.GetAsync(url);

            if (!response.IsSuccessStatusCode)
            {
                LogManager.Log($"Failed to check for updates: HTTP {response.StatusCode}", "WARNING");
                return null;
            }

            var json = await response.Content.ReadAsStringAsync();
            var release = JsonSerializer.Deserialize<GitHubRelease>(json);

            if (release == null)
            {
                LogManager.Log("Failed to parse GitHub release data", "WARNING");
                return null;
            }

            // Skip pre-releases
            if (release.Prerelease)
            {
                LogManager.Log($"Latest release {release.TagName} is a pre-release, skipping");
                return null;
            }

            // Parse version from tag name (e.g., "v0.1.6" -> Version(0, 1, 6))
            var releaseVersion = ParseVersion(release.TagName);
            var currentVersion = GetCurrentVersion();

            LogManager.Log($"Current version: {currentVersion}, Latest version: {releaseVersion}");

            if (releaseVersion > currentVersion)
            {
                LogManager.Log($"Update available: {release.TagName}");
                return release;
            }

            LogManager.Log("Application is up to date");
            return null;
        }
        catch (HttpRequestException ex)
        {
            LogManager.Log($"Network error checking for updates: {ex.Message}", "WARNING");
            return null;
        }
        catch (Exception ex)
        {
            LogManager.Log($"Error checking for updates: {ex.Message}", "ERROR");
            return null;
        }
    }

    /// <summary>
    /// Parses a version string, handling "v" prefix (e.g., "v0.1.5" or "0.1.5")
    /// </summary>
    private Version ParseVersion(string versionString)
    {
        try
        {
            // Remove 'v' prefix if present
            versionString = versionString.TrimStart('v', 'V');

            // Parse the version
            if (Version.TryParse(versionString, out var version))
            {
                return version;
            }

            LogManager.Log($"Failed to parse version string: {versionString}", "WARNING");
            return new Version(0, 0, 0);
        }
        catch
        {
            return new Version(0, 0, 0);
        }
    }

    /// <summary>
    /// Opens the GitHub releases page in the default browser
    /// </summary>
    public void OpenReleasesPage()
    {
        try
        {
            var url = $"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases";
            Process.Start(new ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            LogManager.Log($"Failed to open releases page: {ex.Message}", "ERROR");
        }
    }

    /// <summary>
    /// Opens a specific release page in the default browser
    /// </summary>
    public void OpenReleasePage(string releaseUrl)
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = releaseUrl,
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            LogManager.Log($"Failed to open release page: {ex.Message}", "ERROR");
        }
    }
}
