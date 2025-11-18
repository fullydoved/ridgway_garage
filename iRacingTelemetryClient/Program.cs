using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using SVappsLAB.iRacingTelemetrySDK;

namespace iRacingTelemetryClient;

/// <summary>
/// Required telemetry variables from iRacing SDK
/// </summary>
[RequiredTelemetryVars([
    "SessionTime", "LapDist", "LapDistPct", "Lap", "LapCurrentLapTime", "LapLastLapTime",
    "Speed", "RPM", "Gear",
    "Throttle", "Brake", "SteeringWheelAngle", "Clutch",
    "Lat", "Lon",
    "LFtempCL", "RFtempCL", "LRtempCL", "RRtempCL",
    "LFpressure", "RFpressure", "LRpressure", "RRpressure",
    "FuelLevel", "FuelUsePerHour",
    "PlayerTrackSurface", "OnPitRoad",
    "IsOnTrack", "IsOnTrackCar"
])]
internal static class Program
{
    [STAThread]
    static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}

public class MainForm : Form
{
    private NotifyIcon? trayIcon;
    private ContextMenuStrip? trayMenu;
    private AppSettings settings;
    private ITelemetryClient<TelemetryData>? telemetryClient;
    private ClientWebSocket? webSocket;
    private CancellationTokenSource? streamingCts;

    private bool isStreaming = false;
    private bool sessionInitialized = false;
    private int currentLap = 0;
    private DateTime lastSendTime = DateTime.MinValue;
    private TimeSpan sendInterval;

    public MainForm()
    {
        // Load settings
        settings = LoadSettings();
        sendInterval = TimeSpan.FromMilliseconds(1000.0 / settings.UpdateRateHz);

        // Initialize form (hidden)
        this.Text = "iRacing Telemetry Client";
        this.WindowState = FormWindowState.Minimized;
        this.ShowInTaskbar = false;
        this.FormBorderStyle = FormBorderStyle.FixedSingle;
        this.MaximizeBox = false;
        this.Size = new Size(400, 300);

        // Create system tray icon
        trayMenu = new ContextMenuStrip();
        trayMenu.Items.Add("Start Streaming", null, OnStartStreaming);
        trayMenu.Items.Add("Stop Streaming", null, OnStopStreaming);
        trayMenu.Items.Add("-");
        trayMenu.Items.Add("Settings...", null, OnSettings);
        trayMenu.Items.Add("View Log", null, OnViewLog);
        trayMenu.Items.Add("-");
        trayMenu.Items.Add("Exit", null, OnExit);

        // Disable Stop initially
        trayMenu.Items[1].Enabled = false;

        // Load custom icon
        Icon appIcon;
        try
        {
            appIcon = new Icon("app.ico");
        }
        catch
        {
            appIcon = SystemIcons.Application;
        }

        trayIcon = new NotifyIcon()
        {
            Icon = appIcon,
            ContextMenuStrip = trayMenu,
            Visible = true,
            Text = "iRacing Telemetry - Stopped"
        };

        trayIcon.DoubleClick += OnTrayIconDoubleClick;

        // Show balloon tip on startup
        trayIcon.ShowBalloonTip(3000, "iRacing Telemetry",
            "Client is ready. Right-click icon to start streaming.",
            ToolTipIcon.Info);

        // Handle form closing
        this.FormClosing += MainForm_FormClosing;
    }

    private void MainForm_FormClosing(object? sender, FormClosingEventArgs e)
    {
        if (isStreaming)
        {
            var result = MessageBox.Show(
                "Streaming is active. Stop streaming and exit?",
                "Confirm Exit",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question);

            if (result == DialogResult.Yes)
            {
                StopStreamingAsync().Wait();
            }
            else
            {
                e.Cancel = true;
                return;
            }
        }

        trayIcon?.Dispose();
    }

    private void OnTrayIconDoubleClick(object? sender, EventArgs e)
    {
        ShowStatusWindow();
    }

    private void ShowStatusWindow()
    {
        var status = new StatusForm(isStreaming, settings, currentLap);
        status.ShowDialog();
    }

