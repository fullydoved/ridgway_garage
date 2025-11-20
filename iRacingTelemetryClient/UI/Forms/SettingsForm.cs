using System.Text.Json;
using iRacingTelemetryClient.Models;
using iRacingTelemetryClient.Services;

namespace iRacingTelemetryClient.UI.Forms;

public class SettingsForm : Form
{
    private TextBox txtServerUrl, txtApiToken, txtTelemetryFolder;
    private CheckBox chkAutoUpload, chkStartWithWindows;
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

        chkStartWithWindows = new CheckBox
        {
            Text = "Start with Windows",
            Location = new Point(130, 170),
            Size = new Size(300, 25),
            Checked = WindowsStartupService.IsStartupWithWindowsEnabled()
        };

        var btnTestConnection = new Button
        {
            Text = "Test Connection",
            Location = new Point(130, 210),
            Size = new Size(150, 35)
        };
        btnTestConnection.Click += BtnTestConnection_Click;

        var btnSave = new Button
        {
            Text = "Save",
            Location = new Point(260, 290),
            Size = new Size(120, 35),
            DialogResult = DialogResult.OK
        };
        btnSave.Click += BtnSave_Click;

        var btnCancel = new Button
        {
            Text = "Cancel",
            Location = new Point(390, 290),
            Size = new Size(120, 35),
            DialogResult = DialogResult.Cancel
        };

        this.Controls.AddRange(new Control[] {
            lblServer, txtServerUrl, lblToken, txtApiToken, btnShowToken,
            lblFolder, txtTelemetryFolder, btnBrowse, chkAutoUpload, chkStartWithWindows, btnTestConnection, btnSave, btnCancel
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
        var serverUrl = txtServerUrl.Text.Trim();
        var apiToken = txtApiToken.Text.Trim();

        // Validate API token doesn't look like a URL
        if (!string.IsNullOrEmpty(apiToken) &&
            (apiToken.StartsWith("http://", StringComparison.OrdinalIgnoreCase) ||
             apiToken.StartsWith("https://", StringComparison.OrdinalIgnoreCase)))
        {
            var result = MessageBox.Show(
                "Warning: The API Token appears to be a URL, not a token.\n\n" +
                "API tokens should be long random strings (64 characters), not URLs.\n\n" +
                "Do you want to save anyway?",
                "Invalid API Token",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Warning);

            if (result == DialogResult.No)
            {
                this.DialogResult = DialogResult.None; // Prevent form from closing
                return;
            }
        }

        settings.ServerUrl = serverUrl;
        settings.ApiToken = apiToken;
        settings.AutoUpload = chkAutoUpload.Checked;
        settings.StartWithWindows = chkStartWithWindows.Checked;
        telemetryFolder = txtTelemetryFolder.Text.Trim();

        // Update Windows startup registry
        WindowsStartupService.SetStartupWithWindows(settings.StartWithWindows);
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
