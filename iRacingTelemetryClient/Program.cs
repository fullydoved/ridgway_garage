using System.Text;
using System.Text.Json;

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
        LogManager.Log($"Unhandled thread exception: {e.Exception.Message}\n{e.Exception.StackTrace}", "CRITICAL");
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
            LogManager.Log($"Unhandled exception: {ex.Message}\n{ex.StackTrace}", "CRITICAL");
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
            settings = LoadSettings();
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
            LogManager.Log($"Could not load app icon: {ex.Message}", "WARN");
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

        LogManager.Log("Application started");
        LogManager.Log($"Monitoring folder: {telemetryFolder}");
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
            LogManager.Log("Auto-upload enabled");

            // Check if we have the required settings before auto-starting
            if (Directory.Exists(telemetryFolder) && !string.IsNullOrEmpty(settings.ApiToken))
            {
                LogManager.Log("Starting monitoring automatically");
                // Start monitoring on next message loop iteration
                BeginInvoke(() =>
                {
                    try
                    {
                        OnStartMonitoring(null, EventArgs.Empty);
                    }
                    catch (Exception ex)
                    {
                        LogManager.Log($"Error during auto-start: {ex.Message}", "ERROR");
                    }
                });
            }
            else
            {
                LogManager.Log("Cannot auto-start: Missing API token or invalid telemetry folder", "WARN");
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
            LogManager.Log("Starting file monitoring...");

            // Verify telemetry folder exists
            if (!Directory.Exists(telemetryFolder))
            {
                LogManager.Log($"Telemetry folder not found: {telemetryFolder}", "ERROR");
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
                LogManager.Log("API token not configured", "ERROR");
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
                LogManager.Log("Auto-upload is disabled in settings", "WARN");
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

            LogManager.Log("File monitoring started");

            // Check for existing files that haven't been uploaded
            await ScanExistingFiles();
        }
        catch (Exception ex)
        {
            LogManager.Log($"Error starting monitoring: {ex.Message}", "ERROR");
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

        LogManager.Log("Stopping file monitoring...");

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

        LogManager.Log("File monitoring stopped");
    }

    private async Task ScanExistingFiles()
    {
        try
        {
            LogManager.Log("Scanning for existing telemetry files...");
            var files = Directory.GetFiles(telemetryFolder, "*.ibt");

            int newFiles = 0;
            foreach (var file in files)
            {
                if (!uploadTracker.IsUploaded(file))
                {
                    newFiles++;
                    LogManager.Log($"Found unuploaded file: {Path.GetFileName(file)}");
                    _ = Task.Run(() => UploadFile(file));
                }
            }

            if (newFiles == 0)
            {
                LogManager.Log("No new files to upload");
            }
            else
            {
                LogManager.Log($"Found {newFiles} file(s) to upload");
            }
        }
        catch (Exception ex)
        {
            LogManager.Log($"Error scanning files: {ex.Message}", "ERROR");
        }
    }

    private void OnFileCreated(object sender, FileSystemEventArgs e)
    {
        LogManager.Log($"New file detected: {e.Name}");
        _ = Task.Run(() => UploadFileWithDelay(e.FullPath));
    }

    private void OnFileChanged(object sender, FileSystemEventArgs e)
    {
        // If file hasn't been uploaded yet, retry the upload
        // This handles cases where the file was locked during initial upload attempt
        if (!uploadTracker.IsUploaded(e.FullPath))
        {
            LogManager.Log($"File changed and not yet uploaded, retrying: {Path.GetFileName(e.FullPath)}");
            _ = Task.Run(() => UploadFileWithDelay(e.FullPath));
        }
    }

    private async Task UploadFileWithDelay(string filePath)
    {
        // Wait a bit to ensure iRacing has finished writing the file
        await Task.Delay(5000);
        await UploadFile(filePath);
    }

    private async Task UploadFile(string filePath)
    {
        // Check if auto-upload is enabled
        if (!settings.AutoUpload)
        {
            LogManager.Log($"Auto-upload disabled, skipping: {Path.GetFileName(filePath)}");
            return;
        }

        // Check if already uploaded
        if (uploadTracker.IsUploaded(filePath))
        {
            LogManager.Log($"File already uploaded: {Path.GetFileName(filePath)}");
            return;
        }

        // Check if file exists and is accessible
        if (!File.Exists(filePath))
        {
            LogManager.Log($"File not found: {Path.GetFileName(filePath)}", "ERROR");
            return;
        }

        // Wait for semaphore to ensure only one upload at a time
        await uploadSemaphore.WaitAsync();

        try
        {
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
                                LogManager.Log($"File ready for upload: {Path.GetFileName(filePath)} ({currentFileSize / (1024.0 * 1024.0):F2} MB)");
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
                catch (IOException ex)
                {
                    if (retries == 0)
                    {
                        LogManager.Log($"Waiting for iRacing to finish writing: {Path.GetFileName(filePath)}");
                    }
                }

                retries++;
                if (retries >= maxRetries)
                {
                    LogManager.Log($"File still being written after {maxRetries} attempts (4 minutes): {Path.GetFileName(filePath)}", "WARNING");
                    LogManager.Log($"Will retry upload when file finishes writing (on file system change event)", "INFO");
                    return; // Don't throw - exit gracefully, OnFileChanged will retry
                }

                // Exponential backoff: start at 1 second, increase to max 5 seconds
                int delayMs = Math.Min(1000 + (retries * 100), 5000);
                await Task.Delay(delayMs);
            }

            var fileInfo = new FileInfo(filePath);
            var fileSizeMB = fileInfo.Length / (1024.0 * 1024.0);
            var uploadUrl = settings.ServerUrl.TrimEnd('/') + "/api/upload/";

            LogManager.Log($"Uploading: {Path.GetFileName(filePath)} ({fileSizeMB:F2} MB) to {uploadUrl}");

            using var form = new MultipartFormDataContent();
            using var fileStream = File.OpenRead(filePath);
            using var fileContent = new StreamContent(fileStream);

            fileContent.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream");
            form.Add(fileContent, "file", Path.GetFileName(filePath));

            // Add API token as header
            httpClient.DefaultRequestHeaders.Clear();
            httpClient.DefaultRequestHeaders.Add("Authorization", $"Token {settings.ApiToken}");

            LogManager.Log($"Sending POST request to {uploadUrl}...");

            var response = await httpClient.PostAsync(uploadUrl, form);

            LogManager.Log($"Received response: {response.StatusCode}");

            if (response.IsSuccessStatusCode)
            {
                uploadTracker.MarkAsUploaded(filePath);
                LogManager.Log($"Successfully uploaded: {Path.GetFileName(filePath)}");

                BeginInvoke(() =>
                {
                    trayIcon?.ShowBalloonTip(3000, "Upload Complete",
                        $"Uploaded: {Path.GetFileName(filePath)}",
                        ToolTipIcon.Info);
                });
            }
            else
            {
                var errorContent = await response.Content.ReadAsStringAsync();
                LogManager.Log($"Upload failed ({response.StatusCode}): {Path.GetFileName(filePath)} - {errorContent}", "ERROR");

                BeginInvoke(() =>
                {
                    trayIcon?.ShowBalloonTip(5000, "Upload Failed",
                        $"Failed to upload: {Path.GetFileName(filePath)}\n{response.StatusCode}",
                        ToolTipIcon.Error);
                });
            }
        }
        catch (TaskCanceledException ex)
        {
            LogManager.Log($"Upload timeout for {Path.GetFileName(filePath)}: {ex.Message}", "ERROR");
        }
        catch (HttpRequestException ex)
        {
            LogManager.Log($"Network error uploading {Path.GetFileName(filePath)}: {ex.Message}", "ERROR");
            if (ex.InnerException != null)
            {
                LogManager.Log($"  Inner exception: {ex.InnerException.Message}", "ERROR");
            }
        }
        catch (Exception ex)
        {
            LogManager.Log($"Unexpected error uploading {Path.GetFileName(filePath)}: {ex.GetType().Name} - {ex.Message}", "ERROR");
            LogManager.Log($"  Stack trace: {ex.StackTrace}", "ERROR");
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
            SaveSettings(settings, telemetryFolder);
            LogManager.Log("Settings updated");
            LogManager.Log($"Monitoring folder: {telemetryFolder}");
        }
    }

    private async void OnCheckForUpdates(object? sender, EventArgs e)
    {
        try
        {
            LogManager.Log("Checking for updates...");

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
            LogManager.Log($"Error checking for updates: {ex.Message}", "ERROR");
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
        var btnViewRelease = new Button
        {
            Text = "View Release Page",
            Location = new Point(20, 325),
            Size = new Size(140, 30),
            Font = new Font("Segoe UI", 9)
        };
        btnViewRelease.Click += (s, e) =>
        {
            var checker = new UpdateChecker();
            checker.OpenReleasePage(release.HtmlUrl);
            updateForm.Close();
        };
        updateForm.Controls.Add(btnViewRelease);

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

    private AppSettings LoadSettings()
    {
        try
        {
            string settingsPath = Path.Combine(
                AppDomain.CurrentDomain.BaseDirectory,
                "appsettings.json"
            );

            if (File.Exists(settingsPath))
            {
                string json = File.ReadAllText(settingsPath);
                var settings = JsonSerializer.Deserialize<AppSettings>(json, new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true
                });

                if (settings != null)
                {
                    LogManager.Log("Settings loaded successfully");
                    return settings;
                }
            }
        }
        catch (Exception ex)
        {
            LogManager.Log($"Error loading settings: {ex.Message}", "ERROR");
        }

        LogManager.Log("Using default settings");
        return new AppSettings
        {
            ServerUrl = "https://garage.mapleleafmakers.com",
            ApiToken = "",
            TelemetryFolder = ""
        };
    }

    private void SaveSettings(AppSettings settings, string telemetryFolder)
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
            LogManager.Log("Settings saved");
        }
        catch (Exception ex)
        {
            LogManager.Log($"Error saving settings: {ex.Message}", "ERROR");
        }
    }
}

