using System.Text.Json;

namespace iRacingTelemetryClient.Services;

public class UploadTracker
{
    private HashSet<string> uploadedFiles = new HashSet<string>();
    private string trackerFilePath;

    public UploadTracker()
    {
        trackerFilePath = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory,
            "uploaded_files.json"
        );
        LoadTrackedFiles();
    }

    private void LoadTrackedFiles()
    {
        try
        {
            if (File.Exists(trackerFilePath))
            {
                string json = File.ReadAllText(trackerFilePath);
                uploadedFiles = JsonSerializer.Deserialize<HashSet<string>>(json) ?? new HashSet<string>();
                LoggingService.Log($"Loaded {uploadedFiles.Count} tracked files");
            }
            else
            {
                uploadedFiles = new HashSet<string>();
            }
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Error loading tracked files: {ex.Message}", "ERROR");
            uploadedFiles = new HashSet<string>();
        }
    }

    private void SaveTrackedFiles()
    {
        try
        {
            string json = JsonSerializer.Serialize(uploadedFiles, new JsonSerializerOptions
            {
                WriteIndented = true
            });
            File.WriteAllText(trackerFilePath, json);
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Error saving tracked files: {ex.Message}", "ERROR");
        }
    }

    public bool IsUploaded(string filePath)
    {
        return uploadedFiles.Contains(filePath);
    }

    public void MarkAsUploaded(string filePath)
    {
        uploadedFiles.Add(filePath);
        SaveTrackedFiles();
    }

    public int GetUploadedCount()
    {
        return uploadedFiles.Count;
    }
}
