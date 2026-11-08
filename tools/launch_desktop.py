"""Visible error reporting for the standalone Windows desktop launcher."""
from pathlib import Path
import os,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['PYTHONNOUSERSITE']='1';os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['PYTHONUTF8']='1';os.environ['PYTHONIOENCODING']='utf-8'
try:
    from ohp_gui import OHPApp
    app=OHPApp();app.mainloop()
except Exception as error:
    log=ROOT/'outputs/startup_error.log';log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text(traceback.format_exc(),encoding='utf-8')
    import tkinter as tk
    from tkinter import messagebox
    window=tk.Tk();window.withdraw()
    messagebox.showerror('OHP could not start',str(error)+'\n\nDetails: '+str(log)+'\nRun start_windows.cmd to check or repair the local installation.')
    window.destroy();raise
