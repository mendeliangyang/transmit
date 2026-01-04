import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import logging
from pathlib import Path
import datetime
import threading

import json

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

CONFIG_FILE = "config.json"

class DirectorySelectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文件合并工具 (异步增强版)")
        self.root.geometry("1200x850")
        
        # 存储状态: {item_id: {'path': path, 'is_dir': bool, 'selected': bool, 'recursive': bool}}
        self.node_states = {}
        
        # 加载配置
        self.load_config()

        # 跳转路径
        self.jump_path_var = tk.StringVar(value=self.jump_path_cache)
        # 搜索
        self.search_var = tk.StringVar(value=self.search_query_cache)
        self.search_results = []
        self.current_search_idx = -1
        
        # 默认输出路径：用户下载目录
        self.output_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        # 状态文字
        self.status_var = tk.StringVar(value="就绪")
        self.progress_var = tk.DoubleVar(value=0)

        self.type_vars = {} # {category: BooleanVar}
        
        self.setup_ui()
        self.load_drives()

        # 添加保存配置的监听
        self.jump_path_var.trace_add("write", lambda *args: self.save_config())
        self.search_var.trace_add("write", lambda *args: self.save_config())

        # 如果有缓存的跳转路径，执行跳转
        if self.jump_path_cache:
            self.root.after(500, self.jump_to_path)
        
        # 如果有缓存的搜索词，执行搜索
        if self.search_query_cache:
            self.root.after(1000, lambda: self.perform_search(reset=True))

    def load_config(self):
        """从文件加载配置，如果不存在则使用默认值"""
        default_config = {
            "file_types": {
                "代码文件": [".py", ".c", ".cpp", ".h", ".java", ".js", ".ts", ".html", ".css", ".php", ".go", ".rs", ".sql", ".sh", ".bat", ".cs"],
                "文档文件": [".txt", ".md", ".csv", ".rst", ".log"],
                "配置文件": [".json", ".xml", ".yaml", ".yml", ".ini", ".conf", ".toml", ".env"],
                "日志文件": [".log", ".out", ".err"]
            },
            "selected_states": {}, # {path: {"selected": bool, "recursive": bool}}
            "jump_path": "",
            "search_query": ""
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.file_types = config.get("file_types", default_config["file_types"])
                    self.selected_states = config.get("selected_states", {})
                    self.jump_path_cache = config.get("jump_path", "")
                    self.search_query_cache = config.get("search_query", "")
            except Exception as e:
                logging.error(f"加载配置文件失败: {e}")
                self.file_types = default_config["file_types"]
                self.selected_states = {}
                self.jump_path_cache = ""
                self.search_query_cache = ""
        else:
            self.file_types = default_config["file_types"]
            self.selected_states = {}
            self.jump_path_cache = ""
            self.search_query_cache = ""
            self.save_config()

    def save_config(self):
        """保存当前配置到文件"""
        try:
            config_to_save = {
                "file_types": self.file_types,
                "selected_states": self.selected_states,
                "jump_path": self.jump_path_var.get(),
                "search_query": self.search_var.get()
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"保存配置文件失败: {e}")

    def setup_ui(self):
        # 清除现有 UI（用于动态刷新）
        for widget in self.root.winfo_children():
            widget.destroy()

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
        self.filter_frame = ttk.LabelFrame(self.root, text="文件类型筛选 (仅合并选中的格式)")
        self.filter_frame.pack(fill=tk.X, padx=10, pady=5)
        self.refresh_filter_ui()

        # Treeview 区域
        self.tree_frame = ttk.Frame(self.root)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 快速跳转区域 (移动到 Treeview 上方)
        jump_frame = ttk.Frame(self.tree_frame)
        jump_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 5))
        
        ttk.Label(jump_frame, text="快速跳转路径:").pack(side=tk.LEFT, padx=(0, 5))
        self.jump_entry = ttk.Entry(jump_frame, textvariable=self.jump_path_var)
        self.jump_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.jump_entry.bind("<Return>", lambda e: self.jump_to_path())
        
        ttk.Button(jump_frame, text="跳转", command=self.jump_to_path).pack(side=tk.LEFT, padx=5)
        ttk.Button(jump_frame, text="选择...", command=self.browse_for_jump).pack(side=tk.LEFT, padx=2)

        # 搜索区域 (在跳转下方)
        search_frame = ttk.Frame(self.tree_frame)
        search_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 5))
        
        ttk.Label(search_frame, text="在视图中搜索:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.search_entry.bind("<Return>", lambda e: self.perform_search())
        self.search_var.trace_add("write", lambda *args: self.perform_search(reset=True))

        self.search_info_var = tk.StringVar(value="0/0")
        ttk.Label(search_frame, textvariable=self.search_info_var, width=10).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(search_frame, text="∧", width=3, command=lambda: self.navigate_search(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(search_frame, text="∨", width=3, command=lambda: self.navigate_search(1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(search_frame, text="清除", width=5, command=self.clear_search).pack(side=tk.LEFT, padx=2)

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

        self.tree.grid(row=2, column=0, sticky='nsew')
        vsb.grid(row=2, column=1, sticky='ns')
        hsb.grid(row=3, column=0, sticky='ew')
        
        self.tree_frame.grid_columnconfigure(0, weight=1)
        self.tree_frame.grid_rowconfigure(2, weight=1)

        self.tree.tag_configure("match", background="#FFFACD", foreground="black") # 浅黄色背景
        self.tree.tag_configure("current_match", background="#FFD700", foreground="black") # 金黄色背景

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
        
        self.sync_btn = tk.Button(
            bottom_frame,
            text="对比并同步修改",
            command=self.run_diff_sync,
            bg="#28A745", fg="white", font=("Microsoft YaHei", 10), padx=10
        )
        self.sync_btn.pack(side=tk.RIGHT, padx=5)

        self.run_btn = tk.Button(
            bottom_frame, 
            text="开始合并导出", 
            command=self.run_process,
            bg="#0078D7", fg="white", font=("Microsoft YaHei", 10, "bold"), padx=20
        )
        self.run_btn.pack(side=tk.RIGHT, padx=5)

    def refresh_filter_ui(self):
        """刷新筛选区域的 UI"""
        for widget in self.filter_frame.winfo_children():
            widget.destroy()
        
        # 全选/全取消
        select_all_btn = ttk.Button(self.filter_frame, text="全选", width=8, command=self._select_all_types)
        select_all_btn.pack(side=tk.LEFT, padx=5, pady=5)
        deselect_all_btn = ttk.Button(self.filter_frame, text="清空", width=8, command=self._deselect_all_types)
        deselect_all_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # 类型复选框
        for category in self.file_types.keys():
            # 保持之前的选中状态，如果分类是新增加的则默认选中
            old_val = self.type_vars[category].get() if category in self.type_vars else True
            var = tk.BooleanVar(value=old_val)
            self.type_vars[category] = var
            cb = ttk.Checkbutton(self.filter_frame, text=category, variable=var)
            cb.pack(side=tk.LEFT, padx=10)
            self._create_tooltip(cb, f"包含: {' '.join(self.file_types[category])}")
        
        # 管理按钮
        manage_btn = ttk.Button(self.filter_frame, text="⚙ 管理类型", command=self.show_manage_dialog)
        manage_btn.pack(side=tk.RIGHT, padx=10, pady=5)

    def show_manage_dialog(self):
        """显示管理文件类型的对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("管理文件类型")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # 左侧分类列表
        list_frame = ttk.Frame(frame)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        ttk.Label(list_frame, text="现有分类:").pack(anchor=tk.W)
        self.category_list = tk.Listbox(list_frame, height=15)
        self.category_list.pack(fill=tk.BOTH, expand=True)
        for cat in self.file_types.keys():
            self.category_list.insert(tk.END, cat)

        # 右侧操作区
        op_frame = ttk.Frame(frame)
        op_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))

        ttk.Label(op_frame, text="分类名称:").pack(anchor=tk.W)
        cat_entry = ttk.Entry(op_frame)
        cat_entry.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(op_frame, text="后缀名 (一行一个):").pack(anchor=tk.W)
        ext_text = tk.Text(op_frame, height=12, width=30, font=("Consolas", 10))
        ext_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        def on_list_select(event):
            selection = self.category_list.curselection()
            if selection:
                cat = self.category_list.get(selection[0])
                cat_entry.delete(0, tk.END)
                cat_entry.insert(0, cat)
                ext_text.delete("1.0", tk.END)
                ext_text.insert(tk.END, "\n".join(self.file_types[cat]))

        self.category_list.bind("<<ListboxSelect>>", on_list_select)

        def add_update():
            cat = cat_entry.get().strip()
            # 获取文本框内容，按行分割并过滤空行
            exts_content = ext_text.get("1.0", tk.END).strip()
            # 兼容性处理：支持空格分割或换行分割
            import re
            exts = re.split(r'[\n\s,]+', exts_content)
            exts = [e.strip() for e in exts if e.strip()]
            
            if not cat or not exts:
                messagebox.showwarning("警告", "名称和后缀名不能为空", parent=dialog)
                return
            
            # 格式化后缀名（确保以 . 开头）
            formatted_exts = [e if e.startswith('.') else f'.{e}' for e in exts]
            self.file_types[cat] = sorted(list(set(formatted_exts)))
            self.save_config()
            
            # 更新列表
            self.category_list.delete(0, tk.END)
            for c in self.file_types.keys():
                self.category_list.insert(tk.END, c)
            self.refresh_filter_ui()
            messagebox.showinfo("成功", f"分类 '{cat}' 已保存", parent=dialog)

        def delete_cat():
            selection = self.category_list.curselection()
            if not selection:
                return
            cat = self.category_list.get(selection[0])
            if messagebox.askyesno("确认", f"确定要删除分类 '{cat}' 吗？", parent=dialog):
                del self.file_types[cat]
                if cat in self.type_vars:
                    del self.type_vars[cat]
                self.save_config()
                self.category_list.delete(selection[0])
                self.refresh_filter_ui()

        ttk.Button(op_frame, text="添加 / 更新", command=add_update).pack(fill=tk.X, pady=5)
        ttk.Button(op_frame, text="删除选中项", command=delete_cat).pack(fill=tk.X, pady=5)
        ttk.Button(op_frame, text="关闭", command=dialog.destroy).pack(fill=tk.X, pady=(20, 0))

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

    def clear_search(self):
        self.search_var.set("")
        for item in self.search_results:
            self._update_node_tags(item)
        self.search_results = []
        self.current_search_idx = -1
        self.search_info_var.set("0/0")

    def perform_search(self, reset=False):
        """在已加载的节点中执行搜索并高亮"""
        query = self.search_var.get().strip().lower()
        
        # 清除旧高亮
        for item in self.search_results:
            self._update_node_tags(item)
            
        if not query:
            self.search_results = []
            self.current_search_idx = -1
            self.search_info_var.set("0/0")
            return

        if reset:
            self.current_search_idx = -1

        # 遍历所有已加载节点
        self.search_results = []
        self._find_matches("", query)
        
        count = len(self.search_results)
        if count > 0:
            if self.current_search_idx == -1:
                self.current_search_idx = 0
            
            # 应用高亮标签
            for i, item_id in enumerate(self.search_results):
                tag = "current_match" if i == self.current_search_idx else "match"
                self.tree.item(item_id, tags=(tag,))
                
                # 如果是当前项，确保可见
                if i == self.current_search_idx:
                    self.tree.see(item_id)
            
            self.search_info_var.set(f"{self.current_search_idx + 1}/{count}")
        else:
            self.current_search_idx = -1
            self.search_info_var.set("0/0")

    def _find_matches(self, parent, query):
        """递归查找匹配项"""
        for item_id in self.tree.get_children(parent):
            node_text = self.tree.item(item_id, "text").lower()
            if query in node_text:
                self.search_results.append(item_id)
            
            # 继续查找已展开的子节点
            self._find_matches(item_id, query)

    def navigate_search(self, direction):
        """上一个/下一个跳转"""
        count = len(self.search_results)
        if count == 0: return
        
        # 清除当前的高亮状态（恢复为普通 match 状态）
        if 0 <= self.current_search_idx < count:
            self.tree.item(self.search_results[self.current_search_idx], tags=("match",))
            
        self.current_search_idx = (self.current_search_idx + direction) % count
        
        # 设置新的当前高亮并滚动
        target_id = self.search_results[self.current_search_idx]
        self.tree.item(target_id, tags=("current_match",))
        self.tree.see(target_id)
        self.search_info_var.set(f"{self.current_search_idx + 1}/{count}")

    def _update_node_tags(self, item_id):
        """重置节点标签"""
        if self.tree.exists(item_id):
            self.tree.item(item_id, tags=())

    def browse_for_jump(self):
        directory = filedialog.askdirectory()
        if directory:
            self.jump_path_var.set(os.path.normpath(directory))
            self.jump_to_path()

    def jump_to_path(self):
        """跳转到指定路径并自动展开"""
        raw_path = self.jump_path_var.get().strip()
        if not raw_path:
            return
            
        target_path = os.path.normpath(raw_path)
        if not os.path.exists(target_path):
            messagebox.showerror("错误", f"路径不存在: {target_path}")
            return

        # 获取路径层级
        parts = []
        temp_path = target_path
        while True:
            parent, child = os.path.split(temp_path)
            if child:
                parts.insert(0, child)
                temp_path = parent
            else:
                if parent: # 磁盘根目录，如 C:\
                    parts.insert(0, parent)
                break

        if not parts:
            return

        # 从根部开始逐级查找并展开
        current_node = ""
        
        def find_and_expand(index, parent_id):
            nonlocal current_node
            target_part = parts[index].lower()
            
            # 获取当前层级的所有子节点
            children = self.tree.get_children(parent_id)
            
            # 如果是 loading...，说明还没加载，先触发加载
            if len(children) == 1 and self.tree.item(children[0])['text'] == "loading...":
                # 这种同步跳转比较复杂，因为加载是异步的
                # 我们改为直接调用同步读取方法，或者等待异步完成
                self._sync_expand_for_jump(parent_id)
                children = self.tree.get_children(parent_id)

            found_id = None
            for child_id in children:
                node_data = self.node_states.get(child_id)
                if not node_data: continue
                
                node_path = node_data["path"]
                _, node_name = os.path.split(node_path.rstrip(os.sep))
                
                # 特殊处理磁盘根目录
                if index == 0 and os.path.dirname(node_path) == node_path:
                    if node_path.lower().startswith(target_part):
                        found_id = child_id
                        break
                elif node_name.lower() == target_part:
                    found_id = child_id
                    break
            
            if found_id:
                self.tree.item(found_id, open=True)
                self.tree.see(found_id)
                self.tree.selection_set(found_id)
                self.tree.focus(found_id)
                
                if index < len(parts) - 1:
                    # 继续下一级
                    self.root.after(50, lambda: find_and_expand(index + 1, found_id))
                else:
                    # 如果是最后一级（目标路径），确保它的子项也被加载出来
                    if os.path.isdir(target_path):
                        self.root.after(50, lambda: self._sync_expand_for_jump(found_id))
                        self.tree.item(found_id, open=True)
            else:
                messagebox.showwarning("提醒", f"在当前视图中未找到: {parts[index]}\n请尝试手动展开父目录。")

        find_and_expand(0, "")

    def _sync_expand_for_jump(self, node_id):
        """同步加载目录内容，仅用于跳转功能"""
        parent_path = self.node_states[node_id]["path"]
        try:
            dirs = []
            files = []
            for entry in os.scandir(parent_path):
                if entry.is_dir():
                    dirs.append(entry)
                else:
                    files.append(entry)
            
            self._update_tree_with_contents(node_id, dirs, files)
        except Exception as e:
            logging.error(f"同步读取失败 {parent_path}: {e}")

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
                    # 检查驱动器是否有保存的状态
                    saved = self.selected_states.get(drive, {})
                    is_selected = saved.get("selected", False)
                    is_recursive = saved.get("recursive", False)

                    node = self.tree.insert("", tk.END, text=f" 💽 本地磁盘 ({letter}:)", 
                                           values=("☑" if is_selected else "☐", "☑" if is_recursive else "☐"), open=False)
                    self.node_states[node] = {"path": drive, "is_dir": True, "selected": is_selected, "recursive": is_recursive}
                    self.tree.insert(node, tk.END, text="loading...")
                    
                    # 如果有保存状态且不是根目录（或者我们想自动展开选中的项），可以根据需要处理
                    # 这里为了兼容懒加载，如果驱动器被选中了，我们在展开时会自动处理子项
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
                # 优先级：1. 显式记录的状态 2. 父节点的继承状态
                saved = self.selected_states.get(entry.path, {})
                is_selected = saved.get("selected", parent_selected and parent_recursive)
                is_recursive = saved.get("recursive", False)

                node = self.tree.insert(parent_node, tk.END, text=f" 📁 {entry.name}", 
                                       values=("☑" if is_selected else "☐", "☑" if is_recursive else "☐"), open=False)
                self.node_states[node] = {"path": entry.path, "is_dir": True, "selected": is_selected, "recursive": is_recursive}
                try:
                    # 快速检查是否有子项以显示展开箭头
                    if any(os.scandir(entry.path)):
                        self.tree.insert(node, tk.END, text="loading...")
                except: pass
                
            for entry in sorted(files, key=lambda e: e.name.lower()):
                # 优先级：1. 显式记录的状态 2. 父节点的继承状态
                saved = self.selected_states.get(entry.path, {})
                is_selected = saved.get("selected", parent_selected)

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
            path = state["path"]
            
            if column == "#1":  # 选择列
                state["selected"] = not state["selected"]
                self.tree.set(item_id, "selected", "☑" if state["selected"] else "☐")
                
                # 更新持久化状态
                if state["selected"]:
                    self.selected_states[path] = {"selected": True, "recursive": state.get("recursive", False)}
                else:
                    if path in self.selected_states:
                        del self.selected_states[path]
                self.save_config()

                # 处理级联选择
                if state["is_dir"]:
                    self._cascade_selection(item_id, state["selected"], state["recursive"])
                
            elif column == "#2" and state["is_dir"]:  # 递归列
                state["recursive"] = not state["recursive"]
                self.tree.set(item_id, "recursive", "☑" if state["recursive"] else "☐")
                
                # 更新持久化状态
                if state["selected"]:
                    self.selected_states[path] = {"selected": True, "recursive": state["recursive"]}
                    self.save_config()

                # 如果当前目录已选中，切换递归状态时需要更新下级状态
                if state["selected"]:
                    self._cascade_selection(item_id, True, state["recursive"])

    def _cascade_selection(self, parent_node, is_selected, recursive):
        """向下级联更新选择状态"""
        for child in self.tree.get_children(parent_node):
            if child not in self.node_states:
                continue
            
            child_state = self.node_states[child]
            path = child_state["path"]
            
            if not child_state["is_dir"]:
                # 文件处理
                child_state["selected"] = is_selected
                self.tree.set(child, "selected", "☑" if is_selected else "☐")
                
                # 同步到持久化状态
                if is_selected:
                    self.selected_states[path] = {"selected": True, "recursive": None}
                else:
                    if path in self.selected_states:
                        del self.selected_states[path]
            else:
                # 目录处理
                if recursive:
                    # 递归模式下，子目录同步状态并继续向下级联
                    child_state["selected"] = is_selected
                    self.tree.set(child, "selected", "☑" if is_selected else "☐")
                    
                    if is_selected:
                        self.selected_states[path] = {"selected": True, "recursive": child_state["recursive"]}
                    else:
                        if path in self.selected_states:
                            del self.selected_states[path]
                    
                    self._cascade_selection(child, is_selected, True)
                else:
                    # 非递归模式下，取消选中父目录时，如果之前是同步选中的，则也取消选中子目录
                    if not is_selected:
                        child_state["selected"] = False
                        self.tree.set(child, "selected", "☐")
                        if path in self.selected_states:
                            del self.selected_states[path]
                        self._cascade_selection(child, False, False)
        
        # 批量操作后统一保存一次配置
        self.save_config()

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
        self.sync_btn.config(state=state)
        if enabled:
            self.run_btn.config(bg="#0078D7")
            self.sync_btn.config(bg="#28A745")
        else:
            self.run_btn.config(bg="#ccc")
            self.sync_btn.config(bg="#ccc")

    def run_diff_sync(self):
        """对比并同步逻辑入口"""
        merged_file = filedialog.askopenfilename(
            title="选择已修改的合并文件",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=self.output_dir.get()
        )
        if not merged_file:
            return

        self.set_ui_state(False)
        self.status_var.set("正在解析合并文件并对比差异...")
        
        # 在线程中运行解析和对比，避免 UI 卡死
        threading.Thread(target=self._async_diff_process, args=(merged_file,), daemon=True).start()

    def _async_diff_process(self, merged_file_path):
        """异步处理文件解析和对比"""
        try:
            import re
            import difflib

            with open(merged_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 使用正则解析文件块
            # 匹配模式：==================================================\nFILE: path\n==================================================\n\nCONTENT
            pattern = r'={50}\nFILE: (.*?)\n={50}\n\n(.*?)(?=\n={50}\nFILE: |\Z)'
            matches = re.findall(pattern, content, re.DOTALL)

            diff_results = [] # [(path, original_lines, new_lines, diff_html/text)]
            
            for fpath, new_content in matches:
                fpath = fpath.strip()
                if not os.path.exists(fpath):
                    logging.warning(f"原文件不存在，跳过对比: {fpath}")
                    continue

                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        old_content = f.read()
                    
                    if old_content.strip() == new_content.strip():
                        continue # 没有变化

                    old_lines = old_content.splitlines()
                    new_lines = new_content.splitlines()
                    
                    # 生成差异
                    diff = list(difflib.unified_diff(
                        old_lines, new_lines, 
                        fromfile='Original', tofile='Modified',
                        lineterm=''
                    ))
                    
                    if diff:
                        diff_results.append({
                            'path': fpath,
                            'old_content': old_content,
                            'new_content': new_content,
                            'diff': diff
                        })
                except Exception as e:
                    logging.error(f"对比文件出错 {fpath}: {e}")

            self.root.after(0, lambda: self.show_diff_dialog(diff_results))
        except Exception as e:
            logging.error(f"解析合并文件失败: {e}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"解析失败: {e}"))
            self.root.after(0, lambda: self.finish_ui_update())

    def show_diff_dialog(self, diff_results):
        """显示差异对比和同步对话框"""
        self.finish_ui_update()
        
        if not diff_results:
            messagebox.showinfo("提示", "未检测到任何文件差异。")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("文件差异对比与同步")
        dialog.geometry("1100x700")
        dialog.transient(self.root)
        dialog.grab_set()

        # 主布局
        paned = ttk.PanedWindow(dialog, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧列表：变更文件
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="已修改的文件:").pack(anchor=tk.W, pady=2)
        
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.diff_list = tk.Listbox(list_frame, font=("Segoe UI", 9))
        self.diff_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.diff_list.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.diff_list.config(yscrollcommand=sb.set)

        for item in diff_results:
            self.diff_list.insert(tk.END, os.path.basename(item['path']))

        # 右侧：差异预览
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)
        
        ttk.Label(right_frame, text="差异预览 (Unified Diff):").pack(anchor=tk.W, pady=2)
        
        diff_text_frame = ttk.Frame(right_frame)
        diff_text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.diff_view = tk.Text(diff_text_frame, wrap=tk.NONE, font=("Consolas", 10))
        self.diff_view.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 差异颜色标签
        self.diff_view.tag_configure("add", foreground="green", background="#e6ffec")
        self.diff_view.tag_configure("del", foreground="red", background="#ffebe9")
        self.diff_view.tag_configure("header", foreground="blue", font=("Consolas", 10, "bold"))
        self.diff_view.tag_configure("info", foreground="gray")

        vsb_diff = ttk.Scrollbar(diff_text_frame, orient="vertical", command=self.diff_view.yview)
        vsb_diff.pack(side=tk.RIGHT, fill=tk.Y)
        hsb_diff = ttk.Scrollbar(right_frame, orient="horizontal", command=self.diff_view.xview)
        hsb_diff.pack(fill=tk.X)
        self.diff_view.config(yscrollcommand=vsb_diff.set, xscrollcommand=hsb_diff.set)

        def on_diff_select(event):
            selection = self.diff_list.curselection()
            if not selection:
                return
            idx = selection[0]
            item = diff_results[idx]
            
            self.diff_view.config(state=tk.NORMAL)
            self.diff_view.delete("1.0", tk.END)
            
            self.diff_view.insert(tk.END, f"文件: {item['path']}\n", "header")
            self.diff_view.insert(tk.END, "-"*60 + "\n", "info")
            
            for line in item['diff']:
                if line.startswith('+'):
                    self.diff_view.insert(tk.END, line + "\n", "add")
                elif line.startswith('-'):
                    self.diff_view.insert(tk.END, line + "\n", "del")
                elif line.startswith('@@'):
                    self.diff_view.insert(tk.END, line + "\n", "info")
                else:
                    self.diff_view.insert(tk.END, line + "\n")
            
            self.diff_view.config(state=tk.DISABLED)

        self.diff_list.bind("<<ListboxSelect>>", on_diff_select)

        # 底部按钮
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        def apply_selected():
            selection = self.diff_list.curselection()
            if not selection:
                messagebox.showwarning("提示", "请先在列表中选择要应用的文件")
                return
            
            idx = selection[0]
            item = diff_results[idx]
            
            if messagebox.askyesno("确认应用", f"确定要将修改应用到原文件吗？\n\n文件: {item['path']}"):
                try:
                    with open(item['path'], 'w', encoding='utf-8') as f:
                        f.write(item['new_content'])
                    messagebox.showinfo("成功", "更改已应用到文件。")
                    # 刷新 UI 或移除已处理项
                    self.diff_list.delete(idx)
                    diff_results.pop(idx)
                    self.diff_view.config(state=tk.NORMAL)
                    self.diff_view.delete("1.0", tk.END)
                    self.diff_view.config(state=tk.DISABLED)
                except Exception as e:
                    messagebox.showerror("错误", f"应用失败: {e}")

        def apply_all():
            count = len(diff_results)
            if count == 0: return
            
            if messagebox.askyesno("确认全部应用", f"确定要将所有 {count} 个文件的修改应用到原文件吗？"):
                success = 0
                for item in diff_results:
                    try:
                        with open(item['path'], 'w', encoding='utf-8') as f:
                            f.write(item['new_content'])
                        success += 1
                    except Exception as e:
                        logging.error(f"批量应用失败 {item['path']}: {e}")
                
                messagebox.showinfo("结果", f"批量应用完成！\n成功: {success}\n失败: {count-success}")
                dialog.destroy()

        ttk.Button(btn_frame, text="应用选中的修改", command=apply_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="全部应用", command=apply_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消/关闭", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        # 默认选择第一项
        if diff_results:
            self.diff_list.selection_set(0)
            on_diff_select(None)

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
    # 设置系统默认字体
    default_font = ("Microsoft YaHei", 9)
    root.option_add("*Font", default_font)
    app = DirectorySelectorApp(root)
    root.mainloop()
