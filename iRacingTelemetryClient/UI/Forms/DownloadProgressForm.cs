namespace iRacingTelemetryClient.UI.Forms;

public class DownloadProgressForm : Form
{
    private Label lblStatus;
    private ProgressBar progressBar;
    private Label lblProgress;

    public DownloadProgressForm(string filename)
    {
        Text = "Downloading Update";
        Size = new Size(450, 150);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;

        lblStatus = new Label
        {
            Text = $"Downloading: {filename}",
            Location = new Point(20, 20),
            Size = new Size(410, 25),
            Font = new Font("Segoe UI", 9)
        };
        this.Controls.Add(lblStatus);

        progressBar = new ProgressBar
        {
            Location = new Point(20, 55),
            Size = new Size(410, 25),
            Minimum = 0,
            Maximum = 100
        };
        this.Controls.Add(progressBar);

        lblProgress = new Label
        {
            Text = "0 MB / 0 MB (0%)",
            Location = new Point(20, 90),
            Size = new Size(410, 20),
            Font = new Font("Segoe UI", 9),
            TextAlign = ContentAlignment.MiddleCenter
        };
        this.Controls.Add(lblProgress);
    }

    public void UpdateProgress(DownloadProgress progress)
    {
        if (InvokeRequired)
        {
            Invoke(new Action<DownloadProgress>(UpdateProgress), progress);
            return;
        }

        progressBar.Value = Math.Min(progress.PercentComplete, 100);

        double downloadedMB = progress.BytesDownloaded / 1024.0 / 1024.0;
        double totalMB = progress.TotalBytes / 1024.0 / 1024.0;

        lblProgress.Text = $"{downloadedMB:F1} MB / {totalMB:F1} MB ({progress.PercentComplete}%)";
    }
}
