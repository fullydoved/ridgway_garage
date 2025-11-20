using iRacingTelemetryClient.Models;

namespace iRacingTelemetryClient.UI.Forms;

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