    private async void OnStartStreaming(object? sender, EventArgs e)
    {
        if (isStreaming) return;

        try
        {
            trayIcon!.Text = "iRacing Telemetry - Connecting...";
            trayIcon.ShowBalloonTip(2000, "Starting", "Connecting to server...", ToolTipIcon.Info);

            webSocket = new ClientWebSocket();

            if (!await ConnectToServerAsync())
            {
                trayIcon.ShowBalloonTip(5000, "Connection Failed",
                    $"Could not connect to {settings.ServerUrl}",
                    ToolTipIcon.Error);
                trayIcon.Text = "iRacing Telemetry - Connection Failed";
                return;
            }

            telemetryClient = TelemetryClient<TelemetryData>.Create(null);
            telemetryClient.OnTelemetryUpdate += OnTelemetryUpdate;

            streamingCts = new CancellationTokenSource();
            isStreaming = true;

            // Update menu
            trayMenu!.Items[0].Enabled = false; // Start
            trayMenu.Items[1].Enabled = true;   // Stop

            trayIcon.Text = "iRacing Telemetry - Connected";
            trayIcon.ShowBalloonTip(2000, "Connected", "Waiting for iRacing...", ToolTipIcon.Info);

            // Start monitoring in background
            _ = Task.Run(async () =>
            {
                try
                {
                    await telemetryClient.Monitor(streamingCts.Token);
                }
                catch (TaskCanceledException)
                {
                    // Normal shutdown
                }
                catch (Exception ex)
                {
                    BeginInvoke(() =>
                    {
                        trayIcon.ShowBalloonTip(5000, "Error", $"Streaming error: {ex.Message}", ToolTipIcon.Error);
                    });
                }
            });
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Failed to start streaming: {ex.Message}", "Error",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            await StopStreamingAsync();
        }
    }

    private async void OnStopStreaming(object? sender, EventArgs e)
    {
        await StopStreamingAsync();
    }

    private async Task StopStreamingAsync()
    {
        if (!isStreaming) return;

        streamingCts?.Cancel();

        if (webSocket?.State == WebSocketState.Open)
        {
            await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, "User stopped", CancellationToken.None);
        }

        webSocket?.Dispose();
        telemetryClient?.Dispose();

        isStreaming = false;
        sessionInitialized = false;
        currentLap = 0;

        // Update menu
        trayMenu!.Items[0].Enabled = true;  // Start
        trayMenu.Items[1].Enabled = false;  // Stop

