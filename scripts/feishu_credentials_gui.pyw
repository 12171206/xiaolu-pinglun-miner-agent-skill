#!/usr/bin/env python3
"""Small local-only GUI for saving a Feishu App Secret with Windows DPAPI."""

from __future__ import annotations

import argparse
import tkinter as tk
from tkinter import messagebox

from feishu_credentials import save_credentials


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", required=True)
    args = parser.parse_args()

    root = tk.Tk()
    root.title("飞书连接器安全设置")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    frame = tk.Frame(root, padx=22, pady=18)
    frame.pack()

    tk.Label(frame, text="飞书评论选题连接器", font=("Microsoft YaHei UI", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
    )
    tk.Label(frame, text="App ID").grid(row=1, column=0, sticky="w", pady=5)
    app_id = tk.Entry(frame, width=42)
    app_id.insert(0, args.app_id)
    app_id.configure(state="readonly")
    app_id.grid(row=1, column=1, pady=5)

    tk.Label(frame, text="新 App Secret").grid(row=2, column=0, sticky="w", pady=5)
    secret = tk.Entry(frame, width=42, show="●")
    secret.grid(row=2, column=1, pady=5)

    tk.Label(frame, text="再次输入").grid(row=3, column=0, sticky="w", pady=5)
    confirmation = tk.Entry(frame, width=42, show="●")
    confirmation.grid(row=3, column=1, pady=5)

    hint = tk.Label(
        frame,
        text="密钥只保存在本机，并由当前 Windows 账户加密。\n请先在飞书后台重置已暴露的旧密钥。",
        fg="#555555",
        justify="left",
    )
    hint.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 14))

    def save() -> None:
        value = secret.get().strip()
        if not value:
            messagebox.showerror("无法保存", "App Secret 不能为空。", parent=root)
            return
        if value != confirmation.get().strip():
            messagebox.showerror("无法保存", "两次输入不一致。", parent=root)
            return
        try:
            save_credentials(args.app_id, value)
        except Exception as exc:  # noqa: BLE001 - show a local setup error to the user.
            messagebox.showerror("保存失败", str(exc), parent=root)
            return
        secret.delete(0, tk.END)
        confirmation.delete(0, tk.END)
        messagebox.showinfo("保存成功", "飞书凭证已在本机加密保存。", parent=root)
        root.destroy()

    buttons = tk.Frame(frame)
    buttons.grid(row=5, column=0, columnspan=2, sticky="e")
    tk.Button(buttons, text="取消", width=10, command=root.destroy).pack(side="right", padx=(8, 0))
    tk.Button(buttons, text="安全保存", width=12, command=save).pack(side="right")

    secret.focus_set()
    root.bind("<Return>", lambda _event: save())
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
