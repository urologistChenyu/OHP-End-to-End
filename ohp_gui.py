# English upload edition: UI strings translated from the bilingual research interface.
# Path resolution is relocatable; numerical model weights and prediction rules are unchanged.
"""OHP independent endpoint desktop application.

This UI is deliberately a thin, auditable layer over ``run_ohp.py``.  The
model code, weights, normalisation rules and quality gates remain unchanged.
The app launches the locked runner in a separate process, displays progress,
offers a DICOM/Mask viewer, and writes a self-contained run report.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
ROOT = Path(__file__).resolve().parent
PYTHON = Path(sys.executable)
PYTHONW = PYTHON
RUNNER = ROOT / 'run_ohp_publication.py'
MIN_CASES = 1
RECOMMENDED_CASES = 5
from run_ohp_publication import THRESHOLD as PRIMARY_THRESHOLD
try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:
    Image = ImageDraw = ImageTk = None

def now_name() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')

def safe_float(value: str) -> float | None:
    value = str(value).strip().replace(',', '')
    if not value:
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None

def case_id(value: str | Path) -> str:
    name = Path(str(value).replace('\\', '/')).name
    for suffix in ('.nii.png', '.nii.gz', '.nii', '.nrrd', '.nhdr', '.mha', '.mhd'):
        if name.lower().endswith(suffix):
            return name[:-len(suffix)]
    return Path(name).stem

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda : f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

@dataclass
class CaseRow:
    patient_id: str
    age: tk.StringVar
    tumorsize: tk.StringVar
    neut: tk.StringVar
    lymph: tk.StringVar

class ScrollableFrame(ttk.Frame):

    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, background='#ffffff')
        self.scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scrollbar.pack(side='right', fill='y')
        self.body.bind('<Configure>', self._on_body)
        self.canvas.bind('<Configure>', self._on_canvas)

    def _on_body(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_canvas(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

class OHPApp(tk.Tk):
    """Desktop controller for the locked OHP endpoint."""

    def __init__(self) -> None:
        super().__init__()
        self.title('OHP End-to-End Analysis')
        self.geometry('1440x900')
        self.minsize(1180, 760)
        self.configure(background='#f4f7fb')
        try:
            self.iconbitmap(str(ROOT / 'assets' / 'ui' / 'ohp_icon.ico'))
        except Exception:
            pass
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.input_var = tk.StringVar()
        self.mask_var = tk.StringVar()
        self.mask_mode_var = tk.StringVar(value='automatic')
        self.output_var = tk.StringVar(value=str(ROOT / 'outputs' / now_name()))
        self.batch_var = tk.StringVar(value='Not created')
        self.status_var = tk.StringVar(value='Ready: select a DICOM folder')
        self.phase_var = tk.StringVar(value='Waiting for input')
        self.case_count_var = tk.StringVar(value='0 cases')
        self.quality_var = tk.StringVar(value='Not QC-checked')
        self.ohp_var = tk.StringVar(value='--')
        self.fusion_formula_var = tk.StringVar(value='Fusion formula: loading after run')
        self.fusion_integrity_var = tk.StringVar(value='Same saved prediction table')
        self._case_rows: list[CaseRow] = []
        self._case_ids: list[str] = []
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._running = False
        self._manifest: dict[str, Any] | None = None
        self._segmentation_progress: dict[str, Any] | None = None
        self._segmentation_progress_mtime = 0.0
        self._predictions: list[dict[str, Any]] = []
        self._viewer_cache: dict[str, tuple[Any, Any]] = {}
        self._viewer_photo: Any = None
        self._viewer_image: Any = None
        self._viewer_mask: Any = None
        self._viewer_source = ''
        self._viewer_spacing: tuple[float, float, float] | None = None
        self._viewer_spacing_cache: dict[str, tuple[float, float, float] | None] = {}
        self._viewer_indices = {'axial': 0, 'coronal': 0, 'sagittal': 0}
        self._viewer_token = 0
        self._found_inputs: dict[str, Path] = {}
        self._viewer_3d_canvas: Any = None
        self._viewer_3d_figure: Any = None
        self._current_output: Path | None = None
        self._build_style()
        self._build_ui()
        self.after(120, self._drain_queue)
        self.after(600, self._poll_segmentation_progress)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('App.TFrame', background='#f4f7fb')
        style.configure('Panel.TFrame', background='#ffffff')
        style.configure('Card.TFrame', background='#ffffff')
        style.configure('Header.TFrame', background='#ffffff')
        style.configure('Title.TLabel', background='#ffffff', foreground='#102a43', font=('Segoe UI', 21, 'bold'))
        style.configure('Subtitle.TLabel', background='#ffffff', foreground='#6b7a90', font=('Segoe UI', 9))
        style.configure('CardTitle.TLabel', background='#ffffff', foreground='#1f2a44', font=('Segoe UI', 11, 'bold'))
        style.configure('Body.TLabel', background='#ffffff', foreground='#243b53', font=('Segoe UI', 9))
        style.configure('Muted.TLabel', background='#ffffff', foreground='#829ab6', font=('Segoe UI', 9))
        style.configure('CardMuted.TLabel', background='#ffffff', foreground='#6b7a90', font=('Segoe UI', 9))
        style.configure('Metric.TLabel', background='#ffffff', foreground='#2563eb', font=('Segoe UI', 19, 'bold'))
        style.configure('MetricSmall.TLabel', background='#ffffff', foreground='#102a43', font=('Segoe UI', 10, 'bold'))
        style.configure('TEntry', fieldbackground='#f8fafc', foreground='#102a43', insertcolor='#2563eb', borderwidth=1, padding=8, lightcolor='#dce6f2', darkcolor='#dce6f2')
        style.configure('TCombobox', fieldbackground='#f8fafc', foreground='#102a43', arrowsize=14, padding=5)
        style.configure('Primary.TButton', background='#2563eb', foreground='#ffffff', font=('Segoe UI', 10, 'bold'), padding=(14, 9), borderwidth=0)
        style.map('Primary.TButton', background=[('active', '#1d4ed8'), ('disabled', '#a9bde8')])
        style.configure('Secondary.TButton', background='#e8eef8', foreground='#1f4e8c', font=('Segoe UI', 9), padding=(10, 7), borderwidth=0)
        style.map('Secondary.TButton', background=[('active', '#d9e5f5')])
        style.configure('Danger.TButton', background='#fff0f1', foreground='#b4233c', font=('Segoe UI', 9), padding=(10, 7), borderwidth=0)
        style.configure('TNotebook', background='#f4f7fb', borderwidth=0)
        style.configure('TNotebook.Tab', background='#e8eef8', foreground='#6b7a90', padding=(16, 8), font=('Segoe UI', 9))
        style.map('TNotebook.Tab', background=[('selected', '#2563eb')], foreground=[('selected', '#ffffff')])
        style.configure('Treeview', background='#ffffff', fieldbackground='#ffffff', foreground='#243b53', rowheight=31, borderwidth=0, font=('Segoe UI', 9))
        style.configure('Treeview.Heading', background='#e8eef8', foreground='#1f2a44', font=('Segoe UI', 9, 'bold'), relief='flat')
        style.map('Treeview', background=[('selected', '#dbeafe')], foreground=[('selected', '#102a43')])
        style.configure('Horizontal.TProgressbar', troughcolor='#e8eef8', background='#2563eb', lightcolor='#2563eb', darkcolor='#2563eb', borderwidth=0, thickness=11)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style='App.TFrame')
        root.pack(fill='both', expand=True)
        header = ttk.Frame(root, style='Header.TFrame', height=76)
        header.pack(fill='x')
        header.pack_propagate(False)
        brand = ttk.Frame(header, style='Header.TFrame')
        brand.pack(side='left', padx=26, pady=13)
        ttk.Label(brand, text='OHP', style='Title.TLabel').pack(side='left')
        text_box = ttk.Frame(brand, style='Header.TFrame')
        text_box.pack(side='left', padx=(15, 0))
        ttk.Label(text_box, text='End-to-End Analysis', style='Title.TLabel', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(text_box, text='DICOM  →  Automatic or supplied mask  →  Five-branch mean  →  OHP%', style='Subtitle.TLabel').pack(anchor='w', pady=(2, 0))
        accent_line = tk.Frame(header, height=4, bg='#2563eb')
        accent_line.pack(side='bottom', fill='x')
        self.header_status = tk.Label(header, text='Ready', bg='#ffffff', fg='#2563eb', font=('Segoe UI', 10, 'bold'))
        self.header_status.pack(side='right', padx=28)
        body = ttk.Frame(root, style='App.TFrame')
        body.pack(fill='both', expand=True, padx=16, pady=14)
        sidebar = ttk.Frame(body, style='Panel.TFrame', width=360)
        sidebar.pack(side='left', fill='y', padx=(0, 12))
        sidebar.pack_propagate(False)
        side_scroll = ScrollableFrame(sidebar)
        side_scroll.pack(fill='both', expand=True)
        self._build_sidebar(side_scroll.body)
        main = ttk.Frame(body, style='App.TFrame')
        main.pack(side='left', fill='both', expand=True)
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill='both', expand=True)
        self.overview_tab = ttk.Frame(self.notebook, style='App.TFrame')
        self.viewer_tab = ttk.Frame(self.notebook, style='App.TFrame')
        self.branch_tab = ttk.Frame(self.notebook, style='App.TFrame')
        self.export_tab = ttk.Frame(self.notebook, style='App.TFrame')
        self.notebook.add(self.overview_tab, text='Overview')
        self.notebook.add(self.viewer_tab, text='CT & Mask')
        self.notebook.add(self.branch_tab, text='Branch Results')
        self.notebook.add(self.export_tab, text='Export & Audit')
        self._build_overview(self.overview_tab)
        self._build_viewer(self.viewer_tab)
        self._build_branch(self.branch_tab)
        self._build_export(self.export_tab)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text='Case Workspace', style='CardTitle.TLabel').pack(anchor='w', padx=20, pady=(22, 4))
        ttk.Label(parent, text='Select a DICOM folder, enter preoperative variables, and run.', style='CardMuted.TLabel', wraplength=315).pack(anchor='w', padx=20, pady=(0, 15))
        self._field(parent, 'CT input directory', self.input_var, self.choose_input)
        ttk.Button(parent, text='Select DICOM files', command=self.choose_dicom_files).pack(fill='x', padx=20, pady=3)
        route = ttk.Frame(parent, style='Panel.TFrame')
        route.pack(fill='x', padx=20)
        ttk.Radiobutton(route, text='Automatic', variable=self.mask_mode_var, value='automatic').pack(side='left')
        ttk.Radiobutton(route, text='Supplied mask', variable=self.mask_mode_var, value='supplied').pack(side='left')
        self._field(parent, 'Supplied-mask directory', self.mask_var, self.choose_mask)
        self._field(parent, 'Output directory', self.output_var, self.choose_output)
        ttk.Button(parent, text='Discover Cases / Enter Variables', style='Secondary.TButton', command=self.discover_cases).pack(fill='x', padx=20, pady=(16, 5))
        ttk.Button(parent, text='Clear Workspace', style='Secondary.TButton', command=self.clear_workspace).pack(fill='x', padx=20, pady=2)
        ttk.Button(parent, text='Open completed batch', style='Secondary.TButton', command=self.choose_completed_batch).pack(fill='x', padx=20, pady=2)
        ttk.Separator(parent).pack(fill='x', padx=20, pady=18)
        ttk.Label(parent, text='Batch QC Rules', style='CardTitle.TLabel').pack(anchor='w', padx=20)
        ttk.Label(parent, text='Single-case scoring is supported.\nOHP_mean5_ACC_20261104 uses frozen training statistics.\nA case is scored independently of the uploaded batch size.', style='CardMuted.TLabel', justify='left', wraplength=315).pack(anchor='w', padx=20, pady=(7, 10))
        self.run_btn = ttk.Button(parent, text='Start Analysis', style='Primary.TButton', command=self.start_run)
        self.run_btn.pack(fill='x', padx=20, pady=(8, 4))
        self.stop_btn = ttk.Button(parent, text='Stop', style='Danger.TButton', command=self.stop_run, state='disabled')
        self.stop_btn.pack(fill='x', padx=20, pady=4)
        ttk.Label(parent, text='The endpoint runs independently and keeps an auditable log.', style='Muted.TLabel', wraplength=315).pack(anchor='w', padx=20, pady=(18, 0))

    def _field(self, parent: ttk.Frame, label: str, variable: tk.StringVar, command: Any) -> None:
        frame = ttk.Frame(parent, style='Panel.TFrame')
        frame.pack(fill='x', padx=20, pady=(4, 3))
        ttk.Label(frame, text=label, style='Body.TLabel').pack(anchor='w')
        row = ttk.Frame(frame, style='Panel.TFrame')
        row.pack(fill='x', pady=(5, 0))
        ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Browse', style='Secondary.TButton', command=command).pack(side='right', padx=(6, 0))

    def _build_overview(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style='App.TFrame')
        top.pack(fill='x', pady=(0, 12))
        self._metric(top, 'Current Batch', self.case_count_var, 'Cases in batch')
        self._metric(top, 'Batch ID', self.batch_var, 'SHA-256 after run')
        self._metric(top, 'QC Status', self.quality_var, 'Segmentation and input QC')
        status = ttk.Frame(parent, style='Card.TFrame')
        status.pack(fill='x', pady=(0, 12))
        ttk.Label(status, text='Live Progress', style='CardTitle.TLabel').pack(anchor='w', padx=18, pady=(15, 3))
        ttk.Label(status, textvariable=self.phase_var, style='CardMuted.TLabel').pack(anchor='w', padx=18)
        self.progress = ttk.Progressbar(status, mode='determinate', maximum=100)
        self.progress.pack(fill='x', padx=18, pady=(10, 3))
        self.status_label = ttk.Label(status, textvariable=self.status_var, style='Body.TLabel')
        self.status_label.pack(anchor='w', padx=18, pady=(0, 15))
        self.workflow_card = ttk.Frame(parent, style='Card.TFrame')
        self.workflow_card.pack(fill='x', pady=(0, 12))
        ttk.Label(self.workflow_card, text='Workflow', style='CardTitle.TLabel').pack(anchor='w', padx=18, pady=(12, 2))
        # Native English labels remain sharp at different display scaling settings.
        steps = ttk.Frame(self.workflow_card, style='Card.TFrame')
        steps.pack(fill='x', padx=18, pady=(8, 16))
        for column, (title, detail) in enumerate([
            ('1  CT / DICOM', 'Select the intended CT series'),
            ('2  Tumour mask', 'Automatic or supplied contour'),
            ('3  Features', 'Frozen image preprocessing'),
            ('4  Fusion', 'Five-branch arithmetic mean'),
            ('5  OHP risk', 'Probability and mask review'),
        ]):
            steps.columnconfigure(column, weight=1, uniform='workflow')
            step = ttk.Frame(steps, style='Card.TFrame')
            step.grid(row=0, column=column, sticky='nsew', padx=(0, 12))
            ttk.Label(step, text=title, style='CardTitle.TLabel').pack(anchor='w')
            ttk.Label(step, text=detail, style='CardMuted.TLabel', wraplength=160).pack(anchor='w', pady=(4, 0))
        cards = ttk.Frame(parent, style='App.TFrame')
        cards.pack(fill='x', pady=(0, 12))
        self.ohp_card = ttk.Frame(cards, style='Card.TFrame')
        self.ohp_card.pack(side='left', fill='both', expand=True, padx=(0, 6))
        ttk.Label(self.ohp_card, text='Final Fusion', style='CardTitle.TLabel').pack(anchor='w', padx=18, pady=(16, 2))
        ttk.Label(self.ohp_card, textvariable=self.ohp_var, style='Metric.TLabel').pack(anchor='w', padx=18, pady=2)
        ttk.Label(self.ohp_card, text='Five-branch arithmetic mean / Cutoff 0.353054', style='CardMuted.TLabel').pack(anchor='w', padx=18, pady=(0, 16))
        self.review_card = ttk.Frame(cards, style='Card.TFrame')
        self.review_card.pack(side='left', fill='both', expand=True, padx=(6, 0))
        ttk.Label(self.review_card, text='Review', style='CardTitle.TLabel').pack(anchor='w', padx=18, pady=(16, 2))
        self.review_label = ttk.Label(self.review_card, text='Review CT and Mask after segmentation.', style='MetricSmall.TLabel', wraplength=300)
        self.review_label.pack(anchor='w', padx=18, pady=2)
        ttk.Label(self.review_card, text='Failed segmentation never produces a forced OHP.', style='CardMuted.TLabel').pack(anchor='w', padx=18, pady=(0, 16))
        log_frame = ttk.Frame(parent, style='Card.TFrame')
        log_frame.pack(fill='both', expand=True)
        ttk.Label(log_frame, text='Run Log', style='CardTitle.TLabel').pack(anchor='w', padx=18, pady=(15, 7))
        self.log_text = tk.Text(log_frame, height=15, background='#f8fafc', foreground='#486581', insertbackground='#2563eb', relief='flat', bd=0, font=('Consolas', 9), wrap='word')
        self.log_text.pack(side='left', fill='both', expand=True, padx=(18, 0), pady=(0, 18))
        scroll = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        scroll.pack(side='right', fill='y', padx=(0, 15), pady=(0, 18))
        self.log_text.configure(yscrollcommand=scroll.set, state='disabled')

    def _metric(self, parent: ttk.Frame, title: str, variable: tk.StringVar, subtitle: str) -> None:
        card = ttk.Frame(parent, style='Card.TFrame')
        card.pack(side='left', fill='both', expand=True, padx=4)
        ttk.Label(card, text=title, style='CardTitle.TLabel').pack(anchor='w', padx=15, pady=(12, 2))
        ttk.Label(card, textvariable=variable, style='MetricSmall.TLabel').pack(anchor='w', padx=15, pady=2)
        ttk.Label(card, text=subtitle, style='CardMuted.TLabel').pack(anchor='w', padx=15, pady=(0, 12))

    def _build_viewer(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent, style='Card.TFrame')
        controls.pack(fill='x', pady=(0, 10))
        ttk.Label(controls, text='Case', style='Body.TLabel').pack(side='left', padx=(15, 6), pady=12)
        self.viewer_case = tk.StringVar()
        self.case_combo = ttk.Combobox(controls, textvariable=self.viewer_case, state='readonly', width=22)
        self.case_combo.pack(side='left', padx=4, pady=8)
        self.case_combo.bind('<<ComboboxSelected>>', lambda _e: self._load_viewer_case())
        ttk.Label(controls, text='WW', style='Body.TLabel').pack(side='left', padx=(25, 4))
        self.window_var = tk.StringVar(value='300')
        ttk.Entry(controls, textvariable=self.window_var, width=7).pack(side='left')
        ttk.Label(controls, text='WL', style='Body.TLabel').pack(side='left', padx=(10, 4))
        self.level_var = tk.StringVar(value='25')
        ttk.Entry(controls, textvariable=self.level_var, width=7).pack(side='left')
        ttk.Button(controls, text='Apply', style='Secondary.TButton', command=self._refresh_viewer).pack(side='left', padx=10)
        ttk.Label(controls, text='View', style='Body.TLabel').pack(side='left', padx=(12, 4))
        self.view_mode_var = tk.StringVar(value='Single')
        view_mode = ttk.Combobox(controls, textvariable=self.view_mode_var, values=('Single', 'Three views / 3 Views'), state='readonly', width=14)
        view_mode.pack(side='left', padx=2)
        view_mode.bind('<<ComboboxSelected>>', lambda _e: self._draw_viewer())
        ttk.Label(controls, text='Plane', style='Body.TLabel').pack(side='left', padx=(10, 4))
        self.plane_var = tk.StringVar(value='Axial')
        plane = ttk.Combobox(controls, textvariable=self.plane_var, values=('Axial', 'Coronal / Coronal', 'Sagittal / Sagittal'), state='readonly', width=18)
        plane.pack(side='left', padx=2)
        plane.bind('<<ComboboxSelected>>', self._plane_changed)
        ttk.Button(controls, text='Prev', style='Secondary.TButton', command=lambda : self._step_slice(-1)).pack(side='left', padx=(8, 2))
        ttk.Button(controls, text='Next', style='Secondary.TButton', command=lambda : self._step_slice(1)).pack(side='left', padx=2)
        self.mask_visible_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text='Show Mask', variable=self.mask_visible_var, command=self._refresh_viewer).pack(side='left', padx=(10, 2))
        self.viewer_info = ttk.Label(controls, text='No image loaded', style='CardMuted.TLabel')
        self.viewer_info.pack(side='right', padx=15)
        viewer_body = ttk.Frame(parent, style='App.TFrame')
        viewer_body.pack(fill='both', expand=True)
        image_card = ttk.Frame(viewer_body, style='Card.TFrame')
        image_card.pack(side='left', fill='both', expand=True, padx=(0, 10))
        self.image_canvas = tk.Canvas(image_card, background='#02060c', highlightthickness=0)
        self.image_canvas.pack(fill='both', expand=True, padx=12, pady=12)
        self.image_canvas.bind('<Configure>', lambda _e: self._draw_viewer())
        self.image_canvas.bind('<MouseWheel>', self._wheel_viewer)
        self.image_canvas.bind('<Button-4>', lambda _e: self._step_slice(1))
        self.image_canvas.bind('<Button-5>', lambda _e: self._step_slice(-1))
        side = ttk.Frame(viewer_body, style='Card.TFrame', width=390)
        side.pack(side='right', fill='y')
        side.pack_propagate(False)
        ttk.Label(side, text='Image QC', style='CardTitle.TLabel').pack(anchor='w', padx=16, pady=(17, 8))
        self.viewer_qc = tk.Text(side, height=13, background='#f8fafc', foreground='#486581', relief='flat', bd=0, font=('Segoe UI', 9), wrap='word')
        self.viewer_qc.pack(fill='x', padx=16)
        self.viewer_qc.configure(state='disabled')
        ttk.Label(side, text='Slice Position', style='CardMuted.TLabel').pack(anchor='w', padx=16, pady=(18, 2))
        self.slice_var = tk.IntVar(value=0)
        self.slice_scale = ttk.Scale(side, from_=0, to=0, orient='horizontal', command=lambda _v: self._draw_viewer())
        self.slice_scale.pack(fill='x', padx=16)
        self.slice_label = ttk.Label(side, text='-- / --', style='CardMuted.TLabel')
        self.slice_label.pack(anchor='w', padx=16, pady=(5, 16))
        ttk.Label(side, text='Controls', style='CardMuted.TLabel').pack(anchor='w', padx=16, pady=(8, 2))
        ttk.Label(side, text='Scroll or use Previous/Next to browse\nThree views: axial, coronal, sagittal\nColoured tumour mask can be toggled', style='CardMuted.TLabel', justify='left', wraplength=345).pack(anchor='w', padx=16, pady=(0, 8))
        ttk.Label(side, text='3D Fusion View', style='CardTitle.TLabel').pack(anchor='w', padx=12, pady=(4, 4))
        self.viewer_3d_frame = ttk.Frame(side, style='Panel.TFrame')
        self.viewer_3d_frame.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.viewer_3d_placeholder = ttk.Label(self.viewer_3d_frame, text='CT orthogonal planes + 3D Mask appear after segmentation', style='CardMuted.TLabel', justify='center', wraplength=340)
        self.viewer_3d_placeholder.pack(fill='both', expand=True, padx=10, pady=10)

    def _build_branch(self, parent: ttk.Frame) -> None:
        intro = ttk.Frame(parent, style='Card.TFrame')
        intro.pack(fill='x', pady=(0, 10))
        ttk.Label(intro, text='Branch Probabilities & Fusion', style='CardTitle.TLabel').pack(anchor='w', padx=18, pady=(15, 3))
        ttk.Label(intro, text='Values are read from the same saved prediction table; full precision is retained.', style='CardMuted.TLabel').pack(anchor='w', padx=18, pady=(0, 14))
        ttk.Label(intro, textvariable=self.fusion_formula_var, style='CardMuted.TLabel', wraplength=1100, justify='left').pack(anchor='w', padx=18, pady=(0, 4))
        ttk.Label(intro, textvariable=self.fusion_integrity_var, style='CardMuted.TLabel', wraplength=1100, justify='left').pack(anchor='w', padx=18, pady=(0, 12))
        table_frame = ttk.Frame(parent, style='Card.TFrame')
        table_frame.pack(fill='both', expand=True)
        cols = ('patient_id', 'Clinical_prob', 'Traditional_prob', 'Habitat_prob', '2D_prob', '2.5D_prob', 'fusion_prob', 'OHP_percent', 'pred_primary')
        heads = ('Case', 'Clinical', 'Traditional', 'Habitat', '2D', '2.5D', 'Fusion', 'OHP%', 'Class')
        self.branch_tree = ttk.Treeview(table_frame, columns=cols, show='headings')
        for (c, h) in zip(cols, heads):
            self.branch_tree.heading(c, text=h)
            self.branch_tree.column(c, width=105 if c != 'patient_id' else 130, anchor='center')
        y = ttk.Scrollbar(table_frame, orient='vertical', command=self.branch_tree.yview)
        x = ttk.Scrollbar(table_frame, orient='horizontal', command=self.branch_tree.xview)
        self.branch_tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.branch_tree.grid(row=0, column=0, sticky='nsew', padx=(15, 0), pady=(15, 0))
        y.grid(row=0, column=1, sticky='ns', padx=(0, 15), pady=(15, 0))
        x.grid(row=1, column=0, sticky='ew', padx=(15, 0), pady=(0, 15))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

    def _build_export(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style='Card.TFrame')
        card.pack(fill='both', expand=True)
        ttk.Label(card, text='Results & Audit', style='CardTitle.TLabel').pack(anchor='w', padx=18, pady=(16, 4))
        ttk.Label(card, text='Each run saves model hashes, case list hash, batch ID, normalization, QC gates, and outputs.', style='CardMuted.TLabel').pack(anchor='w', padx=18, pady=(0, 10))
        self.export_list = tk.Listbox(card, background='#f8fafc', foreground='#486581', selectbackground='#dbeafe', selectforeground='#102a43', relief='flat', bd=0, font=('Consolas', 9), height=16)
        self.export_list.pack(fill='both', expand=True, padx=18, pady=(0, 12))
        buttons = ttk.Frame(card, style='Card.TFrame')
        buttons.pack(fill='x', padx=18, pady=(0, 18))
        ttk.Button(buttons, text='Open Output', style='Secondary.TButton', command=self.open_output).pack(side='left')
        ttk.Button(buttons, text='Open Audit', style='Secondary.TButton', command=self.open_report).pack(side='left', padx=8)
        ttk.Button(buttons, text='Copy Batch ID', style='Secondary.TButton', command=self.copy_batch).pack(side='left')
        ttk.Label(buttons, text='OHP requires imaging QC and clinical review.', style='CardMuted.TLabel').pack(side='right')

    def choose_input(self) -> None:
        p = filedialog.askdirectory(title='Select the CT DICOM case directory')
        if p:
            self.input_var.set(p)
            self.discover_cases()

    def choose_mask(self) -> None:
        p = filedialog.askdirectory(title='Select binary masks matched to the CT case IDs')
        if p:
            self.mask_var.set(p)
            self.mask_mode_var.set('supplied')

    def choose_dicom_files(self) -> None:
        files = filedialog.askopenfilenames(title='Select complete DICOM data files for each CT series', filetypes=[('DICOM data', '*.dcm *.ima *')])
        if not files:
            return
        try:
            from run_ohp_publication import selected_dicom_manifest
            dest = ROOT / 'outputs' / 'selected_files' / now_name() / 'selected_cases.json'
            dest.parent.mkdir(parents=True, exist_ok=True)
            selected_dicom_manifest(files, dest)
            self.input_var.set(str(dest))
            self.discover_cases()
        except Exception as exc:
            messagebox.showerror('DICOM file selection', str(exc))

    def import_clinical(self) -> None:
        name = filedialog.askopenfilename(title='Import the four-variable clinical CSV', filetypes=[('CSV', '*.csv')])
        if not name:
            return
        try:
            import pandas as pd
            z = pd.read_csv(name, dtype={'ID': str, 'patient_id': str}).rename(columns={'patient_id': 'ID'}).set_index('ID')
            if z.index.duplicated().any():
                raise ValueError('Duplicate case IDs')
            for row in self._case_rows:
                r = z.loc[row.patient_id]
                for (var, k) in zip([row.age, row.tumorsize, row.neut, row.lymph], ['Age', 'Tumorsize', 'NEUT', 'LYMPH']):
                    var.set(str(r[k]))
        except Exception as exc:
            messagebox.showerror('Clinical CSV import failed', str(exc))

    def choose_output(self) -> None:
        p = filedialog.askdirectory(title='Select output directory')
        if p:
            self.output_var.set(str(Path(p) / now_name()))

    def choose_completed_batch(self) -> None:
        if self._running:
            messagebox.showinfo('Analysis in progress', 'Wait for the current analysis before opening a completed batch.')
            return
        selected = filedialog.askdirectory(title='Open a completed batch from this model (run_manifest.json)')
        if not selected:
            return
        try:
            folder = Path(selected).resolve()
            self._clear_results()
            self.output_var.set(str(folder))
            self._load_result(folder)
            records = self._manifest.get('segmentation', [])
            modes = {r.get('mode') for r in records}
            if len(modes) == 1:
                self.mask_mode_var.set(next(iter(modes)))
            self._case_ids = [r['patient_id'] for r in self._predictions]
            self._found_inputs = {str(r['patient_id']): Path(r['image']) for r in records}
            self.progress['value'] = 100
            self.phase_var.set('Completed batch loaded')
            self.status_var.set('Stored results loaded; no new inference')
            self.header_status.configure(text='Loaded', fg='#22685e')
        except Exception as exc:
            self._clear_results()
            messagebox.showerror('Cannot open the saved batch', str(exc))

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state='normal')
        self.log_text.insert('end', text.rstrip() + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def discover_cases(self) -> None:
        if self._running:
            return
        root = self.input_var.get().strip()
        if self.mask_mode_var.get() == 'supplied' and (not self.mask_var.get().strip() or not Path(self.mask_var.get().strip()).is_dir()):
            messagebox.showerror('Supplied-mask route', 'Select a valid supplied-mask directory.')
            return
        if not root:
            messagebox.showinfo('Input folder required', 'Select a DICOM folder first.')
            return
        self.status_var.set('Scanning DICOM series…')
        self.header_status.configure(text='Scanning', fg='#f2c66d')
        threading.Thread(target=self._discover_worker, args=(root,), daemon=True).start()

    def _discover_worker(self, root: str) -> None:
        try:
            sys.path.insert(0, str(ROOT))
            from run_ohp_publication import find_inputs
            found = find_inputs(Path(root).resolve())
            self._queue.put(('discovered', [(cid, path if isinstance(path, list) else str(path)) for (cid, path) in found]))
        except Exception as exc:
            self._queue.put(('error', f'Could not identify a DICOM series: {type(exc).__name__}: {exc}'))

    def _populate_cases(self, found: list[tuple[str, str]]) -> None:
        self._case_ids = [str(cid) for (cid, _p) in found]
        self._found_inputs = {str(cid): path if isinstance(path, list) else Path(path) for (cid, path) in found}
        self.case_count_var.set(f'{len(self._case_ids)} cases')
        self._append_log(f"Found {len(self._case_ids)} cases: {', '.join(self._case_ids[:8])}{('…' if len(self._case_ids) > 8 else '')}")
        self.quality_var.set('Preoperative inputs required')
        self._build_clinical_table(found)
        self.case_combo.configure(values=self._case_ids)
        if self._case_ids:
            self.viewer_case.set(self._case_ids[0])
            self._load_viewer_case()
        if len(self._case_ids) < MIN_CASES:
            self.status_var.set(f'At least {MIN_CASES} complete case is required to calculate OHP.')
            self.header_status.configure(text='Too few', fg='#f29a9a')
        elif len(self._case_ids) < RECOMMENDED_CASES:
            self.status_var.set(f'Single-case scoring is supported; batches aid QC')
            self.header_status.configure(text='Validation', fg='#f2c66d')
        else:
            self.status_var.set('Cases found; enter variables')
            self.header_status.configure(text='Input needed', fg='#74e5d6')

    def _build_clinical_table(self, found: list[tuple[str, str]]) -> None:
        if hasattr(self, 'clinical_window'):
            self.clinical_window.destroy()
        self.clinical_window = tk.Toplevel(self)
        self.clinical_window.title('Preoperative Variables')
        self.clinical_window.geometry('820x620')
        self.clinical_window.configure(background='#f4f7fb')
        self.clinical_window.transient(self)
        top = ttk.Frame(self.clinical_window, style='Header.TFrame')
        top.pack(fill='x')
        ttk.Label(top, text='Preoperative Variables', style='Title.TLabel', font=('Segoe UI', 15, 'bold')).pack(anchor='w', padx=20, pady=(15, 2))
        ttk.Label(top, text='Enter all four variables for every case; missing/non-numeric values block OHP.', style='Subtitle.TLabel').pack(anchor='w', padx=20, pady=(0, 15))
        ttk.Button(top, text='Import clinical CSV', command=self.import_clinical).pack(anchor='w', padx=20, pady=(0, 8))
        sf = ScrollableFrame(self.clinical_window)
        sf.pack(fill='both', expand=True, padx=12, pady=12)
        headers = ['Case ID', 'Age', 'Tumorsize', 'NEUT', 'LYMPH']
        for (j, h) in enumerate(headers):
            ttk.Label(sf.body, text=h, style='Body.TLabel').grid(row=0, column=j, sticky='w', padx=8, pady=(4, 9))
        self._case_rows = []
        for (i, (cid, _path)) in enumerate(found, 1):
            vars_ = [tk.StringVar(), tk.StringVar(), tk.StringVar(), tk.StringVar()]
            row = CaseRow(str(cid), *vars_)
            self._case_rows.append(row)
            ttk.Label(sf.body, text=str(cid), style='Body.TLabel').grid(row=i, column=0, sticky='w', padx=8, pady=4)
            for (j, var) in enumerate(vars_, 1):
                ttk.Entry(sf.body, textvariable=var, width=18).grid(row=i, column=j, sticky='ew', padx=8, pady=4)
        for j in range(5):
            sf.body.columnconfigure(j, weight=1)
        bottom = ttk.Frame(self.clinical_window, style='Panel.TFrame')
        bottom.pack(fill='x', padx=12, pady=(0, 12))
        ttk.Button(bottom, text='Save & Close', style='Primary.TButton', command=self.clinical_window.destroy).pack(side='right', padx=8, pady=9)
        ttk.Label(bottom, text='Four clinical inputs; frozen training statistics support single cases or batches.', style='Muted.TLabel').pack(side='left', padx=12)

    def _clinical_csv(self, out: Path) -> Path:
        out.mkdir(parents=True, exist_ok=True)
        path = out / 'clinical_from_gui.csv'
        missing: list[str] = []
        records = []
        for row in self._case_rows:
            values = [safe_float(row.age.get()), safe_float(row.tumorsize.get()), safe_float(row.neut.get()), safe_float(row.lymph.get())]
            if any((v is None for v in values)):
                missing.append(row.patient_id)
            records.append({'patient_id': row.patient_id, 'Age': values[0], 'Tumorsize': values[1], 'NEUT': values[2], 'LYMPH': values[3]})
        if missing:
            raise ValueError('The following cases have incomplete preoperative inputs: ' + ', '.join(missing[:12]))
        with path.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=['patient_id', 'Age', 'Tumorsize', 'NEUT', 'LYMPH'])
            writer.writeheader()
            writer.writerows(records)
        return path

    def start_run(self) -> None:
        if self._running:
            return
        if not PYTHON.exists() or not RUNNER.exists():
            messagebox.showerror('Incomplete package', 'The runtime or run_ohp.py is missing.')
            return
        root = self.input_var.get().strip()
        if self.mask_mode_var.get() == 'supplied' and (not self.mask_var.get().strip() or not Path(self.mask_var.get().strip()).is_dir()):
            messagebox.showerror('Supplied-mask route', 'Select a valid supplied-mask directory.')
            return
        if not root:
            messagebox.showerror('Input required', 'Select a DICOM case folder.')
            return
        if len(self._case_ids) < MIN_CASES:
            messagebox.showerror('Too few cases', f'At least {MIN_CASES} complete case is required. Available: {len(self._case_ids)}.')
            return
        if len(self._case_rows) != len(self._case_ids):
            messagebox.showerror('Discover cases first', 'Discover cases and enter variables first.')
            return
        try:
            out = Path(self.output_var.get().strip() or ROOT / 'outputs' / now_name()).resolve()
            if (out / 'run_manifest.json').exists() or (out / 'cases').exists():
                raise ValueError('This output directory already contains results; choose a new directory.')
            clinical = self._clinical_csv(out)
            from run_ohp_publication import preflight
            preflight(root, clinical, self.mask_var.get().strip() if self.mask_mode_var.get() == 'supplied' else None)
        except Exception as exc:
            messagebox.showerror('Missing variables', str(exc))
            return
        out.mkdir(parents=True, exist_ok=True)
        self.output_var.set(str(out))
        stale_progress = out / 'segmentation_progress.json'
        if stale_progress.exists():
            try:
                stale_progress.unlink()
            except OSError:
                pass
        self._clear_results(preserve_viewer=True)
        self._running = True
        self.run_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal')
        self.header_status.configure(text='● Running / Running', fg='#f2c66d')
        self.status_var.set('Starting analysis process…')
        self.phase_var.set('Preparing')
        self.progress.configure(value=0)
        self._append_log(f'Output directory: {out}')
        self._append_log(f'Preoperative variables: {clinical}')
        self._append_log(f'Cases: {len(self._case_ids)}; OHP_mean5_ACC_20261104 frozen statistics; suggested batch review: {RECOMMENDED_CASES} cases')
        env = os.environ.copy()
        from package_paths import scratch_root
        env['OHP_WORK_ROOT'] = str(scratch_root())
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            self._process = subprocess.Popen([str(PYTHON), str(RUNNER), '--input', root, '--clinical', str(clinical), '--output', str(out)] + (['--mask-dir', self.mask_var.get().strip()] if self.mask_mode_var.get() == 'supplied' else []), cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=flags)
        except Exception as exc:
            self._running = False
            self.run_btn.configure(state='normal')
            self.stop_btn.configure(state='disabled')
            messagebox.showerror('Could not start', str(exc))
            return
        self._reader_thread = threading.Thread(target=self._read_process, daemon=True)
        self._reader_thread.start()

    def _read_process(self) -> None:
        assert self._process is not None
        if self._process.stdout is not None:
            for line in self._process.stdout:
                self._queue.put(('line', line.rstrip('\r\n')))
        code = self._process.wait()
        self._queue.put(('finished', code))

    def _drain_queue(self) -> None:
        try:
            while True:
                (kind, value) = self._queue.get_nowait()
                if kind == 'line':
                    self._handle_line(str(value))
                elif kind == 'discovered':
                    self._populate_cases(value)
                elif kind == 'error':
                    self.header_status.configure(text='● Error', fg='#f29a9a')
                    self.status_var.set(str(value))
                    self._append_log(str(value))
                    messagebox.showerror('Processing failed', str(value))
                elif kind == 'viewer_loaded':
                    self._apply_viewer_data(value)
                elif kind == 'viewer_error':
                    (cid, message) = value
                    self._append_log(f'Image display failed: {cid}：{message}')
                    self.viewer_info.configure(text='Image read failed')
                elif kind == 'finished':
                    self._finish_run(int(value))
        except queue.Empty:
            pass
        self.after(120, self._drain_queue)

    def _poll_segmentation_progress(self) -> None:
        """Load masks published by the runner before radiomics finishes."""
        try:
            progress_path = Path(self.output_var.get().strip()) / 'segmentation_progress.json'
            if progress_path.exists():
                mtime = progress_path.stat().st_mtime
                if mtime > self._segmentation_progress_mtime:
                    data = json.loads(progress_path.read_text(encoding='utf-8'))
                    self._segmentation_progress_mtime = mtime
                    self._segmentation_progress = data
                    records = {str(x.get('patient_id')): x for x in data.get('segmentation', [])}
                    cid = self.viewer_case.get().strip()
                    if cid in records and self._manifest is None:
                        self._load_viewer_case()
                    if records:
                        self.quality_var.set(f"Masks available: {len(records)}/{data.get('cases', len(self._case_ids))} cases / Masks ready")
                        if data.get('status') == 'failed_after_segmentation':
                            self.status_var.set('Segmentation is available, but later feature extraction failed. CT and mask review is still available.')
        except Exception as exc:
            self._append_log(f'Could not read segmentation progress: {exc}')
        self.after(600, self._poll_segmentation_progress)

    def _handle_line(self, line: str) -> None:
        self._append_log(line)
        m = re.search('\\[(.*?)\\]\\s+([0-9.]+)%\\s+(.*)$', line)
        if m:
            (cid, frac, msg) = (m.group(1), float(m.group(2)) / 100.0, m.group(3))
            if cid == 'BATCH':
                value = 88.0 + max(0.0, min(1.0, frac - 0.68)) / 0.32 * 12.0
            else:
                try:
                    pos = self._case_ids.index(cid)
                except ValueError:
                    pos = 0
                total = max(1, len(self._case_ids))
                value = (pos + frac) / total * 88.0
            self.progress.configure(value=min(88, value))
            self.phase_var.set(f'{cid} · {msg} / Processing')
            self.status_var.set(f'Processing: {cid} · {msg} / Processing')
        elif 'Starting independent PyRadiomics' in line:
            self.progress.configure(value=90)
            self.phase_var.set('Feature extraction')
        elif 'Completed: ' in line:
            self.progress.configure(value=100)
            self.phase_var.set('Complete')

    def _finish_run(self, code: int) -> None:
        self._running = False
        self.run_btn.configure(state='normal')
        self.stop_btn.configure(state='disabled')
        if code != 0:
            self.header_status.configure(text='Incomplete', fg='#f29a9a')
            self.status_var.set('Run incomplete; inspect the log and run_failed.json')
            self.quality_var.set('Failed')
            return
        try:
            self._load_result(Path(self.output_var.get()).resolve())
            self.header_status.configure(text='Complete', fg='#74e5d6')
            self.status_var.set('Complete; review CT + Mask before OHP')
            self.phase_var.set('All steps complete')
            self.progress.configure(value=100)
        except Exception as exc:
            self.header_status.configure(text='Result read failed', fg='#f29a9a')
            self.status_var.set(f'Analysis ended, but the results could not be read: {exc} / Analysis ended but result loading failed')
            self._append_log(f'Could not read results: {type(exc).__name__}: {exc}')

    def stop_run(self) -> None:
        if self._process is not None and self._running:
            if messagebox.askyesno('Stop analysis', 'Stop the current analysis? Incomplete cases will not have a final OHP score.'):
                self._process.terminate()
                self._append_log('The user stopped this run; incomplete outputs are not final OHP results.')

    def _clear_results(self, preserve_viewer: bool=False) -> None:
        self._manifest = None
        self._segmentation_progress = None
        self._segmentation_progress_mtime = 0.0
        self._predictions = []
        if preserve_viewer:
            self._viewer_cache.clear()
            self._viewer_spacing_cache.clear()
            self._viewer_mask = None
            self._viewer_source = 'Upload CT'
            self._draw_viewer()
            self._rebuild_3d_preview()
        else:
            self._viewer_cache.clear()
            self._viewer_spacing_cache.clear()
            self._viewer_image = self._viewer_mask = None
            self._viewer_photo = None
            self._viewer_source = ''
            self._viewer_spacing = None
            self._viewer_token += 1
            self._viewer_indices = {'axial': 0, 'coronal': 0, 'sagittal': 0}
            self._rebuild_3d_preview()
        self.ohp_var.set('--')
        self.batch_var.set('Not created')
        self.quality_var.set('Running')
        self.review_label.configure(text='Review CT + Mask after segmentation.')
        for item in self.branch_tree.get_children():
            self.branch_tree.delete(item)
        self.export_list.delete(0, 'end')

    def _load_result(self, out: Path) -> None:
        pred_path = out / 'patient_predictions.csv'
        manifest_path = out / 'run_manifest.json'
        if not pred_path.exists() or not manifest_path.exists():
            raise RuntimeError('patient_predictions.csv or run_manifest.json is missing.')
        import pandas as pd
        df = pd.read_csv(pred_path)
        self._predictions = df.to_dict('records')
        self._manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if self._manifest.get('protocol') != 'OHP_mean5_ACC_20261104':
            raise RuntimeError('The saved results use a different model version.')
        if self._manifest.get('clinical_features') != ['Age', 'Tumorsize', 'NEUT', 'LYMPH']:
            raise RuntimeError('The clinical input schema does not match this model.')
        fusion_contract = self._manifest.get('fusion', {})
        if fusion_contract.get('method') != 'mean5' or fusion_contract.get('weights') != [0.2] * 5 or abs(float(fusion_contract.get('threshold', -1)) - PRIMARY_THRESHOLD) > 1e-12:
            raise RuntimeError('The saved fusion rule, weights or threshold do not match this model.')
        self._current_output = out
        batch = str(self._manifest.get('batch_id', ''))
        self.batch_var.set(batch[:16] if batch else 'Not recorded')
        total = self._manifest.get('cases', len(df))
        failed = self._manifest.get('failed_cases', [])
        self.case_count_var.set(f'{len(df)}/{total} cases with risk estimates')
        self.quality_var.set('Computation complete; review CT and tumour mask')
        imputed = self._manifest.get('habitat_imputed_features', {}) or {}
        if imputed:
            self.quality_var.set(f'Input and model checks passed; habitat feature logs found for {len(imputed)} case(s)')
        if len(df):
            p = float(df['OHP_percent'].iloc[0])
            self.ohp_var.set(f'{p:.2f}%')
        fusion = self._manifest.get('fusion', {})
        weights = fusion.get('weights', [])
        order = fusion.get('weights_order', ['Clinical_prob', 'Traditional_prob', 'Habitat_prob', '2D_prob', '2.5D_prob'])
        if len(weights) == len(order) == 5:
            terms = ' + '.join((f'{float(w):.6f}×{name}' for (w, name) in zip(weights, order)))
            self.fusion_formula_var.set('OHP% = 100 × p; Positive / Positive: p ≥ 0.3530539465')
            try:
                expected = []
                for (_, row) in df.iterrows():
                    expected.append(sum((float(row[name]) * float(w) for (name, w) in zip(order, weights))))
                max_delta = max((abs(float(a) - float(b)) for (a, b) in zip(expected, df['fusion_prob'].tolist()))) if expected else 0.0
                max_ohp = max((abs(float(a) * 100.0 - float(b)) for (a, b) in zip(df['fusion_prob'].tolist(), df['OHP_percent'].tolist()))) if expected else 0.0
                ok = max(max_delta, max_ohp) <= 1e-10
                self.fusion_integrity_var.set(f"Fusion integrity: {('PASS' if ok else 'FAIL')}; max |Δfusion|={max_delta:.3g}, max |ΔOHP|={max_ohp:.3g}source: {pred_path.name}")
                if not ok:
                    self._append_log('The fused probability does not match the saved branch values. Review the batch files; the interface has not changed the probabilities.')
            except Exception as exc:
                self.fusion_integrity_var.set(f'Integrity check failed: {exc}')
        self.review_label.configure(text='Review CT + Mask for every case and confirm tumour coverage.')
        self._fill_branch_table(df)
        for rec in failed:
            self.branch_tree.insert('', 'end', values=[rec['patient_id']] + ['--'] * 7 + ['Review'])
        if failed:
            self.quality_var.set(f'{len(df)} cases completed; {len(failed)} cases require mask review')
        self._fill_export_list(out)
        ids = [str(x) for x in df['patient_id'].tolist()]
        self.case_combo.configure(values=ids)
        if ids:
            self.viewer_case.set(ids[0])
            self._load_viewer_case()
        self._write_html_report(out, df)
        self._append_log(f'Results loaded: {pred_path}')

    def _fill_branch_table(self, df: Any) -> None:
        for item in self.branch_tree.get_children():
            self.branch_tree.delete(item)
        cols = ('patient_id', 'Clinical_prob', 'Traditional_prob', 'Habitat_prob', '2D_prob', '2.5D_prob', 'fusion_prob', 'OHP_percent', 'pred_primary')
        for (_, r) in df.iterrows():
            vals = [str(r.get('patient_id', ''))]
            for c in cols[1:7]:
                vals.append(f'{float(r[c]):.6f}')
            vals.append(f"{float(r['OHP_percent']):.3f}")
            vals.append('Positive' if int(r['pred_primary']) else 'Negative')
            self.branch_tree.insert('', 'end', values=vals)

    def _fill_export_list(self, out: Path) -> None:
        self.export_list.delete(0, 'end')
        priority = {'patient_predictions.csv': 0, 'run_manifest.json': 1, 'case_status.csv': 2, 'OHP_result_report.html': 3}
        files = sorted([p for p in out.rglob('*') if p.is_file()], key=lambda p: (priority.get(p.name, 9) if p.parent == out else 10, str(p.relative_to(out))))
        for p in files:
            try:
                size = p.stat().st_size
                shown = f'{p.relative_to(out)}  ({size / 1024:.1f} KB)'
            except Exception:
                shown = str(p)
            self.export_list.insert('end', shown)

    def _write_html_report(self, out: Path, df: Any) -> None:
        manifest = self._manifest or {}
        rows = []
        for (_, r) in df.iterrows():
            rows.append('<tr>' + ''.join((f'<td>{str(r[c])}</td>' for c in df.columns)) + '</tr>')
        cols = ''.join((f'<th>{c}</th>' for c in df.columns))
        html = f"<!doctype html><html lang='en'><meta charset='utf-8'><title>OHP Risk Report</title>\n<style>body{{font-family:'Segoe UI',Arial;background:#0b1220;color:#dceeff;padding:28px}}h1{{color:#75e5d6}}.card{{background:#14243b;border-radius:12px;padding:18px;margin:14px 0}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #31516c;padding:7px;text-align:center}}th{{background:#1b4262}}td{{background:#0e1a2b}}.muted{{color:#9eb5cf}}</style>\n<h1>OHP End-to-End Analysis Report</h1><div class='card'><b>Software: </b>OHP-mean5-ACC-20261104<br><b>Batch ID: </b>{manifest.get('batch_id', '')}<br><b>Cases: </b>{manifest.get('cases', '')}<br><b>Cutoff: </b>{PRIMARY_THRESHOLD:.10}<br><b>Inference: </b>Standalone pipeline<br><span class='muted'>Review the CT and tumour contour for each case. Risk estimates support clinical review and do not replace the pathological reference standard.</span></div>\n<div class='card'><table><thead><tr>{cols}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></html>"
        (out / 'OHP_result_report.html').write_text(html, encoding='utf-8')

    def _read_viewer_volume(self, path: Path) -> tuple[Any, tuple[float, float, float]]:
        """Read a NIfTI or DICOM series for display without touching scoring."""
        import SimpleITK as sitk
        if isinstance(path, list) or not str(path).isascii():
            from run_ohp_publication import read_volume_image
            image = read_volume_image(path)
            return (sitk.GetArrayFromImage(image).astype('float32', copy=False), tuple((float(x) for x in image.GetSpacing())))
        if isinstance(path, list):
            image = sitk.ReadImage([str(p) for p in path])
        elif path.is_dir():
            series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(path)) or []
            if not series_ids:
                for child in sorted(path.iterdir()):
                    if child.is_dir():
                        series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(child)) or []
                        if series_ids:
                            path = child
                            break
            if not series_ids:
                raise RuntimeError('No readable DICOM series was found.')
            reader = sitk.ImageSeriesReader()
            files = reader.GetGDCMSeriesFileNames(str(path), series_ids[0])
            if not files:
                raise RuntimeError('The DICOM series has no slice files.')
            reader.SetFileNames(files)
            image = reader.Execute()
        else:
            image = sitk.ReadImage([str(p) for p in path]) if isinstance(path, list) else sitk.ReadImage(str(path))
        array = sitk.GetArrayFromImage(image).astype('float32', copy=False)
        if array.ndim != 3:
            raise RuntimeError(f'Only three-dimensional CT is supported; current dimensions: {array.shape}')
        spacing = tuple((float(x) for x in image.GetSpacing()))
        return (array, spacing)

    def _load_viewer_case(self) -> None:
        cid = self.viewer_case.get().strip()
        if not cid:
            return
        image_path: Path | None = self._found_inputs.get(cid)
        mask_path: Path | None = None
        source = 'Upload CT'
        source_manifest = self._manifest or self._segmentation_progress
        if source_manifest:
            records = {str(x.get('patient_id')): x for x in source_manifest.get('segmentation', [])}
            rec = records.get(cid)
            if rec:
                mask_value = rec.get('mask')
                mask_path = Path(mask_value) if mask_value else None
                image_path = Path(rec.get('image', Path(source_manifest['work_dir']) / cid / f'{cid}.nii.gz'))
                source = ('Processed CT + supplied mask' if rec.get('mode') == 'supplied' else 'Processed CT + automatic mask') if mask_path else 'Processed CT'
        if image_path is None:
            self.viewer_info.configure(text='Case image not found')
            return
        cached = self._viewer_cache.get(cid)
        if cached is not None and (mask_path is None or cached[1] is not None):
            (image, mask) = cached
            self._apply_viewer_data({'cid': cid, 'image': image, 'mask': mask, 'source': source, 'spacing': self._viewer_spacing_cache.get(cid)})
            return
        self._viewer_token += 1
        token = self._viewer_token
        self.viewer_info.configure(text=f'{cid}Loading image…')
        threading.Thread(target=self._viewer_worker, args=(token, cid, image_path, mask_path, source), daemon=True).start()

    def _viewer_worker(self, token: int, cid: str, image_path: Path, mask_path: Path | None, source: str) -> None:
        try:
            (image, spacing) = self._read_viewer_volume(image_path)
            mask = None
            if mask_path is not None and mask_path.exists():
                (mask, _mask_spacing) = self._read_viewer_volume(mask_path)
                mask = mask > 0
                if image.shape != mask.shape:
                    raise RuntimeError(f'The CT and mask dimensions differ: {image.shape} / {mask.shape}')
            self._queue.put(('viewer_loaded', {'token': token, 'cid': cid, 'image': image, 'mask': mask, 'source': source, 'spacing': spacing}))
        except Exception as exc:
            self._queue.put(('viewer_error', (cid, f'{type(exc).__name__}: {exc}')))

    def _apply_viewer_data(self, data: dict[str, Any]) -> None:
        if data.get('token') is not None and int(data['token']) != self._viewer_token:
            return
        cid = str(data['cid'])
        (image, mask) = (data['image'], data.get('mask'))
        (self._viewer_image, self._viewer_mask) = (image, mask)
        self._viewer_source = str(data.get('source') or 'CT')
        self._viewer_spacing = data.get('spacing')
        self._viewer_cache[cid] = (image, mask)
        self._viewer_spacing_cache[cid] = self._viewer_spacing
        while len(self._viewer_cache) > 2:
            old_cid = next(iter(self._viewer_cache))
            self._viewer_cache.pop(old_cid)
            self._viewer_spacing_cache.pop(old_cid, None)
        shape = image.shape
        if mask is not None and int(mask.sum()) > 0:
            self._viewer_indices = {'axial': int(max(range(shape[0]), key=lambda k: int(mask[k].sum()))), 'coronal': int(max(range(shape[1]), key=lambda k: int(mask[:, k, :].sum()))), 'sagittal': int(max(range(shape[2]), key=lambda k: int(mask[:, :, k].sum())))}
        else:
            self._viewer_indices = {'axial': shape[0] // 2, 'coronal': shape[1] // 2, 'sagittal': shape[2] // 2}
        self._update_slice_controls()
        self.viewer_info.configure(text=f'{cid} · {shape[2]}×{shape[1]}×{shape[0]} · {self._viewer_source}')
        qc = [f'Case: {cid}', f'Volume: {shape[2]}×{shape[1]}×{shape[0]}', f'Spacing: {self._viewer_spacing[0]:.3g}×{self._viewer_spacing[1]:.3g}×{self._viewer_spacing[2]:.3g} mm' if self._viewer_spacing else 'unavailable']
        if mask is None:
            qc += ['CT only', 'Mask appears after segmentation']
        else:
            voxels = int(mask.sum())
            qc += [f'Voxels: {voxels:,}', 'Non-empty, pass' if voxels > 0 else 'Empty Mask, fail']
            if 0 < voxels < 100:
                qc.append('Small lesion; review carefully')
        self.viewer_qc.configure(state='normal')
        self.viewer_qc.delete('1.0', 'end')
        self.viewer_qc.insert('end', '\n'.join(qc))
        self.viewer_qc.configure(state='disabled')
        self._draw_viewer()
        self._rebuild_3d_preview()

    def _plane_key(self) -> str:
        value = self.plane_var.get()
        if value.startswith('Coronal'):
            return 'coronal'
        if value.startswith('Sagittal'):
            return 'sagittal'
        return 'axial'

    def _plane_size(self, plane: str) -> int:
        if self._viewer_image is None:
            return 0
        return {'axial': self._viewer_image.shape[0], 'coronal': self._viewer_image.shape[1], 'sagittal': self._viewer_image.shape[2]}[plane]

    def _update_slice_controls(self) -> None:
        if self._viewer_image is None:
            self.slice_scale.configure(from_=0, to=0)
            self.slice_label.configure(text='-- / --')
            return
        plane = self._plane_key()
        size = max(1, self._plane_size(plane))
        self.slice_scale.configure(from_=0, to=size - 1)
        self.slice_scale.set(max(0, min(size - 1, self._viewer_indices.get(plane, size // 2))))

    def _plane_changed(self, _event: Any=None) -> None:
        self._update_slice_controls()
        self._draw_viewer()

    def _step_slice(self, delta: int) -> None:
        if self._viewer_image is None:
            return
        plane = self._plane_key()
        size = max(1, self._plane_size(plane))
        value = max(0, min(size - 1, int(round(float(self.slice_scale.get()))) + int(delta)))
        self.slice_scale.set(value)
        self._draw_viewer()

    def _wheel_viewer(self, event: tk.Event) -> str:
        delta = getattr(event, 'delta', 0)
        if delta:
            self._step_slice(1 if delta > 0 else -1)
        return 'break'

    def _refresh_viewer(self) -> None:
        self._draw_viewer()

    def _slice_array(self, array: Any, plane: str, index: int) -> Any:
        if plane == 'axial':
            return array[index, :, :]
        if plane == 'coronal':
            return array[:, index, :]
        return array[:, :, index]

    def _render_slice(self, array: Any, mask: Any, plane: str, index: int) -> Any:
        import numpy as np
        arr = self._slice_array(array, plane, index)
        width = safe_float(self.window_var.get()) or 300.0
        level = safe_float(self.level_var.get()) or 25.0
        (lo, hi) = (level - width / 2.0, level + width / 2.0)
        gray = ((arr - lo) / max(hi - lo, 1e-06) * 255).clip(0, 255).astype('uint8')
        rgb = Image.fromarray(gray, mode='L').convert('RGBA')
        if mask is not None:
            m = self._slice_array(mask, plane, index).astype(bool)
            red = Image.new('RGBA', rgb.size, (255, 45, 66, 0))
            red.putalpha(Image.fromarray(m.astype('uint8') * 100, mode='L'))
            rgb = Image.alpha_composite(rgb, red)
            edge = m.copy()
            if edge.shape[0] > 1:
                edge[1:, :] |= m[1:, :] ^ m[:-1, :]
            if edge.shape[1] > 1:
                edge[:, 1:] |= m[:, 1:] ^ m[:, :-1]
            draw = ImageDraw.Draw(rgb)
            (yy, xx) = np.where(edge & m)
            if len(xx):
                draw.point(list(zip(xx.tolist(), yy.tolist())), fill=(255, 230, 65, 255))
        return rgb.convert('RGB')

    def _draw_viewer(self) -> None:
        if self._viewer_image is None or Image is None:
            self.image_canvas.delete('all')
            self.image_canvas.create_text(300, 250, text='Select a CT folder; Mask will overlay after segmentation.', fill='#829ab6', font=('Segoe UI', 12))
            return
        try:
            import numpy as np
            plane = self._plane_key()
            index = int(round(float(self.slice_scale.get())))
            index = max(0, min(index, self._plane_size(plane) - 1))
            self._viewer_indices[plane] = index
            if self.view_mode_var.get().startswith('Three views'):
                cw = max(660, self.image_canvas.winfo_width() - 24)
                ch = max(360, self.image_canvas.winfo_height() - 24)
                canvas_img = Image.new('RGB', (cw, ch), (2, 6, 12))
                labels = (('Axial', 'axial'), ('Coronal / Coronal', 'coronal'), ('Sagittal / Sagittal', 'sagittal'))
                panel_w = max(180, (cw - 32) // 3)
                for (j, (label, key)) in enumerate(labels):
                    idx = self._viewer_indices[key]
                    panel = self._render_slice(self._viewer_image, self._viewer_mask if self.mask_visible_var.get() else None, key, idx)
                    panel.thumbnail((panel_w, max(180, ch - 42)), Image.Resampling.BILINEAR)
                    x = 8 + j * (panel_w + 8) + (panel_w - panel.width) // 2
                    y = 26 + (ch - 26 - panel.height) // 2
                    canvas_img.paste(panel, (x, y))
                    ImageDraw.Draw(canvas_img).text((8 + j * (panel_w + 8), 7), f'{label}  {idx + 1}/{self._plane_size(key)}', fill=(210, 225, 245))
                shown = canvas_img
                self.slice_label.configure(text=f'Three views / Current: {self.plane_var.get()} {index + 1}/{self._plane_size(plane)}')
            else:
                rendered = self._render_slice(self._viewer_image, self._viewer_mask if self.mask_visible_var.get() else None, plane, index)
                cw = max(320, self.image_canvas.winfo_width() - 24)
                ch = max(320, self.image_canvas.winfo_height() - 24)
                scale = min(cw / rendered.width, ch / rendered.height)
                shown = rendered.resize((max(1, int(rendered.width * scale)), max(1, int(rendered.height * scale))), Image.Resampling.BILINEAR)
                self.slice_label.configure(text=f'{self.plane_var.get()} · {index + 1} / {self._plane_size(plane)}')
            self._viewer_photo = ImageTk.PhotoImage(shown)
            self.image_canvas.delete('all')
            self.image_canvas.create_image(self.image_canvas.winfo_width() // 2, self.image_canvas.winfo_height() // 2, image=self._viewer_photo, anchor='center')
        except Exception as exc:
            self.image_canvas.delete('all')
            self.image_canvas.create_text(300, 250, text=f'Display failed: {exc}', fill='#f29a9a', font=('Segoe UI', 10))

    def _rebuild_3d_preview(self) -> None:
        """Render an embedded, rotatable CT-plane + 3D Mask view.

        The old detached 3D window is intentionally gone.  This panel keeps
        the tumour anchored to three CT orthogonal planes, so rotation remains
        anatomically interpretable instead of showing an isolated red surface.
        """
        if not hasattr(self, 'viewer_3d_frame'):
            return
        if self._viewer_3d_canvas is not None:
            try:
                self._viewer_3d_canvas.get_tk_widget().destroy()
            except Exception:
                pass
            self._viewer_3d_canvas = None
        if self._viewer_3d_figure is not None:
            try:
                import matplotlib.pyplot as plt
                plt.close(self._viewer_3d_figure)
            except Exception:
                pass
            self._viewer_3d_figure = None
        if self._viewer_image is None or self._viewer_mask is None or int(self._viewer_mask.sum()) == 0:
            self.viewer_3d_placeholder.pack(fill='both', expand=True, padx=10, pady=10)
            return
        self.viewer_3d_placeholder.pack_forget()
        try:
            import numpy as np
            import matplotlib
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            from matplotlib import colormaps
            from skimage.measure import marching_cubes
            matplotlib.rcParams['font.sans-serif'] = ['Segoe UI', 'SimHei', 'DejaVu Sans']
            matplotlib.rcParams['axes.unicode_minus'] = False
            mask = np.asarray(self._viewer_mask, dtype=bool)
            image = np.asarray(self._viewer_image, dtype=np.float32)
            coords = np.argwhere(mask)
            mins = np.maximum(coords.min(axis=0) - 6, 0)
            maxs = np.minimum(coords.max(axis=0) + 7, np.asarray(mask.shape))
            crop_mask = mask[mins[0]:maxs[0], mins[1]:maxs[1], mins[2]:maxs[2]]
            crop_image = image[mins[0]:maxs[0], mins[1]:maxs[1], mins[2]:maxs[2]]
            max_dim = max(crop_mask.shape)
            step = max(1, int(np.ceil(max_dim / 96.0)))
            small_mask = crop_mask[::step, ::step, ::step]
            (verts, faces, _normals, _values) = marching_cubes(small_mask.astype(np.float32), 0.5)
            verts = verts * step + mins
            fig = Figure(figsize=(3.8, 3.55), dpi=100, facecolor='#ffffff')
            ax = fig.add_subplot(111, projection='3d')
            ax.set_facecolor('#ffffff')
            if bool(self.mask_visible_var.get()):
                ax.plot_trisurf(verts[:, 2], verts[:, 1], verts[:, 0], triangles=faces, color='#f6a6a6', alpha=0.48, linewidth=0.04, edgecolor='#c96a6a', shade=True)
            z0 = int(self._viewer_indices.get('axial', coords[:, 0].max()))
            y0 = int(self._viewer_indices.get('coronal', coords[:, 1].mean()))
            x0 = int(self._viewer_indices.get('sagittal', coords[:, 2].mean()))
            z0 = max(int(mins[0]), min(int(maxs[0] - 1), z0))
            y0 = max(int(mins[1]), min(int(maxs[1] - 1), y0))
            x0 = max(int(mins[2]), min(int(maxs[2] - 1), x0))
            norm = lambda a: np.clip((a - (safe_float(self.level_var.get()) or 25.0) + (safe_float(self.window_var.get()) or 300.0) / 2.0) / max(safe_float(self.window_var.get()) or 300.0, 1e-06), 0, 1)
            cmap = colormaps.get_cmap('gray')
            xs = np.arange(mins[2], maxs[2], max(1, step))
            ys = np.arange(mins[1], maxs[1], max(1, step))
            zs = np.arange(mins[0], maxs[0], max(1, step))
            (X, Y) = np.meshgrid(xs, ys)
            Z = np.full_like(X, z0, dtype=float)
            ax.plot_surface(X, Y, Z, facecolors=cmap(norm(image[z0][np.ix_(ys, xs)])), rstride=1, cstride=1, shade=False, alpha=0.28, linewidth=0)
            (X2, Z2) = np.meshgrid(xs, zs)
            Y2 = np.full_like(X2, y0, dtype=float)
            coronal_values = image[np.ix_(zs, [y0], xs)][:, 0, :]
            ax.plot_surface(X2, Y2, Z2, facecolors=cmap(norm(coronal_values)), rstride=1, cstride=1, shade=False, alpha=0.2, linewidth=0)
            (Y3, Z3) = np.meshgrid(ys, zs)
            X3 = np.full_like(Y3, x0, dtype=float)
            sagittal_values = image[np.ix_(zs, ys, [x0])][:, :, 0]
            ax.plot_surface(X3, Y3, Z3, facecolors=cmap(norm(sagittal_values)), rstride=1, cstride=1, shade=False, alpha=0.2, linewidth=0)
            ax.set_xlim(mins[2], maxs[2])
            ax.set_ylim(mins[1], maxs[1])
            ax.set_zlim(mins[0], maxs[0])
            ax.set_xlabel('X', labelpad=0, fontsize=7)
            ax.set_ylabel('Y', labelpad=0, fontsize=7)
            ax.set_zlabel('Z', labelpad=0, fontsize=7)
            ax.set_title('CT planes + 3D Mask', color='#102a43', pad=4, fontsize=8)
            try:
                ax.set_box_aspect((max(crop_mask.shape[2], 1), max(crop_mask.shape[1], 1), max(crop_mask.shape[0], 1)))
            except Exception:
                pass
            canvas = FigureCanvasTkAgg(fig, master=self.viewer_3d_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
            toolbar = NavigationToolbar2Tk(canvas, self.viewer_3d_frame, pack_toolbar=False)
            toolbar.update()
            toolbar.pack(fill='x')
            self._viewer_3d_canvas = canvas
            self._viewer_3d_figure = fig
        except Exception as exc:
            self.viewer_3d_placeholder.configure(text=f'3D view failed:\n{type(exc).__name__}: {exc}')
            self.viewer_3d_placeholder.pack(fill='both', expand=True, padx=10, pady=10)

    def open_output(self) -> None:
        path = self._current_output or Path(self.output_var.get())
        if path.exists():
            os.startfile(str(path))

    def open_report(self) -> None:
        path = (self._current_output or Path(self.output_var.get())) / 'OHP_result_report.html'
        if path.exists():
            os.startfile(str(path))

    def copy_batch(self) -> None:
        if self.batch_var.get() and self.batch_var.get() != 'Not created':
            self.clipboard_clear()
            self.clipboard_append(self.batch_var.get())
            self.status_var.set('Batch ID copied')

    def clear_workspace(self) -> None:
        if self._running:
            messagebox.showinfo('Analysis running', 'Stop the current task first.')
            return
        self.input_var.set('')
        self._case_ids = []
        self._case_rows = []
        self.case_count_var.set('0 cases')
        self.batch_var.set('Not created')
        self.quality_var.set('Not QC-checked')
        self.status_var.set('Ready: select a DICOM folder')
        self.header_status.configure(text='Ready', fg='#74e5d6')
        self._clear_results()

    def on_close(self) -> None:
        if self._running and self._process is not None:
            if not messagebox.askyesno('Exit', 'An analysis is still running. Exit and stop the task?'):
                return
            self._process.terminate()
        self.destroy()

def self_test() -> int:
    required = [ROOT / 'run_ohp_publication.py', Path(sys.executable), ROOT / 'assets', ROOT / 'models']
    missing = [str(p) for p in required if not p.exists()]
    if Image is None:
        missing.append('Pillow')
    if missing:
        print('SELF_TEST_FAIL')
        for p in missing:
            print('MISSING', p)
        return 1
    print('SELF_TEST_OK')
    print('ROOT', ROOT)
    print('MIN_CASES', MIN_CASES)
    print('PYTHON', PYTHON)
    return 0
if __name__ == '__main__':
    if '--self-test' in sys.argv:
        raise SystemExit(self_test())
    app = OHPApp()
    app.mainloop()