        trayIcon!.Text = "iRacing Telemetry - Stopped";
        trayIcon.ShowBalloonTip(2000, "Stopped", "Streaming stopped", ToolTipIcon.Info);
    }

    private void OnSettings(object? sender, EventArgs e)
    {
        var settingsForm = new SettingsForm(settings);
        if (settingsForm.ShowDialog() == DialogResult.OK)
        {
            settings = settingsForm.Settings;
            SaveSettings(settings);
            sendInterval = TimeSpan.FromMilliseconds(1000.0 / settings.UpdateRateHz);

            trayIcon!.ShowBalloonTip(2000, "Settings Saved", "Configuration updated", ToolTipIcon.Info);
        }
    }

    private void OnViewLog(object? sender, EventArgs e)
    {
        ShowStatusWindow();
    }

    private void OnExit(object? sender, EventArgs e)
    {
        Application.Exit();
    }

    private async Task<bool> ConnectToServerAsync()
    {
        try
        {
            await webSocket!.ConnectAsync(new Uri(settings.ServerUrl), CancellationToken.None);
            _ = Task.Run(ReceiveMessagesAsync);
            return true;
        }
        catch
        {
            return false;
        }
    }

    private async Task ReceiveMessagesAsync()
    {
        var buffer = new byte[4096];
        try
        {
            while (webSocket!.State == WebSocketState.Open)
            {
                var result = await webSocket.ReceiveAsync(new ArraySegment<byte>(buffer), CancellationToken.None);
                if (result.MessageType == WebSocketMessageType.Close)
                    break;

                string message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                HandleServerMessage(message);
            }
        }
        catch { }
    }

    private void HandleServerMessage(string message)
    {
        try
        {
            var doc = JsonDocument.Parse(message);
            var root = doc.RootElement;

            if (root.TryGetProperty("type", out var typeElement))
            {
                string messageType = typeElement.GetString() ?? "";

                if (messageType == "session_created" && root.TryGetProperty("session_id", out var sessionIdElement))
                {
                    BeginInvoke(() =>
                    {
                        trayIcon!.ShowBalloonTip(3000, "Session Created",
                            $"Session ID: {sessionIdElement.GetInt32()}",
                            ToolTipIcon.Info);
                    });
                }
                else if (messageType == "events")
                {
                    if (root.TryGetProperty("events", out var eventsElement))
                    {
                        foreach (var evt in eventsElement.EnumerateArray())
                        {
                            if (evt.TryGetProperty("type", out var eventType) &&
                                eventType.GetString() == "lap_completed")
                            {
                                var lapNum = evt.GetProperty("lap_number").GetInt32();
                                var lapTime = evt.GetProperty("lap_time").GetDouble();

                                BeginInvoke(() =>
                                {
                                    trayIcon!.ShowBalloonTip(2000, $"Lap {lapNum} Complete",
                                        $"Time: {lapTime:F3}s",
                                        ToolTipIcon.Info);
                                });
                            }
                        }
                    }
                }
            }
        }
        catch { }
    }

    private async void OnTelemetryUpdate(object? sender, TelemetryData telemetry)
    {
        if (!sessionInitialized && telemetry.IsOnTrackCar)
        {
            await SendSessionInitAsync();
            sessionInitialized = true;

            BeginInvoke(() =>
            {
                trayIcon!.Text = "iRacing Telemetry - Streaming";
                trayIcon.ShowBalloonTip(2000, "iRacing Connected", "Now streaming telemetry", ToolTipIcon.Info);
            });
        }

        if (!telemetry.IsOnTrackCar) return;

        var now = DateTime.UtcNow;
        if (now - lastSendTime < sendInterval) return;
        lastSendTime = now;

        int lap = telemetry.Lap;
        if (lap != currentLap && lap > 0)
        {
            currentLap = lap;
            BeginInvoke(() => trayIcon!.Text = $"iRacing Telemetry - Lap {currentLap}");
        }

        var telemetryData = new
        {
            session_time = telemetry.SessionTime,
            lap_distance = telemetry.LapDist,
            lap_distance_pct = telemetry.LapDistPct,
            lap_number = telemetry.Lap,
            lap_time = telemetry.LapCurrentLapTime,
            speed = telemetry.Speed,
            rpm = telemetry.RPM,
            gear = telemetry.Gear,
            throttle = telemetry.Throttle,
            brake = telemetry.Brake,
            steering = telemetry.SteeringWheelAngle,
            clutch = telemetry.Clutch,
            lat = telemetry.Lat,
            lon = telemetry.Lon,
            lf_tire_temp = telemetry.LFtempCL,
            rf_tire_temp = telemetry.RFtempCL,
            lr_tire_temp = telemetry.LRtempCL,
            rr_tire_temp = telemetry.RRtempCL,
            lf_tire_pressure = telemetry.LFpressure,
            rf_tire_pressure = telemetry.RFpressure,
            lr_tire_pressure = telemetry.LRpressure,
            rr_tire_pressure = telemetry.RRpressure,
            fuel_level = telemetry.FuelLevel,
            fuel_use_per_hour = telemetry.FuelUsePerHour,
            player_track_surface = (int)telemetry.PlayerTrackSurface,
            on_pit_road = telemetry.OnPitRoad
        };

        await SendTelemetryAsync(telemetryData);
    }

    private async Task SendSessionInitAsync()
    {
        var message = new
        {
            type = "session_init",
            driver_id = settings.DriverId,
            session_info = new
            {
                track_name = "Unknown Track",
                track_config = "",
                car_name = "Unknown Car",
                session_type = "practice",
                driver_name = Environment.UserName
            }
        };
        await SendMessageAsync(message);
    }

    private async Task SendTelemetryAsync(object telemetryData)
    {
        if (!sessionInitialized) return;
        await SendMessageAsync(new { type = "telemetry", data = telemetryData });
    }

    private async Task SendMessageAsync(object message)
    {
        if (webSocket?.State != WebSocketState.Open) return;
        try
        {
            string json = JsonSerializer.Serialize(message);
            byte[] bytes = Encoding.UTF8.GetBytes(json);
            await webSocket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, CancellationToken.None);
        }
        catch { }
    }

    private static AppSettings LoadSettings()
    {
        try
        {
            string json = File.ReadAllText("appsettings.json");
            return JsonSerializer.Deserialize<AppSettings>(json) ?? new AppSettings();
        }
        catch
        {
            return new AppSettings();
        }
    }

    private static void SaveSettings(AppSettings settings)
    {
        try
        {
            var options = new JsonSerializerOptions { WriteIndented = true };
            string json = JsonSerializer.Serialize(settings, options);
            File.WriteAllText("appsettings.json", json);
        }
        catch { }
    }
}

public class AppSettings
{
    public string ServerUrl { get; set; } = "ws://localhost:42069/ws/telemetry/live/";
    public int DriverId { get; set; } = 1;
    public int UpdateRateHz { get; set; } = 60;
}

