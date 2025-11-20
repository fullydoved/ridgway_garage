using iRacingTelemetryClient.Services;

namespace iRacingTelemetryClient.UI.Forms;

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
        txtLog.Text = string.Join(Environment.NewLine, LoggingService.GetAllLogs());
        txtLog.SelectionStart = txtLog.Text.Length;
        txtLog.ScrollToCaret();

        // Subscribe to new log events
        LoggingService.LogAdded += OnLogAdded;

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
            LoggingService.Clear();
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
        this.FormClosing += (s, e) => LoggingService.LogAdded -= OnLogAdded;
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
                File.WriteAllLines(saveDialog.FileName, LoggingService.GetAllLogs());
                MessageBox.Show("Log saved successfully!", "Success", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error saving log:\n{ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}
