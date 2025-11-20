using System.Diagnostics;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using Microsoft.Win32;
using iRacingTelemetryClient.Models;
using iRacingTelemetryClient.Services;
using iRacingTelemetryClient.UI.Forms;

namespace iRacingTelemetryClient;

internal static class Program
{
    [STAThread]
    static void Main()
    {
        try
        {
            // Write startup to crash log
            WriteCrashLog("Application starting...");

            // Add global exception handlers
            Application.ThreadException += Application_ThreadException;
            AppDomain.CurrentDomain.UnhandledException += CurrentDomain_UnhandledException;

            WriteCrashLog("Initializing application configuration...");
            ApplicationConfiguration.Initialize();

            WriteCrashLog("Creating main form...");
            Application.Run(new MainForm());

            WriteCrashLog("Application exited normally");
        }
        catch (Exception ex)
        {
            WriteCrashLog($"FATAL ERROR during startup: {ex.Message}\n{ex.StackTrace}");
            MessageBox.Show(
                $"Fatal error during startup:\n\n{ex.Message}\n\nCheck crash.log for details.",
                "Startup Failed",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    private static void WriteCrashLog(string message)
    {
        try
        {
            string logPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "crash.log");
            string timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
            File.AppendAllText(logPath, $"[{timestamp}] {message}\n");
        }
        catch
        {
            // If we can't even write to crash log, we're in trouble
        }
    }

    private static void Application_ThreadException(object sender, System.Threading.ThreadExceptionEventArgs e)
    {
        WriteCrashLog($"Unhandled thread exception: {e.Exception.Message}\n{e.Exception.StackTrace}");
        LoggingService.Log($"Unhandled thread exception: {e.Exception.Message}\n{e.Exception.StackTrace}", "CRITICAL");
        MessageBox.Show(
            $"A critical error occurred:\n\n{e.Exception.Message}\n\nCheck crash.log for details.",
            "Critical Error",
            MessageBoxButtons.OK,
            MessageBoxIcon.Error);
    }

    private static void CurrentDomain_UnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
        if (e.ExceptionObject is Exception ex)
        {
            WriteCrashLog($"Unhandled exception: {ex.Message}\n{ex.StackTrace}");
            LoggingService.Log($"Unhandled exception: {ex.Message}\n{ex.StackTrace}", "CRITICAL");
        }
    }
}

public class MainForm : Form
{
    private NotifyIcon? trayIcon;
    private ContextMenuStrip? trayMenu;
    private ToolStripMenuItem? menuStartMonitoring;
    private ToolStripMenuItem? menuStopMonitoring;
    private AppSettings settings;
    private FileSystemWatcher? fileWatcher;
    private UploadTracker uploadTracker;
    private HttpClient httpClient;
    private SemaphoreSlim uploadSemaphore = new SemaphoreSlim(1, 1); // Only allow one upload at a time

    private bool isMonitoring = false;
    private string telemetryFolder = "";

