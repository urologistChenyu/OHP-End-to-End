"""Optional local operating settings panel for the OHP desktop application."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Any
from local_risk_settings import LocalSettings, DEFAULT_THRESHOLD, DEVELOPMENT_PREVALENCE, SOFTWARE_VERSION, calibration_csv, local_rows, export_local_settings


class LocalSettingsPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, on_export=None) -> None:
        super().__init__(parent, style='App.TFrame')
        self.on_export = on_export
        self.batch = None
        self.rows = []
        self.fit = None
        self.mode = tk.StringVar(value='none')
        self.threshold = tk.StringVar(value=str(DEFAULT_THRESHOLD))
        self.intercept = tk.StringVar(value='0')
        self.prevalence = tk.StringVar(value='')
        self.status = tk.StringVar(value='Original model settings. Load a completed batch to preview results.')
        self.fit_status = tk.StringVar(value='No local calibration data loaded.')
        self._build()
        self.mode.trace_add('write', lambda *_: self._update_mode())
        self._update_mode()
        self.bind("<Configure>", self._resize_text)

    def _resize_text(self, event) -> None:
        def visit(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label) and int(child.cget("wraplength") or 0) > 0:
                    child.configure(wraplength=max(260, event.width-36))
                visit(child)
        visit(self)

    def _build(self) -> None:
        card = ttk.Frame(self, style='Card.TFrame')
        card.pack(fill='x', pady=(0, 10))
        ttk.Label(card, text=f'Local Operating Settings · v{SOFTWARE_VERSION}', style='CardTitle.TLabel').pack(anchor='w', padx=18, pady=(16, 5))
        ttk.Label(card, text='Keep the original model output, or preview a local probability adjustment and decision threshold. Original results stay available in Overview and Branch Results.', style='CardMuted.TLabel', wraplength=980, justify='left').pack(anchor='w', padx=18, pady=(0, 12))
        controls = ttk.Frame(card, style='Card.TFrame')
        controls.pack(fill='x', padx=18)
        for col, (text, value) in enumerate([('Original probability', 'none'), ('Intercept update', 'intercept'), ('Prevalence scenario', 'prevalence')]):
            ttk.Radiobutton(controls, text=text, value=value, variable=self.mode).grid(row=0, column=col, padx=(0, 22), sticky='w')
        form = ttk.Frame(card, style='Card.TFrame')
        form.pack(fill='x', padx=18, pady=(13, 6))
        for col, text in enumerate(['Decision threshold (0–1)', 'Log-odds intercept', 'Local OHP prevalence (%)']):
            ttk.Label(form, text=text, style='Body.TLabel').grid(row=0, column=col, sticky='w', padx=(0, 18))
        self.threshold_entry = ttk.Entry(form, textvariable=self.threshold, width=24)
        self.intercept_entry = ttk.Entry(form, textvariable=self.intercept, width=24)
        self.prevalence_entry = ttk.Entry(form, textvariable=self.prevalence, width=24)
        for col, widget in enumerate([self.threshold_entry, self.intercept_entry, self.prevalence_entry]):widget.grid(row=1, column=col, sticky='w', padx=(0, 18), pady=(4, 0))
        self.mode_note = ttk.Label(card, style='CardMuted.TLabel', wraplength=980, justify='left')
        self.mode_note.pack(anchor='w', padx=18, pady=(6, 8))
        actions = ttk.Frame(card, style='Card.TFrame')
        actions.pack(fill='x', padx=18, pady=(0, 10))
        ttk.Button(actions, text='Fit intercept from local CSV', style='Secondary.TButton', command=self.load_fit).pack(side='left')
        self.preview_button = ttk.Button(actions, text='Apply Preview', style='Primary.TButton', command=self.preview, state='disabled')
        self.preview_button.pack(side='left', padx=8)
        self.export_button = ttk.Button(actions, text='Export Local Results', style='Secondary.TButton', command=self.export, state='disabled')
        self.export_button.pack(side='left')
        ttk.Button(actions, text='Restore Defaults', style='Secondary.TButton', command=self.reset).pack(side='right')
        ttk.Label(card, textvariable=self.fit_status, style='CardMuted.TLabel', wraplength=980).pack(anchor='w', padx=18, pady=(0, 5))
        ttk.Label(card, text='Local calibration CSV: fusion_prob and OHP (0/1); one row per unique case. Settings fitted on these cases need separate evaluation.', style='CardMuted.TLabel', wraplength=980, justify='left').pack(anchor='w', padx=18, pady=(0, 14))
        result = ttk.Frame(self, style='Card.TFrame')
        result.pack(fill='both', expand=True)
        ttk.Label(result, textvariable=self.status, style='Body.TLabel', wraplength=980).pack(anchor='w', padx=18, pady=(14, 10))
        table = ttk.Frame(result, style='Card.TFrame');table.pack(fill='both', expand=True, padx=18, pady=(0, 14))
        columns = ('case', 'raw', 'local', 'default_class', 'local_class')
        self.tree = ttk.Treeview(table, columns=columns, show='headings', height=8)
        for c, label, width in zip(columns, ['Case', 'Original OHP risk', 'Configured OHP risk', 'Default classification', 'Configured classification'], [150, 160, 160, 180, 180]):
            self.tree.heading(c, text=label);self.tree.column(c, width=width, minwidth=100, anchor='center')
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        xscroll = ttk.Scrollbar(table, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky='nsew');scroll.grid(row=0, column=1, sticky='ns');xscroll.grid(row=1, column=0, sticky='ew')
        table.columnconfigure(0, weight=1);table.rowconfigure(0, weight=1)

    def _update_mode(self) -> None:
        mode = self.mode.get()
        self.intercept_entry.configure(state='normal' if mode=='intercept' else 'disabled')
        self.prevalence_entry.configure(state='normal' if mode=='prevalence' else 'disabled')
        notes = {
            'none': 'Original probabilities are unchanged. The default threshold is 0.353054; a custom threshold changes classification only.',
            'intercept': 'Adjusted probability = logistic(logit(original probability) + intercept). Fit an intercept from local labelled data or enter an independently estimated value. This does not correct the calibration slope.',
            'prevalence': f'Source OHP prevalence: 114/296 ({100*DEVELOPMENT_PREVALENCE:.1f}%). This scenario assumes stable class-conditional predictor distributions and appropriate source probabilities; it is not a substitute for local calibration data.',
        }
        self.mode_note.configure(text=notes[mode])
        self.status.set('Settings changed. Select Apply Preview to refresh the table.' if self.rows else 'Load a completed batch to preview local settings.')

    def settings(self) -> LocalSettings:
        try:
            threshold = float(self.threshold.get())
            mode = self.mode.get()
            intercept = float(self.intercept.get()) if mode=='intercept' else 0.0
            prevalence = float(self.prevalence.get())/100 if mode=='prevalence' else None
        except ValueError:
            raise ValueError('Enter numeric settings. Prevalence is a percentage strictly between 0 and 100.') from None
        return LocalSettings(mode=mode, threshold=threshold, intercept=intercept, local_prevalence=prevalence)

    def set_batch(self, output: Path, rows: list[dict[str, Any]]) -> None:
        self.batch = Path(output);self.rows = [dict(x) for x in rows]
        self.preview_button.configure(state='normal' if self.rows else 'disabled')
        self.export_button.configure(state='normal' if self.rows else 'disabled')
        try:self.preview(show_error=False)
        except ValueError:self.status.set('Batch loaded. Check settings and select Apply Preview.')

    def clear_batch(self) -> None:
        self.batch = None;self.rows = []
        for item in self.tree.get_children():self.tree.delete(item)
        self.preview_button.configure(state='disabled');self.export_button.configure(state='disabled')
        self.status.set('Load a completed batch to preview local settings.')

    def preview(self, show_error: bool = True) -> list[dict[str, Any]] | None:
        try:
            settings = self.settings();rows = local_rows(self.rows, settings)
        except ValueError as exc:
            if show_error:messagebox.showerror('Check local settings', str(exc), parent=self)
            else:raise
            return None
        for item in self.tree.get_children():self.tree.delete(item)
        for row in rows:
            self.tree.insert('', 'end', values=(row['patient_id'], f"{100*row['raw_probability']:.2f}%", f"{100*row['configured_probability']:.2f}%", 'Higher risk' if row['raw_pred_default'] else 'Lower risk', 'Higher risk' if row['configured_pred'] else 'Lower risk'))
        changed = sum(r['raw_pred_default']!=r['configured_pred'] for r in rows)
        self.status.set(f'{len(rows)} cases · {settings.describe()} · threshold {settings.threshold:.6f} · {changed} classifications differ from default')
        return rows

    def load_fit(self) -> None:
        path = filedialog.askopenfilename(parent=self, title='Local calibration data', filetypes=[('CSV files', '*.csv')])
        if not path:return
        try:fit=calibration_csv(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Calibration data', str(exc), parent=self);return
        self.fit=fit;self.intercept.set(format(fit['intercept'], '.17g'));self.mode.set('intercept')
        self.fit_status.set(f"Intercept {fit['intercept']:.6f} fitted from {fit['n']} local cases ({fit['events']} OHP-positive). Separate evaluation is required.")
        if self.rows:self.preview()

    def reset(self) -> None:
        self.fit=None;self.intercept.set('0');self.prevalence.set('');self.threshold.set(str(DEFAULT_THRESHOLD));self.mode.set('none')
        self.fit_status.set('No local calibration data loaded.')
        if self.rows:self.preview()

    def export(self) -> None:
        if self.batch is None:return
        try:
            settings=self.settings()
            fit=self.fit if self.fit and settings.mode=='intercept' and abs(self.fit['intercept']-settings.intercept)<1e-12 else None
            result=export_local_settings(self.batch, settings, fit=fit)
            self.preview()
        except (OSError,ValueError,RuntimeError) as exc:
            messagebox.showerror('Local export', str(exc), parent=self);return
        if self.on_export:self.on_export(self.batch)
        self.status.set(f"Saved {result['cases']} local results in the batch's local_settings folder. Original files are unchanged.")