public class AppSettings
{
    public string ServerUrl { get; set; } = "https://garage.mapleleafmakers.com";
    public string ApiToken { get; set; } = "";
    public string? TelemetryFolder { get; set; }
    public bool AutoUpload { get; set; } = true;
}

public class UploadTracker
{
    private HashSet<string> uploadedFiles;
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
                LogManager.Log($"Loaded {uploadedFiles.Count} tracked files");
            }
            else
            {
                uploadedFiles = new HashSet<string>();
            }
        }
        catch (Exception ex)
        {
            LogManager.Log($"Error loading tracked files: {ex.Message}", "ERROR");
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
            LogManager.Log($"Error saving tracked files: {ex.Message}", "ERROR");
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

public static class LogManager
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

public class LogForm : Form
{
    private TextBox txtLog;
    private Button btnClear, btnSave, btnClose;

    public LogForm()
    {
        this.Text = "Agent Log";
        this.Size = new Size(800, 600);
        this.StartPosition = FormStartPosition.CenterScreen;
        this.FormBorderStyle = FormBorderStyle.Sizable;

        // Log text box
        txtLog = new TextBox
        {
            Multiline = true,
            ReadOnly = true,
            ScrollBars = ScrollBars.Vertical,
            Font = new Font("Consolas", 9),
            Location = new Point(10, 10),
            Size = new Size(760, 500),
            Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        };

        // Load existing logs
        txtLog.Text = string.Join(Environment.NewLine, LogManager.GetAllLogs());
        txtLog.SelectionStart = txtLog.Text.Length;
        txtLog.ScrollToCaret();

        // Subscribe to new log events
        LogManager.LogAdded += OnLogAdded;

        // Buttons
        btnClear = new Button
        {
            Text = "Clear",
            Location = new Point(10, 520),
            Size = new Size(100, 30),
            Anchor = AnchorStyles.Bottom | AnchorStyles.Left
        };
        btnClear.Click += (s, e) =>
        {
            LogManager.Clear();
            txtLog.Clear();
        };

        btnSave = new Button
        {
            Text = "Save to File",
            Location = new Point(120, 520),
            Size = new Size(120, 30),
            Anchor = AnchorStyles.Bottom | AnchorStyles.Left
        };
        btnSave.Click += BtnSave_Click;

        btnClose = new Button
        {
            Text = "Close",
            Location = new Point(670, 520),
            Size = new Size(100, 30),
            Anchor = AnchorStyles.Bottom | AnchorStyles.Right
        };
        btnClose.Click += (s, e) => this.Close();

        this.Controls.AddRange(new Control[] { txtLog, btnClear, btnSave, btnClose });
        this.AcceptButton = btnClose;
        this.FormClosing += (s, e) => LogManager.LogAdded -= OnLogAdded;
    }

    private void OnLogAdded(string logEntry)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => OnLogAdded(logEntry));
            return;
        }

        txtLog.AppendText(logEntry + Environment.NewLine);
        txtLog.SelectionStart = txtLog.Text.Length;
        txtLog.ScrollToCaret();
    }

    private void BtnSave_Click(object? sender, EventArgs e)
    {
        using var saveDialog = new SaveFileDialog
        {
            Filter = "Log Files (*.log)|*.log|Text Files (*.txt)|*.txt|All Files (*.*)|*.*",
            DefaultExt = "log",
            FileName = $"agent_log_{DateTime.Now:yyyyMMdd_HHmmss}.log"
        };

        if (saveDialog.ShowDialog() == DialogResult.OK)
        {
            try
            {
                File.WriteAllLines(saveDialog.FileName, LogManager.GetAllLogs());
                MessageBox.Show("Log saved successfully!", "Success", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error saving log:\n{ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}

public class StatusForm : Form
{
    public StatusForm(bool isMonitoring, AppSettings settings, string telemetryFolder, int uploadedCount)
    {
        this.Text = "Agent Status";
        this.Size = new Size(500, 380);
        this.StartPosition = FormStartPosition.CenterScreen;
        this.FormBorderStyle = FormBorderStyle.FixedDialog;
        this.MaximizeBox = false;

        var lblTitle = new Label
        {
            Text = "Ridgway Garage Agent",
            Font = new Font(Font.FontFamily, 14, FontStyle.Bold),
            Location = new Point(20, 20),
            Size = new Size(450, 30)
        };

        var lblStatus = new Label
        {
            Text = $"Status: {(isMonitoring ? "Monitoring" : "Stopped")}",
            Location = new Point(20, 60),
            Size = new Size(450, 25)
        };

        var lblFolder = new Label
        {
            Text = $"Telemetry Folder:",
            Location = new Point(20, 90),
            Size = new Size(450, 20)
        };

        var txtFolder = new TextBox
        {
            Text = telemetryFolder,
            Location = new Point(20, 115),
            Size = new Size(450, 25),
            ReadOnly = true
        };

        var lblServer = new Label
        {
            Text = $"Server: {settings.ServerUrl}",
            Location = new Point(20, 150),
            Size = new Size(450, 25)
        };

        var lblToken = new Label
        {
            Text = $"API Token: {(string.IsNullOrEmpty(settings.ApiToken) ? "Not configured" : "Configured")}",
            Location = new Point(20, 180),
            Size = new Size(450, 25)
        };

        var lblUploaded = new Label
        {
            Text = $"Files Uploaded: {uploadedCount}",
            Location = new Point(20, 210),
            Size = new Size(450, 25)
        };

        var lblAutoUpload = new Label
        {
            Text = $"Auto-Upload: {(settings.AutoUpload ? "Enabled" : "Disabled")}",
            Location = new Point(20, 240),
            Size = new Size(450, 25)
        };

        var btnClose = new Button
        {
            Text = "Close",
            Location = new Point(185, 280),
            Size = new Size(120, 35),
            DialogResult = DialogResult.OK
        };

        this.Controls.AddRange(new Control[] {
            lblTitle, lblStatus, lblFolder, txtFolder, lblServer, lblToken, lblUploaded, lblAutoUpload, btnClose
        });

        this.AcceptButton = btnClose;
    }
}

public class SettingsForm : Form
{
    private TextBox txtServerUrl, txtApiToken, txtTelemetryFolder;
    private CheckBox chkAutoUpload;
    private Button btnShowToken;
    private AppSettings settings;
    private string telemetryFolder;
    private bool tokenVisible = false;

    public SettingsForm(AppSettings currentSettings, string currentTelemetryFolder)
    {
        settings = currentSettings;
        telemetryFolder = currentTelemetryFolder;

        this.Text = "Settings";
        this.Size = new Size(550, 360);
        this.StartPosition = FormStartPosition.CenterScreen;
        this.FormBorderStyle = FormBorderStyle.FixedDialog;
        this.MaximizeBox = false;

        var lblServer = new Label
        {
            Text = "Server URL:",
            Location = new Point(20, 20),
            Size = new Size(100, 25)
        };

        txtServerUrl = new TextBox
        {
            Text = settings.ServerUrl,
            Location = new Point(130, 20),
            Size = new Size(380, 25)
        };

        var lblToken = new Label
        {
            Text = "API Token:",
            Location = new Point(20, 60),
            Size = new Size(100, 25)
        };

        txtApiToken = new TextBox
        {
            Text = settings.ApiToken,
            Location = new Point(130, 60),
            Size = new Size(310, 25),
            UseSystemPasswordChar = true
        };

        btnShowToken = new Button
        {
            Text = "Show",
            Location = new Point(450, 58),
            Size = new Size(60, 28)
        };
        btnShowToken.Click += BtnShowToken_Click;

        var lblFolder = new Label
        {
            Text = "Telemetry Folder:",
            Location = new Point(20, 100),
            Size = new Size(100, 25)
        };

        txtTelemetryFolder = new TextBox
        {
            Text = telemetryFolder,
            Location = new Point(130, 100),
            Size = new Size(300, 25)
        };

        var btnBrowse = new Button
        {
            Text = "Browse...",
            Location = new Point(440, 98),
            Size = new Size(70, 28)
        };
        btnBrowse.Click += BtnBrowse_Click;

        chkAutoUpload = new CheckBox
        {
            Text = "Automatically upload new telemetry files",
            Location = new Point(130, 140),
            Size = new Size(300, 25),
            Checked = settings.AutoUpload
        };

        var btnTestConnection = new Button
        {
            Text = "Test Connection",
            Location = new Point(130, 180),
            Size = new Size(150, 35)
        };
        btnTestConnection.Click += BtnTestConnection_Click;

        var btnSave = new Button
        {
            Text = "Save",
            Location = new Point(260, 260),
            Size = new Size(120, 35),
            DialogResult = DialogResult.OK
        };
        btnSave.Click += BtnSave_Click;

        var btnCancel = new Button
        {
            Text = "Cancel",
            Location = new Point(390, 260),
            Size = new Size(120, 35),
            DialogResult = DialogResult.Cancel
        };

        this.Controls.AddRange(new Control[] {
            lblServer, txtServerUrl, lblToken, txtApiToken, btnShowToken,
            lblFolder, txtTelemetryFolder, btnBrowse, chkAutoUpload, btnTestConnection, btnSave, btnCancel
        });

        this.AcceptButton = btnSave;
        this.CancelButton = btnCancel;
    }

    private void BtnShowToken_Click(object? sender, EventArgs e)
    {
        tokenVisible = !tokenVisible;
        txtApiToken.UseSystemPasswordChar = !tokenVisible;
        btnShowToken.Text = tokenVisible ? "Hide" : "Show";
    }

    private void BtnBrowse_Click(object? sender, EventArgs e)
    {
        using var folderDialog = new FolderBrowserDialog
        {
            Description = "Select iRacing telemetry folder",
            SelectedPath = telemetryFolder,
            ShowNewFolderButton = false
        };

        if (folderDialog.ShowDialog() == DialogResult.OK)
        {
            txtTelemetryFolder.Text = folderDialog.SelectedPath;
        }
    }

    private async void BtnTestConnection_Click(object? sender, EventArgs e)
    {
        var serverUrl = txtServerUrl.Text.Trim();
        var apiToken = txtApiToken.Text.Trim();

        if (string.IsNullOrEmpty(serverUrl))
        {
            MessageBox.Show("Please enter a server URL.", "Missing Server URL", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        if (string.IsNullOrEmpty(apiToken))
        {
            MessageBox.Show("Please enter an API token.", "Missing API Token", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var btn = sender as Button;
        if (btn != null)
        {
            btn.Enabled = false;
            btn.Text = "Testing...";
        }

        try
        {
            using var httpClient = new HttpClient();
            httpClient.Timeout = TimeSpan.FromSeconds(10);
            httpClient.DefaultRequestHeaders.Add("Authorization", $"Token {apiToken}");

            // Test connection using dedicated auth test endpoint
            var response = await httpClient.GetAsync(serverUrl.TrimEnd('/') + "/api/auth/test/");

            if (response.IsSuccessStatusCode)
            {
                var jsonResponse = await response.Content.ReadAsStringAsync();
                var authData = JsonSerializer.Deserialize<JsonElement>(jsonResponse);

                var username = authData.GetProperty("username").GetString();
                var sessionCount = authData.GetProperty("sessions_count").GetInt32();

                MessageBox.Show(
                    $"Connection successful!\n\n" +
                    $"Authenticated as: {username}\n" +
                    $"Total sessions: {sessionCount}\n\n" +
                    $"Server is reachable and API token is valid.",
                    "Success",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
            }
            else if (response.StatusCode == System.Net.HttpStatusCode.Unauthorized ||
                     response.StatusCode == System.Net.HttpStatusCode.Forbidden)
            {
                var errorResponse = await response.Content.ReadAsStringAsync();
                MessageBox.Show(
                    $"Authentication failed!\n\nServer is reachable but API token is invalid.\n\nPlease check your API token in the web interface.",
                    "Authentication Failed",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            else
            {
                MessageBox.Show(
                    $"Connection failed!\n\nServer responded with: {response.StatusCode}",
                    "Connection Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
        catch (TaskCanceledException)
        {
            MessageBox.Show(
                "Connection timed out!\n\nCould not reach the server. Check your server URL and network connection.",
                "Timeout",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                $"Connection failed!\n\n{ex.Message}",
                "Error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
        finally
        {
            if (btn != null)
            {
                btn.Enabled = true;
                btn.Text = "Test Connection";
            }
        }
    }

    private void BtnSave_Click(object? sender, EventArgs e)
    {
        settings.ServerUrl = txtServerUrl.Text.Trim();
        settings.ApiToken = txtApiToken.Text.Trim();
        settings.AutoUpload = chkAutoUpload.Checked;
        telemetryFolder = txtTelemetryFolder.Text.Trim();
    }

    public AppSettings GetSettings()
    {
        return settings;
    }

    public string GetTelemetryFolder()
    {
        return telemetryFolder;
    }
}