    public MainForm()
    {
        try
        {
            // Create hidden form
            this.WindowState = FormWindowState.Minimized;
            this.ShowInTaskbar = false;
            this.Visible = false;

            // Load settings
            settings = SettingsService.LoadSettings();
            uploadTracker = new UploadTracker();
            httpClient = new HttpClient();
            httpClient.Timeout = TimeSpan.FromMinutes(5);

            // Determine telemetry folder
            telemetryFolder = GetTelemetryFolder();

        // Create tray icon
        trayMenu = new ContextMenuStrip();
        menuStartMonitoring = new ToolStripMenuItem("Start Monitoring", null, OnStartMonitoring);
        menuStopMonitoring = new ToolStripMenuItem("Stop Monitoring", null, OnStopMonitoring) { Enabled = false };
        trayMenu.Items.Add(menuStartMonitoring);
        trayMenu.Items.Add(menuStopMonitoring);
        trayMenu.Items.Add("-");
        trayMenu.Items.Add("View Log", null, OnViewLog);
        trayMenu.Items.Add("Settings", null, OnSettings);
        trayMenu.Items.Add("-");
        trayMenu.Items.Add("Check for Updates...", null, OnCheckForUpdates);
        trayMenu.Items.Add("About", null, OnAbout);
        trayMenu.Items.Add("-");
        trayMenu.Items.Add("Exit", null, OnExit);

        // Load custom icon
        Icon? appIcon = null;
        try
        {
            string iconPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "app.ico");
            if (File.Exists(iconPath))
            {
                appIcon = new Icon(iconPath);
            }
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Could not load app icon: {ex.Message}", "WARN");
        }

        trayIcon = new NotifyIcon
        {
            Icon = appIcon ?? SystemIcons.Application,
            ContextMenuStrip = trayMenu,
            Visible = true,
            Text = "Ridgway Garage Agent - Stopped"
        };

        trayIcon.DoubleClick += OnTrayIconDoubleClick;

        // Handle form closing
        this.FormClosing += MainForm_FormClosing;

        // Handle form load - this is when we can safely start auto-monitoring
        this.Load += MainForm_Load;

        LoggingService.Log("Application started");
        LoggingService.Log($"Monitoring folder: {telemetryFolder}");
        }
        catch (Exception ex)
        {
            // Fatal error during initialization - write to crash log and show error
            File.AppendAllText(
                Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "crash.log"),
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}] FATAL ERROR in MainForm constructor: {ex.Message}\n{ex.StackTrace}\n"
            );

            MessageBox.Show(
                $"Fatal error during initialization:\n\n{ex.Message}\n\nCheck crash.log in application folder.",
                "Initialization Failed",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);

            // Exit the application
            Environment.Exit(1);
        }
    }

    private string GetTelemetryFolder()
    {
        // Try to find iRacing telemetry folder
        string documentsPath = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        string iracingPath = Path.Combine(documentsPath, "iRacing", "telemetry");

        if (Directory.Exists(iracingPath))
        {
            return iracingPath;
        }

        // Fallback to user-specified or default
        return settings.TelemetryFolder ?? iracingPath;
    }

    private void MainForm_FormClosing(object? sender, FormClosingEventArgs e)
    {
        if (isMonitoring)
        {
            var result = MessageBox.Show(
                "Monitoring is active. Stop monitoring and exit?",
                "Confirm Exit",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question);

            if (result == DialogResult.Yes)
            {
                StopMonitoring();
            }
            else
            {
                e.Cancel = true;
                return;
            }
        }

        trayIcon?.Dispose();
        httpClient?.Dispose();
    }

    private void MainForm_Load(object? sender, EventArgs e)
    {
        // Auto-start monitoring if auto-upload is enabled and settings are valid
        if (settings.AutoUpload)
        {
            LoggingService.Log("Auto-upload enabled");

            // Check if we have the required settings before auto-starting
            if (Directory.Exists(telemetryFolder) && !string.IsNullOrEmpty(settings.ApiToken))
            {
                LoggingService.Log("Starting monitoring automatically");
                // Start monitoring on next message loop iteration
                BeginInvoke(() =>
                {
                    try
                    {
                        OnStartMonitoring(null, EventArgs.Empty);
                    }
                    catch (Exception ex)
                    {
                        LoggingService.Log($"Error during auto-start: {ex.Message}", "ERROR");
                    }
                });
            }
            else
            {
                LoggingService.Log("Cannot auto-start: Missing API token or invalid telemetry folder", "WARN");
                trayIcon!.ShowBalloonTip(3000, "Configuration Required",
                    "Please configure your API token and telemetry folder in Settings.",
                    ToolTipIcon.Warning);
            }
        }
        else
        {
            // Show balloon tip on startup
            trayIcon!.ShowBalloonTip(3000, "Ridgway Garage Agent",
                "Agent is ready. Right-click icon to start monitoring.",
                ToolTipIcon.Info);
        }
    }

    private void OnTrayIconDoubleClick(object? sender, EventArgs e)
    {
        ShowStatusWindow();
    }

    private void ShowStatusWindow()
    {
        var status = new StatusForm(isMonitoring, settings, telemetryFolder, uploadTracker.GetUploadedCount());
        status.ShowDialog();
    }

    private async void OnStartMonitoring(object? sender, EventArgs e)
    {
        if (isMonitoring) return;

        try
        {
            LoggingService.Log("Starting file monitoring...");

            // Verify telemetry folder exists
            if (!Directory.Exists(telemetryFolder))
            {
                LoggingService.Log($"Telemetry folder not found: {telemetryFolder}", "ERROR");
                MessageBox.Show(
                    $"Telemetry folder not found:\n{telemetryFolder}\n\nPlease check Settings.",
                    "Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return;
            }

            // Verify API token
            if (string.IsNullOrEmpty(settings.ApiToken))
            {
                LoggingService.Log("API token not configured", "ERROR");
                MessageBox.Show(
                    "API token not configured. Please set your API token in Settings.",
                    "Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return;
            }

            // Check if auto-upload is enabled
            if (!settings.AutoUpload)
            {
                LoggingService.Log("Auto-upload is disabled in settings", "WARN");
                MessageBox.Show(
                    "Auto-upload is currently disabled in Settings.\n\nFiles will be detected but not uploaded.",
                    "Auto-Upload Disabled",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
            }

            // Start file watcher
            fileWatcher = new FileSystemWatcher(telemetryFolder)
            {
                Filter = "*.ibt",
                NotifyFilter = NotifyFilters.FileName | NotifyFilters.LastWrite | NotifyFilters.CreationTime,
                EnableRaisingEvents = true
            };

            fileWatcher.Created += OnFileCreated;
            fileWatcher.Changed += OnFileChanged;

            isMonitoring = true;
            menuStartMonitoring!.Enabled = false;
            menuStopMonitoring!.Enabled = true;
            trayIcon!.Text = "Ridgway Garage Agent - Monitoring";
            trayIcon.ShowBalloonTip(2000, "Monitoring Started",
                $"Watching for new telemetry files",
                ToolTipIcon.Info);

            LoggingService.Log("File monitoring started");

            // Check for existing files that haven't been uploaded
            ScanExistingFiles();
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Error starting monitoring: {ex.Message}", "ERROR");
            MessageBox.Show($"Error starting monitoring:\n{ex.Message}", "Error",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void OnStopMonitoring(object? sender, EventArgs e)
    {
        StopMonitoring();
    }

    private void StopMonitoring()
    {
        if (!isMonitoring) return;

        LoggingService.Log("Stopping file monitoring...");

        if (fileWatcher != null)
        {
            fileWatcher.EnableRaisingEvents = false;
            fileWatcher.Dispose();
            fileWatcher = null;
        }

        isMonitoring = false;
        menuStartMonitoring!.Enabled = true;
        menuStopMonitoring!.Enabled = false;
        trayIcon!.Text = "Ridgway Garage Agent - Stopped";
        trayIcon.ShowBalloonTip(2000, "Monitoring Stopped", "File monitoring has been stopped.", ToolTipIcon.Info);

        LoggingService.Log("File monitoring stopped");
    }

    private void ScanExistingFiles()
    {
        try
        {
            LoggingService.Log("Scanning for existing telemetry files...");
            var files = Directory.GetFiles(telemetryFolder, "*.ibt");

            int newFiles = 0;
            foreach (var file in files)
            {
                if (!uploadTracker.IsUploaded(file))
                {
                    newFiles++;
                    LoggingService.Log($"Found unuploaded file: {Path.GetFileName(file)}");
                    // Don't show notifications during backfill scan (showNotification: false)
                    _ = Task.Run(() => UploadFile(file, showNotification: false));
                }
            }

            if (newFiles == 0)
            {
                LoggingService.Log("No new files to upload");
            }
            else
            {
                LoggingService.Log($"Found {newFiles} file(s) to upload");
            }
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Error scanning files: {ex.Message}", "ERROR");
        }
    }

    private void OnFileCreated(object sender, FileSystemEventArgs e)
    {
        LoggingService.Log($"New file detected: {e.Name}");
        _ = Task.Run(() => UploadFileWithDelay(e.FullPath));
    }

    private void OnFileChanged(object sender, FileSystemEventArgs e)
    {
        // If file hasn't been uploaded yet, retry the upload
        // This handles cases where the file was locked during initial upload attempt
        if (!uploadTracker.IsUploaded(e.FullPath))
        {
            LoggingService.Log($"File changed and not yet uploaded, retrying: {Path.GetFileName(e.FullPath)}");
            _ = Task.Run(() => UploadFileWithDelay(e.FullPath));
        }
    }

    private async Task UploadFileWithDelay(string filePath)
    {
        // Wait a bit to ensure iRacing has finished writing the file
        await Task.Delay(5000);
        await UploadFile(filePath);
    }

    private async Task UploadFile(string filePath, bool showNotification = true)
    {
        // Check if auto-upload is enabled
        if (!settings.AutoUpload)
        {
            LoggingService.Log($"Auto-upload disabled, skipping: {Path.GetFileName(filePath)}");
            return;
        }

        // Check if already uploaded
        if (uploadTracker.IsUploaded(filePath))
        {
            LoggingService.Log($"File already uploaded: {Path.GetFileName(filePath)}");
            return;
        }

        // Check if file exists and is accessible
        if (!File.Exists(filePath))
        {
            LoggingService.Log($"File not found: {Path.GetFileName(filePath)}", "ERROR");
            return;
        }

        // Wait for semaphore to ensure only one upload at a time
        await uploadSemaphore.WaitAsync();

        try
        {
            // Check again if already uploaded (in case another task uploaded while we were waiting)
            if (uploadTracker.IsUploaded(filePath))
            {
                LoggingService.Log($"File already uploaded by another task: {Path.GetFileName(filePath)}");
                return;
            }

            // Wait for file to be fully written and not locked
            // iRacing can take several minutes to finish writing large IBT files (100MB+)
            int maxRetries = 120;
            int retries = 0;
            long previousFileSize = 0;
            int stableChecks = 0;
            const int requiredStableChecks = 2; // File size must be stable for 2 checks

            while (retries < maxRetries)
            {
                try
                {
                    // Try to open file with ReadWrite share mode to allow iRacing to continue writing
                    using (var fs = File.Open(filePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                    {
                        long currentFileSize = fs.Length;

                        // Check if file size is stable (hasn't changed since last check)
                        if (currentFileSize == previousFileSize && previousFileSize > 0)
                        {
                            stableChecks++;
                            if (stableChecks >= requiredStableChecks)
                            {
                                LoggingService.Log($"File ready for upload: {Path.GetFileName(filePath)} ({currentFileSize / (1024.0 * 1024.0):F2} MB)");
                                break; // File is accessible and size is stable
                            }
                        }
                        else
                        {
                            stableChecks = 0; // Reset stability counter
                        }

                        previousFileSize = currentFileSize;
                    }
                }
                catch (IOException)
                {
                    if (retries == 0)
                    {
                        LoggingService.Log($"Waiting for iRacing to finish writing: {Path.GetFileName(filePath)}");
                    }
                }

                retries++;
                if (retries >= maxRetries)
                {
                    LoggingService.Log($"File still being written after {maxRetries} attempts (4 minutes): {Path.GetFileName(filePath)}", "WARNING");
                    LoggingService.Log($"Will retry upload when file finishes writing (on file system change event)", "INFO");
                    return; // Don't throw - exit gracefully, OnFileChanged will retry
                }

                // Exponential backoff: start at 1 second, increase to max 5 seconds
                int delayMs = Math.Min(1000 + (retries * 100), 5000);
                await Task.Delay(delayMs);
            }

            var fileInfo = new FileInfo(filePath);
            var fileSizeMB = fileInfo.Length / (1024.0 * 1024.0);
            var uploadUrl = settings.ServerUrl.TrimEnd('/') + "/api/upload/";

            // Compress the file before uploading
            var compressedStream = new MemoryStream();
            using (var fileStream = File.OpenRead(filePath))
            using (var gzipStream = new GZipStream(compressedStream, CompressionMode.Compress, leaveOpen: true))
            {
                await fileStream.CopyToAsync(gzipStream);
            }
            compressedStream.Position = 0;  // Reset for reading

            var compressedSizeMB = compressedStream.Length / (1024.0 * 1024.0);
            var compressionRatio = (1 - (compressedStream.Length / (double)fileInfo.Length)) * 100;

            LoggingService.Log($"Uploading: {Path.GetFileName(filePath)} " +
                          $"({fileSizeMB:F2} MB → {compressedSizeMB:F2} MB compressed, " +
                          $"{compressionRatio:F1}% reduction) to {uploadUrl}");

            using var form = new MultipartFormDataContent();
            using var fileContent = new StreamContent(compressedStream);

            fileContent.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream");
            form.Add(fileContent, "file", Path.GetFileName(filePath));

            // Add API token as header
            httpClient.DefaultRequestHeaders.Clear();
            httpClient.DefaultRequestHeaders.Add("Authorization", $"Token {settings.ApiToken}");

            // Add original file modification time as header (ISO 8601 format)
            var fileModTime = fileInfo.LastWriteTimeUtc.ToString("o");
            httpClient.DefaultRequestHeaders.Add("X-Original-Mtime", fileModTime);

            LoggingService.Log($"Sending POST request to {uploadUrl}...");

            var response = await httpClient.PostAsync(uploadUrl, form);

            LoggingService.Log($"Received response: {response.StatusCode}");

            if (response.IsSuccessStatusCode)
            {
                uploadTracker.MarkAsUploaded(filePath);
                LoggingService.Log($"Successfully uploaded: {Path.GetFileName(filePath)}");

                if (showNotification)
                {
                    BeginInvoke(() =>
                    {
                        trayIcon?.ShowBalloonTip(3000, "Upload Complete",
                            $"Uploaded: {Path.GetFileName(filePath)}",
                            ToolTipIcon.Info);
                    });
                }
            }
            else
            {
                var errorContent = await response.Content.ReadAsStringAsync();
                LoggingService.Log($"Upload failed ({response.StatusCode}): {Path.GetFileName(filePath)} - {errorContent}", "ERROR");

                if (showNotification)
                {
                    BeginInvoke(() =>
                    {
                        trayIcon?.ShowBalloonTip(5000, "Upload Failed",
                            $"Failed to upload: {Path.GetFileName(filePath)}\n{response.StatusCode}",
                            ToolTipIcon.Error);
                    });
                }
            }
        }
        catch (TaskCanceledException ex)
        {
            LoggingService.Log($"Upload timeout for {Path.GetFileName(filePath)}: {ex.Message}", "ERROR");
        }
        catch (HttpRequestException ex)
        {
            LoggingService.Log($"Network error uploading {Path.GetFileName(filePath)}: {ex.Message}", "ERROR");
            if (ex.InnerException != null)
            {
                LoggingService.Log($"  Inner exception: {ex.InnerException.Message}", "ERROR");
            }
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Unexpected error uploading {Path.GetFileName(filePath)}: {ex.GetType().Name} - {ex.Message}", "ERROR");
            LoggingService.Log($"  Stack trace: {ex.StackTrace}", "ERROR");
        }
        finally
        {
            // Always release the semaphore
            uploadSemaphore.Release();
        }
    }

    private void OnViewLog(object? sender, EventArgs e)
    {
        var logForm = new LogForm();
        logForm.Show();
    }

    private void OnSettings(object? sender, EventArgs e)
    {
        var settingsForm = new SettingsForm(settings, telemetryFolder);
        if (settingsForm.ShowDialog() == DialogResult.OK)
        {
            settings = settingsForm.GetSettings();
            telemetryFolder = settingsForm.GetTelemetryFolder();
            SettingsService.SaveSettings(settings, telemetryFolder);
            LoggingService.Log("Settings updated");
            LoggingService.Log($"Monitoring folder: {telemetryFolder}");
        }
    }

    private async void OnCheckForUpdates(object? sender, EventArgs e)
    {
        try
        {
            LoggingService.Log("Checking for updates...");

            var checker = new UpdateChecker();
            var currentVersion = checker.GetCurrentVersion();

            // Show checking message
            var checkingForm = new Form
            {
                Text = "Checking for Updates",
                Size = new Size(400, 150),
                StartPosition = FormStartPosition.CenterScreen,
                FormBorderStyle = FormBorderStyle.FixedDialog,
                MaximizeBox = false,
                MinimizeBox = false
            };

            var lblChecking = new Label
            {
                Text = "Checking for updates...",
                Location = new Point(20, 40),
                Size = new Size(360, 30),
                Font = new Font("Segoe UI", 10),
                TextAlign = ContentAlignment.MiddleCenter
            };
            checkingForm.Controls.Add(lblChecking);

            // Show form and check for updates asynchronously
            checkingForm.Show();

            var release = await checker.CheckForUpdateAsync();

            checkingForm.Close();
            checkingForm.Dispose();

            if (release == null)
            {
                // No update available
                MessageBox.Show(
                    $"You are running the latest version ({currentVersion}).",
                    "No Updates Available",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return;
            }

            // Update available - show update dialog
            ShowUpdateDialog(release, currentVersion);
        }
        catch (Exception ex)
        {
            LoggingService.Log($"Error checking for updates: {ex.Message}", "ERROR");
            MessageBox.Show(
                $"Failed to check for updates: {ex.Message}",
                "Update Check Failed",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    private void ShowUpdateDialog(GitHubRelease release, Version currentVersion)
    {
        var updateForm = new Form
        {
            Text = "Update Available",
            Size = new Size(500, 400),
            StartPosition = FormStartPosition.CenterScreen,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            MaximizeBox = false,
            MinimizeBox = false
        };

        // Title label
        var lblTitle = new Label
        {
            Text = $"A new version of Ridgway Garage Agent is available!",
            Location = new Point(20, 20),
            Size = new Size(460, 25),
            Font = new Font("Segoe UI", 10, FontStyle.Bold)
        };
        updateForm.Controls.Add(lblTitle);

        // Version info
        var lblVersionInfo = new Label
        {
            Text = $"Current version: {currentVersion}\nNew version: {release.TagName}",
            Location = new Point(20, 55),
            Size = new Size(460, 40),
            Font = new Font("Segoe UI", 9)
        };
        updateForm.Controls.Add(lblVersionInfo);

        // Release notes label
        var lblReleaseNotes = new Label
        {
            Text = "Release Notes:",
            Location = new Point(20, 105),
            Size = new Size(460, 20),
            Font = new Font("Segoe UI", 9, FontStyle.Bold)
        };
        updateForm.Controls.Add(lblReleaseNotes);

        // Release notes text box
        var txtReleaseNotes = new TextBox
        {
            Text = release.Body,
            Location = new Point(20, 130),
            Size = new Size(460, 180),
            Multiline = true,
            ReadOnly = true,
            ScrollBars = ScrollBars.Vertical,
            Font = new Font("Segoe UI", 9)
        };
        updateForm.Controls.Add(txtReleaseNotes);

        // Buttons
        var btnDownload = new Button
        {
            Text = "Download Update",
            Location = new Point(20, 325),
            Size = new Size(140, 30),
            Font = new Font("Segoe UI", 9)
        };
        btnDownload.Click += async (s, e) =>
        {
            var checker = new UpdateChecker();
            var zipAsset = checker.FindReleaseZip(release);

            if (zipAsset == null)
            {
                MessageBox.Show("No download file found in this release.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            // Show save file dialog
            var saveDialog = new SaveFileDialog
            {
                FileName = zipAsset.Name,
                Filter = "ZIP files (*.zip)|*.zip|All files (*.*)|*.*",
                InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) + "\\Downloads",
                Title = "Save Update File"
            };

            if (saveDialog.ShowDialog() == DialogResult.OK)
            {
                updateForm.Close();

                // Show progress form
                var progressForm = new DownloadProgressForm(zipAsset.Name);
                progressForm.Show();

                var progress = new Progress<DownloadProgress>(p => progressForm.UpdateProgress(p));

                // Download the file
                var success = await checker.DownloadReleaseAsync(zipAsset.BrowserDownloadUrl, saveDialog.FileName, progress);

                progressForm.Close();

                if (success)
                {
                    var result = MessageBox.Show(
                        $"Update downloaded successfully!\n\nFile saved to:\n{saveDialog.FileName}\n\nWould you like to open the download folder?",
                        "Download Complete",
                        MessageBoxButtons.YesNo,
                        MessageBoxIcon.Information);

                    if (result == DialogResult.Yes)
                    {
                        Process.Start("explorer.exe", $"/select,\"{saveDialog.FileName}\"");
                    }
                }
                else
                {
                    MessageBox.Show("Download failed. Please check the log for details.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
        };
        updateForm.Controls.Add(btnDownload);

        var btnLater = new Button
        {
            Text = "Remind Me Later",
            Location = new Point(170, 325),
            Size = new Size(140, 30),
            Font = new Font("Segoe UI", 9)
        };
        btnLater.Click += (s, e) => updateForm.Close();
        updateForm.Controls.Add(btnLater);

        var btnClose = new Button
        {
            Text = "Close",
            Location = new Point(320, 325),
            Size = new Size(160, 30),
            Font = new Font("Segoe UI", 9)
        };
        btnClose.Click += (s, e) => updateForm.Close();
        updateForm.Controls.Add(btnClose);

        updateForm.ShowDialog();
    }

    private void OnAbout(object? sender, EventArgs e)
    {
        var checker = new UpdateChecker();
        var currentVersion = checker.GetCurrentVersion();

        var aboutForm = new Form
        {
            Text = "About Ridgway Garage Agent",
            Size = new Size(400, 250),
            StartPosition = FormStartPosition.CenterScreen,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            MaximizeBox = false,
            MinimizeBox = false
        };

        var lblAppName = new Label
        {
            Text = "Ridgway Garage Agent",
            Location = new Point(20, 20),
            Size = new Size(360, 30),
            Font = new Font("Segoe UI", 14, FontStyle.Bold),
            TextAlign = ContentAlignment.MiddleCenter
        };
        aboutForm.Controls.Add(lblAppName);

        var lblVersion = new Label
        {
            Text = $"Version {currentVersion}",
            Location = new Point(20, 55),
            Size = new Size(360, 25),
            Font = new Font("Segoe UI", 10),
            TextAlign = ContentAlignment.MiddleCenter
        };
        aboutForm.Controls.Add(lblVersion);

        var lblDescription = new Label
        {
            Text = "Automatically monitors and uploads iRacing telemetry files\nto the Ridgway Garage telemetry analysis platform.",
            Location = new Point(20, 90),
            Size = new Size(360, 50),
            Font = new Font("Segoe UI", 9),
            TextAlign = ContentAlignment.MiddleCenter
        };
        aboutForm.Controls.Add(lblDescription);

        var lblCopyright = new Label
        {
            Text = "© 2025 Ridgway Garage",
            Location = new Point(20, 150),
            Size = new Size(360, 20),
            Font = new Font("Segoe UI", 8),
            TextAlign = ContentAlignment.MiddleCenter,
            ForeColor = Color.Gray
        };
        aboutForm.Controls.Add(lblCopyright);

        var btnClose = new Button
        {
            Text = "Close",
            Location = new Point(150, 175),
            Size = new Size(100, 30),
            Font = new Font("Segoe UI", 9)
        };
        btnClose.Click += (s, e) => aboutForm.Close();
        aboutForm.Controls.Add(btnClose);

        aboutForm.ShowDialog();
    }

    private void OnExit(object? sender, EventArgs e)
    {
        Application.Exit();
    }

}



