#!/usr/bin/env python3
"""Tkinter GUI for RenderDocExtract configuration and execution."""

from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

import app_config

PROJECT_ROOT = app_config.PROJECT_ROOT
SCRIPT_DIR = PROJECT_ROOT / "Scripts"


class ScrollText(ttk.Frame):
    def __init__(self, master: tk.Misc, height: int = 14) -> None:
        super().__init__(master)
        self.text = tk.Text(self, height=height, wrap="word")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def append(self, message: str) -> None:
        self.text.insert("end", message)
        self.text.see("end")

    def clear(self) -> None:
        self.text.delete("1.0", "end")


class RenderDocExtractGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("RenderDocExtract GUI")
        self.geometry("1120x780")
        self.proc: Optional[subprocess.Popen[str]] = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.vars: Dict[str, tk.Variable] = {}
        self._build_ui()
        self.load_settings()
        self.after(100, self._poll_output)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        config_frame = ttk.LabelFrame(root, text="参数配置", padding=10)
        config_frame.grid(row=0, column=0, sticky="ew")
        for col in (1,):
            config_frame.columnconfigure(col, weight=1)

        row = 0
        row = self._add_path_row(config_frame, row, "RDC 文件", "rdc", filetypes=[("RenderDoc Capture", "*.rdc"), ("All files", "*.*")])
        row = self._add_entry_row(config_frame, row, "EID", "eid", width=18)
        row = self._add_path_row(config_frame, row, "输出目录", "out", directory=True)
        row = self._add_path_row(config_frame, row, "qrenderdoc.exe", "qrenderdoc", filetypes=[("qrenderdoc", "qrenderdoc.exe"), ("Executable", "*.exe"), ("All files", "*.*")])
        row = self._add_path_row(config_frame, row, "renderdoc.exe", "renderdoc", filetypes=[("renderdoc", "renderdoc.exe"), ("Executable", "*.exe"), ("All files", "*.*")])
        row = self._add_path_row(config_frame, row, "HLSLDecompiler.exe", "decompiler", filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        row = self._add_path_row(config_frame, row, "GBuffer Layout JSON", "gbuffer_layouts", filetypes=[("JSON", "*.json"), ("All files", "*.*")])

        advanced = ttk.Frame(config_frame)
        advanced.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for col in range(8):
            advanced.columnconfigure(col, weight=1)

        self._var("step_timeout", "1800")
        ttk.Label(advanced, text="Step Timeout").grid(row=0, column=0, sticky="w")
        ttk.Entry(advanced, textvariable=self.vars["step_timeout"], width=10).grid(row=0, column=1, sticky="w", padx=(4, 14))

        self._var("mesh_unit", "cm")
        ttk.Label(advanced, text="Mesh Unit").grid(row=0, column=2, sticky="w")
        ttk.Combobox(advanced, textvariable=self.vars["mesh_unit"], values=["cm", "m"], width=6, state="readonly").grid(row=0, column=3, sticky="w", padx=(4, 14))

        self._var("mesh_max_indices", "200000")
        ttk.Label(advanced, text="Max Indices").grid(row=0, column=4, sticky="w")
        ttk.Entry(advanced, textvariable=self.vars["mesh_max_indices"], width=12).grid(row=0, column=5, sticky="w", padx=(4, 14))

        self._var("mesh_json_vertex_limit", "256")
        ttk.Label(advanced, text="JSON Vertex Limit").grid(row=0, column=6, sticky="w")
        ttk.Entry(advanced, textvariable=self.vars["mesh_json_vertex_limit"], width=8).grid(row=0, column=7, sticky="w", padx=(4, 0))

        self._var("texture_lib", "")
        ttk.Label(advanced, text="Texture Lib").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(advanced, textvariable=self.vars["texture_lib"]).grid(row=1, column=1, columnspan=4, sticky="ew", padx=(4, 4), pady=(8, 0))
        ttk.Button(advanced, text="选择", command=lambda: self._choose_directory("texture_lib")).grid(row=1, column=5, sticky="w", pady=(8, 0))

        self._bool_var("textures_only_used", True)
        ttk.Checkbutton(advanced, text="只提取 used textures", variable=self.vars["textures_only_used"]).grid(row=1, column=6, columnspan=2, sticky="w", pady=(8, 0))

        self._bool_var("no_log", False)
        ttk.Checkbutton(advanced, text="禁用日志文件", variable=self.vars["no_log"]).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self._bool_var("run_svt_reconstruction", True)
        ttk.Checkbutton(advanced, text="SVT 贴图重建", variable=self.vars["run_svt_reconstruction"]).grid(row=2, column=2, columnspan=2, sticky="w", pady=(8, 0))

        self._var("primitive_sample_count", "64")
        ttk.Label(advanced, text="Primitive samples").grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(advanced, textvariable=self.vars["primitive_sample_count"], width=8).grid(row=2, column=3, sticky="w", padx=(4, 14), pady=(8, 0))

        self._var("renderdoc_module_dirs", "")
        ttk.Label(advanced, text="RenderDoc module dirs ;").grid(row=2, column=4, sticky="w", pady=(8, 0))
        ttk.Entry(advanced, textvariable=self.vars["renderdoc_module_dirs"]).grid(row=2, column=5, columnspan=3, sticky="ew", padx=(4, 0), pady=(8, 0))

        self.log = ScrollText(root, height=22)
        self.log.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        actions = ttk.Frame(root)
        actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        actions.columnconfigure(8, weight=1)
        ttk.Button(actions, text="保存配置", command=self.save_settings).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(actions, text="重新加载", command=self.load_settings).grid(row=0, column=1, padx=(0, 6))
        self.run_button = ttk.Button(actions, text="运行完整提取", command=self.run_extraction)
        self.run_button.grid(row=0, column=2, padx=(0, 6))
        self.stop_button = ttk.Button(actions, text="停止运行", command=self.stop_process, state="disabled")
        self.stop_button.grid(row=0, column=3, padx=(0, 6))
        ttk.Button(actions, text="打开输出目录", command=lambda: self._open_path(self.vars["out"].get())).grid(row=0, column=4, padx=(0, 6))
        ttk.Button(actions, text="打开日志目录", command=lambda: self._open_path(str(app_config.LOG_DIR))).grid(row=0, column=5, padx=(0, 6))
        ttk.Button(actions, text="清空输出", command=self.log.clear).grid(row=0, column=6, padx=(0, 6))

        status_frame = ttk.Frame(root)
        status_frame.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        status_frame.columnconfigure(1, weight=1)
        ttk.Label(status_frame, text="配置文件:").grid(row=0, column=0, sticky="w")
        self.config_label = ttk.Label(status_frame, text=str(app_config.DEFAULT_SETTINGS_PATH))
        self.config_label.grid(row=0, column=1, sticky="w")

    def _var(self, name: str, default: str = "") -> tk.StringVar:
        var = tk.StringVar(value=default)
        self.vars[name] = var
        return var

    def _bool_var(self, name: str, default: bool = False) -> tk.BooleanVar:
        var = tk.BooleanVar(value=default)
        self.vars[name] = var
        return var

    def _add_entry_row(self, parent: ttk.Frame, row: int, label: str, key: str, width: int = 80) -> int:
        self._var(key, "")
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=self.vars[key], width=width).grid(row=row, column=1, sticky="ew", padx=(8, 4), pady=2)
        return row + 1

    def _add_path_row(self, parent: ttk.Frame, row: int, label: str, key: str, directory: bool = False, filetypes: Optional[List[tuple[str, str]]] = None) -> int:
        self._var(key, "")
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", padx=(8, 4), pady=2)
        cmd = (lambda k=key: self._choose_directory(k)) if directory else (lambda k=key, ft=filetypes: self._choose_file(k, ft))
        ttk.Button(parent, text="选择", command=cmd).grid(row=row, column=2, sticky="e", pady=2)
        return row + 1

    def _choose_file(self, key: str, filetypes: Optional[List[tuple[str, str]]] = None) -> None:
        initial = self.vars[key].get() if key in self.vars else ""
        path = filedialog.askopenfilename(initialdir=str(Path(initial).parent) if initial else str(PROJECT_ROOT), filetypes=filetypes or [("All files", "*.*")])
        if path:
            self.vars[key].set(path)

    def _choose_directory(self, key: str) -> None:
        initial = self.vars[key].get() if key in self.vars else ""
        path = filedialog.askdirectory(initialdir=initial or str(PROJECT_ROOT))
        if path:
            self.vars[key].set(path)

    def settings_from_ui(self) -> app_config.AppSettings:
        data = {
            "rdc": self.vars["rdc"].get(),
            "eid": self.vars["eid"].get(),
            "out": self.vars["out"].get(),
            "qrenderdoc": self.vars["qrenderdoc"].get(),
            "renderdoc": self.vars["renderdoc"].get(),
            "decompiler": self.vars["decompiler"].get(),
            "gbuffer_layouts": self.vars["gbuffer_layouts"].get(),
            "step_timeout": self.vars["step_timeout"].get(),
            "no_log": bool(self.vars["no_log"].get()),
            "mesh_unit": self.vars["mesh_unit"].get(),
            "mesh_max_indices": self.vars["mesh_max_indices"].get(),
            "mesh_json_vertex_limit": self.vars["mesh_json_vertex_limit"].get(),
            "texture_lib": self.vars["texture_lib"].get(),
            "textures_only_used": bool(self.vars["textures_only_used"].get()),
            "primitive_sample_count": self.vars["primitive_sample_count"].get(),
            "renderdoc_module_dirs": app_config.split_path_list(self.vars["renderdoc_module_dirs"].get()),
            "run_svt_reconstruction": bool(self.vars["run_svt_reconstruction"].get()),
        }
        return app_config._coerce_settings(data)  # Shared validation/coercion for the GUI.

    def load_settings(self) -> None:
        settings = app_config.ensure_settings()
        self.vars["rdc"].set(settings.rdc)
        self.vars["eid"].set(str(settings.eid))
        self.vars["out"].set(settings.out)
        self.vars["qrenderdoc"].set(settings.qrenderdoc)
        self.vars["renderdoc"].set(settings.renderdoc)
        self.vars["decompiler"].set(settings.decompiler)
        self.vars["gbuffer_layouts"].set(settings.gbuffer_layouts)
        self.vars["step_timeout"].set(str(settings.step_timeout))
        self.vars["no_log"].set(settings.no_log)
        self.vars["mesh_unit"].set(settings.mesh_unit)
        self.vars["mesh_max_indices"].set(str(settings.mesh_max_indices))
        self.vars["mesh_json_vertex_limit"].set(str(settings.mesh_json_vertex_limit))
        self.vars["texture_lib"].set(settings.texture_lib)
        self.vars["textures_only_used"].set(settings.textures_only_used)
        self.vars["primitive_sample_count"].set(str(settings.primitive_sample_count))
        self.vars["renderdoc_module_dirs"].set(app_config.join_path_list(settings.renderdoc_module_dirs))
        self.vars["run_svt_reconstruction"].set(settings.run_svt_reconstruction)
        self.log.append(f"Loaded settings: {app_config.DEFAULT_SETTINGS_PATH}\n")

    def save_settings(self) -> None:
        settings = self.settings_from_ui()
        app_config.save_settings(settings)
        self.log.append(f"Saved settings: {app_config.DEFAULT_SETTINGS_PATH}\n")

    def validate_settings(self, settings: app_config.AppSettings) -> bool:
        required_files = {
            "RDC 文件": settings.rdc,
            "qrenderdoc.exe": settings.qrenderdoc,
            "GBuffer layout JSON": settings.gbuffer_layouts,
        }
        missing = [f"{label}: {path}" for label, path in required_files.items() if path and not Path(path).exists()]
        if settings.decompiler and not Path(settings.decompiler).exists():
            missing.append(f"HLSLDecompiler.exe: {settings.decompiler}")
        if missing:
            messagebox.showerror("路径不存在", "以下路径不存在:\n\n" + "\n".join(missing))
            return False
        if settings.step_timeout <= 0:
            messagebox.showerror("参数错误", "Step timeout 必须大于 0")
            return False
        return True

    def build_command(self, settings: app_config.AppSettings) -> List[str]:
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "extract_eid.py"),
            "--rdc", settings.rdc,
            "--eid", str(settings.eid),
            "--out", settings.out,
            "--qrenderdoc", settings.qrenderdoc,
            "--renderdoc", settings.renderdoc,
            "--decompiler", settings.decompiler,
            "--gbuffer-layouts", settings.gbuffer_layouts,
            "--unit", settings.mesh_unit,
            "--max-indices", str(settings.mesh_max_indices),
            "--json-vertex-limit", str(settings.mesh_json_vertex_limit),
            "--primitive-sample-count", str(settings.primitive_sample_count),
            "--step-timeout", str(settings.step_timeout),
        ]
        if settings.texture_lib:
            cmd.extend(["--texture-lib", settings.texture_lib])
        cmd.append("--only-used" if settings.textures_only_used else "--all-bound")
        if settings.no_log:
            cmd.append("--no-log")
        for module_dir in settings.renderdoc_module_dirs:
            cmd.extend(["--renderdoc-module-dir", module_dir])
        # SVT reconstruction
        if settings.run_svt_reconstruction:
            cmd.append("--run-svt-reconstruction")
        else:
            cmd.append("--no-svt-reconstruction")
        return cmd

    def run_extraction(self) -> None:
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("正在运行", "当前已有任务正在运行")
            return
        settings = self.settings_from_ui()
        if not self.validate_settings(settings):
            return
        app_config.save_settings(settings)
        cmd = self.build_command(settings)
        self.log.append("\n=== Run extract_eid.py ===\n")
        self.log.append(" ".join(f'"{c}"' if " " in c else c for c in cmd) + "\n")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            self.run_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            messagebox.showerror("启动失败", str(exc))
            return
        threading.Thread(target=self._reader_thread, daemon=True).start()

    def _reader_thread(self) -> None:
        assert self.proc is not None
        if self.proc.stdout is not None:
            for line in self.proc.stdout:
                self.output_queue.put(line)
        code = self.proc.wait()
        self.output_queue.put(f"\n=== Process exited: {code} ===\n")
        self.output_queue.put("__PROCESS_DONE__")

    def _poll_output(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if item == "__PROCESS_DONE__":
                    self.run_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.proc = None
                else:
                    self.log.append(item)
        except queue.Empty:
            pass
        self.after(100, self._poll_output)

    def stop_process(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.log.append("\nStopping process...\n")
            try:
                self.proc.terminate()
            except Exception:
                self.proc.kill()

    def _open_path(self, path_text: str) -> None:
        path = Path(path_text)
        try:
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))


def main() -> int:
    app = RenderDocExtractGUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
