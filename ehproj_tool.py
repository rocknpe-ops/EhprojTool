# -*- coding: utf-8 -*-
"""像塑工程入口文件转换工具
1. 将目录下的 .dyehpj 文件复制一份为 .ehproj，并把其中
   "version": "xxxx" 字段修改为 "version": "5.5.2" 后保存。
2. 遍历目录下 assets 文件夹，删除名称包含 _DynamicAsset 的目录。
"""
import os
import re
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

TARGET_VERSION = "5.5.2"
DYNAMIC_TAG = "_DynamicAsset"
# 匹配任意 "version": "xxxx" 字段（兼容不同空白与缩进）
VERSION_RE = re.compile(rb'("version"\s*:\s*")[^"]*(")')


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("像塑工程转换工具 (dyehpj → ehproj)")
        root.geometry("680x460")
        root.minsize(560, 380)

        self.dir_var = tk.StringVar(value="")

        # 顶部：目录选择
        top = ttk.Frame(root, padding=(12, 12, 12, 6))
        top.pack(fill=tk.X)
        ttk.Label(top, text="工程目录：").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.dir_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(top, text="选择目录...", command=self.choose_dir).pack(side=tk.LEFT)
        self.run_btn = ttk.Button(top, text="开始转换", command=self.run)
        self.run_btn.pack(side=tk.LEFT, padx=(6, 0))

        # 中部：进度与日志
        self.log_box = tk.Text(root, wrap="none", state=tk.DISABLED,
                               font=("Consolas", 10))
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        # 底部：状态栏
        self.status_var = tk.StringVar(value="请选择包含 .dyehpj 文件的目录")
        ttk.Label(root, textvariable=self.status_var, anchor="w",
                  padding=(12, 4)).pack(fill=tk.X)

    def log(self, msg: str):
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def choose_dir(self):
        path = filedialog.askdirectory(title="选择像塑工程所在目录")
        if path:
            self.dir_var.set(os.path.normpath(path))
            self.status_var.set(f"已选择目录：{path}")

    def run(self):
        directory = self.dir_var.get().strip()
        if not directory or not os.path.isdir(directory):
            messagebox.showwarning("提示", "请先选择有效的目录")
            return
        self.run_btn.configure(state=tk.DISABLED)
        self.status_var.set("转换中...")
        # 后台线程执行，避免 UI 卡死
        threading.Thread(target=self._work, args=(directory,),
                         daemon=True).start()

    def _work(self, directory: str):
        try:
            files = sorted(
                f for f in os.listdir(directory)
                if f.lower().endswith(".dyehpj")
                and os.path.isfile(os.path.join(directory, f)))
        except OSError as e:
            self.root.after(0, self._done, False, f"读取目录失败：{e}")
            return

        ok, fail = 0, 0
        if not files:
            self.root.after(0, self.log, "该目录下未找到 .dyehpj 文件")
        else:
            self.root.after(0, self.log, f"找到 {len(files)} 个 .dyehpj 文件")
        for name in files:
            src = os.path.join(directory, name)
            dst_name = os.path.splitext(name)[0] + ".ehproj"
            dst = os.path.join(directory, dst_name)
            try:
                # 复制一份并改后缀
                shutil.copy2(src, dst)
                # 二进制方式读取，避免编码问题
                with open(dst, "rb") as f:
                    data = f.read()
                new_data, n = VERSION_RE.subn(
                    rb'\g<1>' + TARGET_VERSION.encode() + rb'\g<2>', data)
                if n == 0:
                    self.root.after(0, self.log,
                                    f"[跳过] {dst_name}：未找到 version 字段（文件已复制）")
                else:
                    with open(dst, "wb") as f:
                        f.write(new_data)
                    self.root.after(0, self.log,
                                    f"[成功] {name} → {dst_name}（替换 {n} 处 version）")
                ok += 1
            except OSError as e:
                self.root.after(0, self.log, f"[失败] {name}：{e}")
                fail += 1

        # 第二步：清理 assets 目录中包含 _DynamicAsset 的文件/文件夹
        cleaned = self._clean_assets(directory)

        msg = f"完成：转换成功 {ok} 个，失败 {fail} 个，删除 {cleaned} 项"
        self.root.after(0, self._done, True, msg)

    def _clean_assets(self, directory: str) -> int:
        """遍历 directory/assets，删除名称包含 _DynamicAsset 的目录"""
        assets_dir = os.path.join(directory, "assets")
        if not os.path.isdir(assets_dir):
            self.root.after(0, self.log, "[跳过] 未找到 assets 目录")
            return 0

        targets = []
        for dirpath, dirnames, filenames in os.walk(assets_dir):
            # 命中的目录整体删除，不再深入遍历；文件一律不动
            matched = [d for d in dirnames if DYNAMIC_TAG in d]
            for d in matched:
                targets.append(os.path.join(dirpath, d))
            dirnames[:] = [d for d in dirnames if DYNAMIC_TAG not in d]

        if not targets:
            self.root.after(0, self.log, "[清理] assets 中无 _DynamicAsset 项")
            return 0

        count = 0
        for p in targets:
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
                self.root.after(0, self.log,
                                f"[删除] {os.path.relpath(p, directory)}")
                count += 1
            except OSError as e:
                self.root.after(0, self.log,
                                f"[失败] 删除 {os.path.relpath(p, directory)}：{e}")
        return count

    def _done(self, success: bool, msg: str):
        self.log(msg)
        self.status_var.set(msg)
        self.run_btn.configure(state=tk.NORMAL)
        if success:
            messagebox.showinfo("完成", msg)
        else:
            messagebox.showwarning("提示", msg)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
