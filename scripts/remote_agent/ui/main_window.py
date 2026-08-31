"""Small, visible Tkinter window backed by a headless-testable view model."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.remote_agent.lifecycle import CloseMode, LifecycleController
from scripts.remote_agent.models import AgentState


@dataclass(frozen=True)
class WindowSnapshot:
    machine_id: str
    agent_state: AgentState
    status_message: str
    resolve_state: str
    allowed_aliases: tuple[str, ...]
    current_job: str
    last_job: str
    recent_logs: tuple[str, ...]


class MainWindowModel:
    def __init__(self, controller: LifecycleController) -> None:
        self.controller = controller

    def snapshot(self) -> WindowSnapshot:
        value = self.controller.snapshot()
        last = value.last_job
        if value.last_job_status is not None and last != "-":
            last = f"{last} ({value.last_job_status.value})"
        return WindowSnapshot(
            machine_id=value.machine_id,
            agent_state=value.state,
            status_message=value.status_message,
            resolve_state=value.resolve_state,
            allowed_aliases=value.allowed_aliases,
            current_job=value.current_job,
            last_job=last,
            recent_logs=value.recent_logs,
        )


class MainWindow:
    REFRESH_MS = 500

    def __init__(self, controller: LifecycleController, *, root=None) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._tk = tk
        self._ttk = ttk
        self._root = root or tk.Tk()
        self._controller = controller
        self._model = MainWindowModel(controller)
        self._closing = False
        self._root.title("ARPHE Remote Agent")
        self._root.minsize(720, 520)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        frame = ttk.Frame(self._root, padding=16)
        frame.pack(fill="both", expand=True)
        self._values = {
            name: tk.StringVar(value="-")
            for name in ("machine", "agent", "resolve", "aliases", "current", "last")
        }
        labels = (
            ("Machine ID", "machine"),
            ("Agent state", "agent"),
            ("Resolve state", "resolve"),
            ("Allowed folder aliases", "aliases"),
            ("Current job", "current"),
            ("Last job", "last"),
        )
        for row, (label, key) in enumerate(labels):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 14), pady=4)
            ttk.Label(frame, textvariable=self._values[key], wraplength=500).grid(
                row=row, column=1, sticky="nw", pady=4
            )

        controls = ttk.Frame(frame)
        controls.grid(row=len(labels), column=0, columnspan=2, sticky="w", pady=(16, 8))
        self._pause_button = ttk.Button(controls, text="Pause jobs", command=self._toggle_pause)
        self._pause_button.pack(side="left", padx=(0, 8))
        ttk.Button(
            controls, text="Stop after current job", command=self._controller.stop_after_current
        ).pack(side="left")

        ttk.Label(frame, text="Recent local lifecycle logs").grid(
            row=len(labels) + 1, column=0, columnspan=2, sticky="w", pady=(12, 4)
        )
        self._logs = tk.Text(frame, height=12, state="disabled", wrap="word")
        self._logs.grid(row=len(labels) + 2, column=0, columnspan=2, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(len(labels) + 2, weight=1)

    def run(self) -> None:
        # The worker gate opens only after Tk has realized and displayed the window.
        self._root.update_idletasks()
        self._root.deiconify()
        self._root.update_idletasks()
        self._controller.start(ui_visible=bool(self._root.winfo_viewable()))
        self._refresh()
        try:
            self._root.mainloop()
        finally:
            # A Tk loop can return for reasons other than WM_DELETE_WINDOW.
            # The visible window remains the hard lifetime boundary for polling.
            self._controller.shutdown()

    def _refresh(self) -> None:
        snapshot = self._model.snapshot()
        self._values["machine"].set(snapshot.machine_id)
        self._values["agent"].set(f"{snapshot.agent_state.value} - {snapshot.status_message}")
        self._values["resolve"].set(snapshot.resolve_state)
        self._values["aliases"].set(", ".join(snapshot.allowed_aliases))
        self._values["current"].set(snapshot.current_job)
        self._values["last"].set(snapshot.last_job)
        self._pause_button.configure(
            text="Resume jobs" if snapshot.agent_state is AgentState.PAUSED else "Pause jobs"
        )
        self._logs.configure(state="normal")
        self._logs.delete("1.0", "end")
        self._logs.insert("1.0", "\n".join(snapshot.recent_logs))
        self._logs.configure(state="disabled")
        if self._closing and not self._controller.worker_alive:
            self._root.destroy()
            return
        self._root.after(self.REFRESH_MS, self._refresh)

    def _toggle_pause(self) -> None:
        if self._controller.state is AgentState.PAUSED:
            self._controller.resume()
        else:
            self._controller.pause()

    def _on_close(self) -> None:
        from tkinter import messagebox

        try:
            may_close = self._controller.request_close()
        except ValueError:
            answer = messagebox.askyesnocancel(
                "Job in progress",
                "Finish the current job before closing?\n"
                "Yes: finish then close\nNo: abort cooperatively then close",
                parent=self._root,
            )
            if answer is None:
                return
            mode = CloseMode.FINISH_CURRENT if answer else CloseMode.ABORT_CURRENT
            may_close = self._controller.request_close(mode)
        if may_close:
            self._root.destroy()
        else:
            self._closing = True
