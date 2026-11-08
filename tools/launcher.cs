// OHP Windows launcher. Numerical inference remains in the auditable Python source.
using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
class OHPLauncher {
    [STAThread]
    static void Main() {
        string root=AppDomain.CurrentDomain.BaseDirectory;
        string python=Path.Combine(root,@"runtime\python312\pythonw.exe");
        string script=Path.Combine(root,@"tools\launch_desktop.py");
        if(!File.Exists(python)||!File.Exists(script)) {
            MessageBox.Show("Copy or extract the complete OHP release folder. The local Python core or application is missing.","OHP",MessageBoxButtons.OK,MessageBoxIcon.Error);return;
        }
        try {
            var start=new ProcessStartInfo(python,"-B -s \""+script+"\"");
            start.WorkingDirectory=root;start.UseShellExecute=false;start.CreateNoWindow=true;
            start.EnvironmentVariables.Remove("PYTHONHOME");
            start.EnvironmentVariables.Remove("PYTHONPATH");
            start.EnvironmentVariables["PYTHONNOUSERSITE"]="1";
            start.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"]="1";
            start.EnvironmentVariables["PYTHONUTF8"]="1";
            start.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";
            Process.Start(start);
        } catch(Exception e) {
            MessageBox.Show(e.Message+"\nRun start_windows.cmd to see diagnostic output.","OHP could not start",MessageBoxButtons.OK,MessageBoxIcon.Error);
        }
    }
}
