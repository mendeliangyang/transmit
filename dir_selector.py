import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import logging
from pathlib import Path
import datetime
import threading

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

class DirectorySelectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件合并工具 (异步增强版)")
        self.root.geometry("1200x850")
        
        # 存储状态: {item_id: {'path': path, 'is_dir': bool, 'selected': bool, 'recursive': bool}}
        self.node_states = {}
        
        # 默认输出路径：用户下载目录
        self.output_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        # 状态文字
        self.status_var = tk.StringVar(value="就绪")
        self.progress_var = tk.DoubleVar(value=0)

        # 文件类型配置
        self.file_types = {
            "代码文件": [".py", ".c", ".cpp", ".h", ".java", ".js", ".ts", ".html", ".css", ".php", ".go", ".rs", ".sql", ".sh", ".bat"],
            "文档文件": [".txt", ".md", ".csv", ".rst", ".log"],
            "配置文件": [".json", ".xml", ".yaml", ".yml", ".ini", ".conf", ".toml", ".env"],
            "日志文件": [".log", ".out", ".err"]
        }
        self.type_vars = {} # {category: BooleanVar}
        self.all_exts = set()
        for exts in self.file_types.values():
            self.all_exts.update(exts)
        
        self.setup_ui()
        self.load_drives()

    def setup_ui(self):
        # 顶部提示
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(top_frame, text="文件浏览器 (勾选要合并的文件/目录，合并后将生成在输出目录)", 
                  font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)

        # 输出目录设置区域
        output_frame = ttk.LabelFrame(self.root, text="输出设置")
        output_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(output_frame, text="输出目录:").pack(side=tk.LEFT, padx=5, pady=10)
        ttk.Entry(output_frame, textvariable=self.output_dir, width=80).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(output_frame, text="浏览...", command=self.browse_output_dir).pack(side=tk.LEFT, padx=5)

        # 文件类型筛选区域
        filter_frame = ttk.LabelFrame(self.root, text="文件类型筛选 (仅合并选中的格式)")
        filter_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 全选/全取消
        select_all_btn = ttk.Button(filter_frame, text="全选", width=8, command=self._select_all_types)
        select_all_btn.pack(side=tk.LEFT, padx=5, pady=5)
        deselect_all_btn = ttk.Button(filter_frame, text="清空", width=8, command=self._deselect_all_types)
        deselect_all_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # 类型复选框
        for category in self.file_types.keys():
            var = tk.BooleanVar(value=True)
            self.type_vars[category] = var
            cb = ttk.Checkbutton(filter_frame, text=category, variable=var)
            cb.pack(side=tk.LEFT, padx=10)
            # 悬停提示
            self._create_tooltip(cb, f"包含: {' '.join(self.file_types[category])}")

        # Treeview 区域
        self.tree_frame = ttk.Frame(self.root)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ("selected", "recursive")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show='tree headings')
        
        self.tree.heading("#0", text="名称", anchor=tk.W)
        self.tree.heading("selected", text="选择", anchor=tk.CENTER)
        self.tree.heading("recursive", text="递归子目录", anchor=tk.CENTER)
        
        self.tree.column("#0", width=700, stretch=True)
        self.tree.column("selected", width=100, anchor=tk.CENTER, stretch=False)
        self.tree.column("recursive", width=100, anchor=tk.CENTER, stretch=False)

        vsb = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        self.tree_frame.grid_columnconfigure(0, weight=1)
        self.tree_frame.grid_rowconfigure(0, weight=1)

        self.tree.bind('<<TreeviewOpen>>', self.on_node_expand)
        self.tree.bind('<Button-1>', self.on_click)

        # 进度条
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=10, pady=(0, 5))

        # 底部按钮和状态栏
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(bottom_frame, text="刷新驱动器", command=self.load_drives).pack(side=tk.LEFT, padx=5)
        
        # 状态标签
        ttk.Label(bottom_frame, textvariable=self.status_var, foreground="#666").pack(side=tk.LEFT, padx=20)
        
        self.run_btn = tk.Button(
            bottom_frame, 
            text="开始合并导出", 
            command=self.run_process,
            bg="#0078D7", fg="white", font=("Microsoft YaHei", 10, "bold"), padx=20
        )
        self.run_btn.pack(side=tk.RIGHT, padx=5)

    def _select_all_types(self):
        for var in self.type_vars.values():
            var.set(True)

    def _deselect_all_types(self):
        for var in self.type_vars.values():
            var.set(False)

    def _create_tooltip(self, widget, text):
        def enter(event):
            self.status_var.set(text)
        def leave(event):
            self.status_var.set("就绪")
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def browse_output_dir(self):
        directory = filedialog.askdirectory(initialdir=self.output_dir.get())
        if directory:
            self.output_dir.set(os.path.normpath(directory))

    def load_drives(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.node_states.clear()

        import string
        from ctypes import windll
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    node = self.tree.insert("", tk.END, text=f" 💽 本地磁盘 ({letter}:)", 
                                           values=("☐", "☐"), open=False)
                    self.node_states[node] = {"path": drive, "is_dir": True, "selected": False, "recursive": False}
                    self.tree.insert(node, tk.END, text="loading...")
            bitmask >>= 1

    def on_node_expand(self, event):
        node = self.tree.focus()
        if not node or node not in self.node_states:
            return

        children = self.tree.get_children(node)
        if len(children) == 1 and self.tree.item(children[0])['text'] == "loading...":
            # 异步加载目录内容
            self.status_var.set(f"正在读取: {self.node_states[node]['path']}...")
            threading.Thread(target=self._async_load_contents, args=(node,), daemon=True).start()

    def _async_load_contents(self, parent_node):
        """在后台线程读取目录内容，避免 UI 卡顿"""
        parent_path = self.node_states[parent_node]["path"]
        try:
            dirs = []
            files = []
            for entry in os.scandir(parent_path):
                if entry.is_dir():
                    dirs.append(entry)
                else:
                    files.append(entry)
            
            # 回到主线程更新 UI
            self.root.after(0, lambda: self._update_tree_with_contents(parent_node, dirs, files))
        except Exception as e:
            logging.error(f"无法读取内容 {parent_path}: {e}")
            self.root.after(0, lambda: self._update_tree_with_contents(parent_node, [], [], error=str(e)))

    def _update_tree_with_contents(self, parent_node, dirs, files, error=None):
        """主线程更新 Treeview"""
        # 删除 "loading..." 节点
        for child in self.tree.get_children(parent_node):
            if self.tree.item(child)['text'] == "loading...":
                self.tree.delete(child)
        
        if error:
            self.tree.insert(parent_node, tk.END, text=f" ❌ 无法访问: {error}")
        else:
            parent_state = self.node_states.get(parent_node, {})
            parent_selected = parent_state.get("selected", False)
            parent_recursive = parent_state.get("recursive", False)

            for entry in sorted(dirs, key=lambda e: e.name.lower()):
                # 如果父节点选中且开启递归，子目录也自动选中
                is_selected = parent_selected and parent_recursive
                node = self.tree.insert(parent_node, tk.END, text=f" 📁 {entry.name}", 
                                       values=("☑" if is_selected else "☐", "☐"), open=False)
                self.node_states[node] = {"path": entry.path, "is_dir": True, "selected": is_selected, "recursive": False}
                try:
                    # 快速检查是否有子项以显示展开箭头
                    if any(os.scandir(entry.path)):
                        self.tree.insert(node, tk.END, text="loading...")
                except: pass
                
            for entry in sorted(files, key=lambda e: e.name.lower()):
                # 如果父节点选中，子文件自动选中（不论是否递归）
                # 或者父节点递归选中，子文件也必须选中
                is_selected = parent_selected
                node = self.tree.insert(parent_node, tk.END, text=f" 📄 {entry.name}", 
                                       values=("☑" if is_selected else "☐", "-"), open=False)
                self.node_states[node] = {"path": entry.path, "is_dir": False, "selected": is_selected, "recursive": None}
        
        self.status_var.set("就绪")

    def on_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            item_id = self.tree.identify_row(event.y)
            if not item_id or item_id not in self.node_states:
                return

            state = self.node_states[item_id]
            if column == "#1":  # 选择列
                state["selected"] = not state["selected"]
                self.tree.set(item_id, "selected", "☑" if state["selected"] else "☐")
                
                # 处理级联选择
                if state["is_dir"]:
                    self._cascade_selection(item_id, state["selected"], state["recursive"])
                
            elif column == "#2" and state["is_dir"]:  # 递归列
                state["recursive"] = not state["recursive"]
                self.tree.set(item_id, "recursive", "☑" if state["recursive"] else "☐")
                
                # 如果当前目录已选中，切换递归状态时需要更新下级状态
                if state["selected"]:
                    self._cascade_selection(item_id, True, state["recursive"])

    def _cascade_selection(self, parent_node, is_selected, recursive):
        """向下级联更新选择状态"""
        for child in self.tree.get_children(parent_node):
            if child not in self.node_states:
                continue
            
            child_state = self.node_states[child]
            
            # 逻辑：
            # 1. 如果是文件：始终跟随父目录的选中状态
            # 2. 如果是目录：
            #    - 如果父目录开启递归：子目录跟随父目录选中状态，并继续向下递归
            #    - 如果父目录关闭递归：子目录不自动选中（除非之前就选中了，但用户要求是“选中目录后自动选中下一级文件”）
            
            if not child_state["is_dir"]:
                # 文件处理
                child_state["selected"] = is_selected
                self.tree.set(child, "selected", "☑" if is_selected else "☐")
            else:
                # 目录处理
                if recursive:
                    # 递归模式下，子目录同步状态并继续向下级联
                    child_state["selected"] = is_selected
                    self.tree.set(child, "selected", "☑" if is_selected else "☐")
                    self._cascade_selection(child, is_selected, True)
                else:
                    # 非递归模式下，取消选中父目录时，如果之前是同步选中的，则也取消选中子目录
                    if not is_selected:
                        child_state["selected"] = False
                        self.tree.set(child, "selected", "☑" if False else "☐")
                        self._cascade_selection(child, False, False)

    def run_process(self):
        """主入口，启动异步处理线程"""
        selected_files = []
        selected_dirs = []
        
        for node, state in self.node_states.items():
            if state["selected"]:
                if state["is_dir"]:
                    selected_dirs.append((state["path"], state["recursive"]))
                else:
                    selected_files.append(state["path"])
        
        if not selected_files and not selected_dirs:
            messagebox.showwarning("警告", "请至少勾选一个文件或目录")
            return

        out_dir = self.output_dir.get()
        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建输出目录: {e}")
                return

        # 禁用 UI 避免重复点击
        self.set_ui_state(False)
        self.status_var.set("正在扫描并合并文件，请稍候...")
        
        # 启动工作线程
        worker = threading.Thread(target=self.worker_thread, args=(selected_files, selected_dirs, out_dir))
        worker.daemon = True
        worker.start()

    def set_ui_state(self, enabled):
        """启用或禁用 UI 交互"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.run_btn.config(state=state)
        if enabled:
            self.run_btn.config(bg="#0078D7")
        else:
            self.run_btn.config(bg="#ccc")

    def worker_thread(self, selected_files, selected_dirs, out_dir):
        """后台工作线程逻辑"""
        try:
            # 0. 获取允许的文件后缀名
            allowed_exts = set()
            for category, var in self.type_vars.items():
                if var.get():
                    allowed_exts.update(self.file_types[category])
            
            # 如果什么都没选，默认不进行后缀名过滤，或者提示错误
            # 这里我们选择如果什么都没选，则只合并用户显式勾选的单个文件，不扫描目录
            
            # 1. 扫描文件
            total_file_paths = set()
            
            # 处理显式勾选的文件
            for fpath in selected_files:
                ext = os.path.splitext(fpath)[1].lower()
                if not allowed_exts or ext in allowed_exts:
                    total_file_paths.add(fpath)

            # 处理勾选的目录
            for d_path, recursive in selected_dirs:
                if recursive:
                    for root, _, files in os.walk(d_path):
                        for f in files:
                            ext = os.path.splitext(f)[1].lower()
                            if not allowed_exts or ext in allowed_exts:
                                total_file_paths.add(os.path.join(root, f))
                else:
                    try:
                        for entry in os.scandir(d_path):
                            if entry.is_file():
                                ext = os.path.splitext(entry.name)[1].lower()
                                if not allowed_exts or ext in allowed_exts:
                                    total_file_paths.add(entry.path)
                    except: pass

            if not total_file_paths:
                self.root.after(0, lambda: messagebox.showinfo("提示", "根据当前的筛选条件，未找到任何匹配的文件"))
                self.root.after(0, lambda: self.finish_ui_update())
                return

            # 2. 执行合并
            self.perform_merge(total_file_paths, out_dir)
            
        except Exception as e:
            logging.error(f"工作线程异常: {e}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"处理过程中发生意外错误: {e}"))
            self.root.after(0, lambda: self.finish_ui_update())

    def perform_merge(self, file_paths, output_directory):
        """实际的合并 IO 操作"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"merged_files_{timestamp}.txt"
        output_path = os.path.join(output_directory, output_filename)
        
        success_count = 0
        fail_count = 0
        sorted_paths = sorted(list(file_paths))
        total_count = len(sorted_paths)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as outfile:
                for i, fpath in enumerate(sorted_paths):
                    # 更新状态文字和进度条
                    progress = ((i + 1) / total_count) * 100
                    self.root.after(0, lambda p=progress, count=i+1: self._update_progress(p, count, total_count))
                    
                    try:
                        outfile.write(f"\n{'='*50}\n")
                        outfile.write(f"FILE: {fpath}\n")
                        outfile.write(f"{'='*50}\n\n")
                        
                        with open(fpath, 'r', encoding='utf-8', errors='ignore') as infile:
                            while True:
                                chunk = infile.read(1024 * 1024)
                                if not chunk:
                                    break
                                outfile.write(chunk)
                            outfile.write("\n")
                        success_count += 1
                    except Exception as e:
                        logging.error(f"读取失败 {fpath}: {e}")
                        fail_count += 1
            
            msg = f"合并完成！\n\n生成文件: {output_filename}\n所在目录: {output_directory}\n"
            msg += f"成功合并: {success_count} 个文件\n失败: {fail_count} 个"
            
            self.root.after(0, lambda: self.show_final_result(msg, output_directory))
            
        except Exception as e:
            logging.error(f"合并写入失败: {e}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"无法写入输出文件: {e}"))
            self.root.after(0, lambda: self.finish_ui_update())

    def _update_progress(self, progress, current, total):
        """更新 UI 进度条和状态文字"""
        self.progress_var.set(progress)
        self.status_var.set(f"正在处理: {current}/{total} ({int(progress)}%)")

    def show_final_result(self, message, output_dir):
        """在主线程显示最终结果并恢复 UI"""
        self.progress_var.set(100)
        messagebox.showinfo("成功", message)
        self.finish_ui_update()
        try:
            os.startfile(output_dir)
        except: pass

    def finish_ui_update(self):
        """恢复 UI 状态"""
        self.set_ui_state(True)
        self.status_var.set("就绪")
        self.progress_var.set(0)

if __name__ == "__main__":
    root = tk.Tk()
    default_font = ("Microsoft YaHei", 9)
    root.option_add("*Font", default_font)
    app = DirectorySelectorApp(root)
    root.mainloop()

if __name__ == "__main__":
    root = tk.Tk()
    # 设置系统默认字体
    default_font = ("Microsoft YaHei", 9)
    root.option_add("*Font", default_font)
    app = DirectorySelectorApp(root)
    root.mainloop()