// Settings Form
public class SettingsForm : Form
{
    private TextBox txtServerUrl;
    private NumericUpDown numDriverId;
    private NumericUpDown numUpdateRate;
    private Button btnOK, btnCancel, btnTest;

    public AppSettings Settings { get; private set; }

    public SettingsForm(AppSettings settings)
    {
        Settings = new AppSettings
        {
            ServerUrl = settings.ServerUrl,
            DriverId = settings.DriverId,
            UpdateRateHz = settings.UpdateRateHz
        };

        this.Text = "Settings";
        this.Size = new Size(500, 250);
        this.FormBorderStyle = FormBorderStyle.FixedDialog;
        this.StartPosition = FormStartPosition.CenterScreen;
        this.MaximizeBox = false;
        this.MinimizeBox = false;

        // Server URL
        var lblServer = new Label { Text = "Server URL:", Location = new Point(20, 20), AutoSize = true };
        txtServerUrl = new TextBox { Location = new Point(20, 45), Size = new Size(440, 25), Text = Settings.ServerUrl };

        // Driver ID
        var lblDriver = new Label { Text = "Driver ID:", Location = new Point(20, 80), AutoSize = true };
        numDriverId = new NumericUpDown { Location = new Point(20, 105), Size = new Size(200, 25), Minimum = 1, Maximum = 999999, Value = Settings.DriverId };

        // Update Rate
        var lblRate = new Label { Text = "Update Rate (Hz):", Location = new Point(240, 80), AutoSize = true };
        numUpdateRate = new NumericUpDown { Location = new Point(240, 105), Size = new Size(200, 25), Minimum = 1, Maximum = 60, Value = Settings.UpdateRateHz };

        // Buttons
        btnTest = new Button { Text = "Test Connection", Location = new Point(20, 160), Size = new Size(130, 30) };
        btnTest.Click += BtnTest_Click;

        btnOK = new Button { Text = "OK", Location = new Point(280, 160), Size = new Size(90, 30), DialogResult = DialogResult.OK };
        btnOK.Click += (s, e) =>
        {
            Settings.ServerUrl = txtServerUrl.Text;
            Settings.DriverId = (int)numDriverId.Value;
            Settings.UpdateRateHz = (int)numUpdateRate.Value;
        };

        btnCancel = new Button { Text = "Cancel", Location = new Point(380, 160), Size = new Size(90, 30), DialogResult = DialogResult.Cancel };

        this.Controls.AddRange(new Control[] { lblServer, txtServerUrl, lblDriver, numDriverId, lblRate, numUpdateRate, btnTest, btnOK, btnCancel });
        this.AcceptButton = btnOK;
        this.CancelButton = btnCancel;
    }

    private async void BtnTest_Click(object? sender, EventArgs e)
    {
        btnTest.Enabled = false;
        btnTest.Text = "Testing...";

        try
        {
            using var testSocket = new ClientWebSocket();
            await testSocket.ConnectAsync(new Uri(txtServerUrl.Text), CancellationToken.None);
            await testSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Test", CancellationToken.None);

            MessageBox.Show("Connection successful!", "Test Result", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Connection failed:\n{ex.Message}", "Test Result", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            btnTest.Enabled = true;
            btnTest.Text = "Test Connection";
        }
    }
}

// Status Form
public class StatusForm : Form
{
    public StatusForm(bool isStreaming, AppSettings settings, int currentLap)
    {
        this.Text = "Status";
        this.Size = new Size(400, 300);
        this.FormBorderStyle = FormBorderStyle.FixedDialog;
        this.StartPosition = FormStartPosition.CenterScreen;
        this.MaximizeBox = false;
        this.MinimizeBox = false;

        var status = new Label
        {
            Location = new Point(20, 20),
            Size = new Size(360, 200),
            Text = $"Status: {(isStreaming ? "STREAMING" : "STOPPED")}\n\n" +
                   $"Server: {settings.ServerUrl}\n" +
                   $"Driver ID: {settings.DriverId}\n" +
                   $"Update Rate: {settings.UpdateRateHz} Hz\n" +
                   $"Current Lap: {(currentLap > 0 ? currentLap.ToString() : "N/A")}"
        };

        var btnClose = new Button
        {
            Text = "Close",
            Location = new Point(150, 230),
            Size = new Size(100, 30),
            DialogResult = DialogResult.OK
        };

        this.Controls.AddRange(new Control[] { status, btnClose });
        this.AcceptButton = btnClose;
    }
}
