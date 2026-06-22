import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import pandas as pd
import re
import json
import os
from datetime import datetime
import threading
import sys

# 导入核心转换功能
from core.converter import TiaToKingscadaConverter

class TiaToKingscadaGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("TIA DB 转换专家")
        self.root.geometry("1200x800")
        self.root.configure(bg="#f8fafc")
        
        # 设置窗口图标
        try:
            import os
            # 使用相对路径
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'icons', 'hat_star_icon.ico')
            self.root.iconbitmap(icon_path)
        except:
            pass

        self.setup_styles()
        self.build_ui()

    # ---------- 样式 ----------
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        # 自定义样式
        style.configure("Header.TFrame", background="white")
        style.configure("Step.TFrame", background="white")
        style.configure("Content.TFrame", background="#f8fafc")
        style.configure("Card.TFrame", background="white", relief="solid", borderwidth=1, bordercolor="#e2e8f0")
        style.configure("ProgressBg.TFrame", background="#e2e8f0")
        style.configure("DarkBg.TFrame", background="#1e293b")
        style.configure("Accent.TButton", font=("Microsoft YaHei", 10, "bold"), background="#3b82f6", foreground="white")
        style.configure("TButton", font=("Microsoft YaHei", 9), padding=5)
        style.configure("TLabel", font=("Microsoft YaHei", 9))
        style.configure("TEntry", font=("Microsoft YaHei", 9), padding=3)
        style.configure("Treeview", font=("Microsoft YaHei", 8))
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 9, "bold"))

    # ---------- UI ----------
    def build_ui(self):
        # 主框架
        main_frame = ttk.Frame(self.root, style="Content.TFrame")
        main_frame.pack(fill="both", expand=True)

        # 顶部导航栏
        self.build_header()
        
        # 步骤导航
        self.build_steps()
        
        # 主体内容
        self.build_main_content()
        
        # 页脚
        self.build_footer()

    def build_header(self):
        header = ttk.Frame(self.root, style="Header.TFrame", height=80)
        header.pack(fill="x", pady=0)
        header.pack_propagate(False)
        
        # 左侧Logo和标题
        left_frame = ttk.Frame(header)
        left_frame.pack(side=tk.LEFT, padx=32, pady=16, fill="y")
        
        # Logo
        logo_frame = ttk.Frame(left_frame, width=40, height=40)
        logo_frame.pack(side=tk.LEFT, padx=12)
        logo_frame.pack_propagate(False)
        logo_bg = tk.Frame(logo_frame, width=40, height=40)
        logo_bg.pack(fill="both", expand=True)
        logo_bg.configure(bg="#3b82f6")
        label = ttk.Label(logo_bg, text="PLC")
        label.pack(fill="both", expand=True)
        label.configure(foreground="white", font=("Microsoft YaHei", 12, "bold"))
        
        # 标题
        title_frame = ttk.Frame(left_frame)
        title_frame.pack(side=tk.LEFT, fill="y")
        label = ttk.Label(title_frame, text="TIA DB 转换专家")
        label.pack(anchor="w")
        label.configure(foreground="#1e293b", font=("Microsoft YaHei", 16, "bold"))
        label = ttk.Label(title_frame, text="工业自动化点表自动化工具 v2.4.0")
        label.pack(anchor="w")
        label.configure(foreground="#64748b", font=("Microsoft YaHei", 9))
        
        # 右侧信息
        right_frame = ttk.Frame(header)
        right_frame.pack(side=tk.RIGHT, padx=32, pady=16, fill="y")
        
        # 当前日期
        current_date = datetime.now().strftime("%Y年%m月%d日")
        date_frame = ttk.Frame(right_frame)
        date_frame.pack(side=tk.LEFT, padx=24)
        label = ttk.Label(date_frame, text="当前日期:")
        label.pack(side=tk.LEFT)
        label.configure(foreground="#64748b", font=("Microsoft YaHei", 9))
        label = ttk.Label(date_frame, text=current_date)
        label.pack(side=tk.LEFT, padx=8)
        label.configure(foreground="#1e293b", font=("Microsoft YaHei", 9, "bold"))
        
        # 转换历史
        history_frame = ttk.Frame(right_frame)
        history_frame.pack(side=tk.LEFT, padx=24)
        ttk.Button(history_frame, text="转换历史").pack(side=tk.LEFT)
        
        # 用户图标
        user_frame = ttk.Frame(right_frame, width=32, height=32)
        user_frame.pack(side=tk.LEFT, padx=24)
        user_frame.pack_propagate(False)
        user_bg = tk.Frame(user_frame, width=32, height=32)
        user_bg.pack(fill="both", expand=True)
        user_bg.configure(bg="#e2e8f0")
        label = ttk.Label(user_bg, text="U")
        label.pack(fill="both", expand=True)
        label.configure(foreground="#64748b", font=("Microsoft YaHei", 12, "bold"))

    def build_steps(self):
        steps = ttk.Frame(self.root, style="Step.TFrame", height=100)
        steps.pack(fill="x", pady=0)
        steps.pack_propagate(False)
        
        # 步骤内容
        steps_content = ttk.Frame(steps)
        steps_content.pack(fill="both", expand=True, padx=160)
        
        # 进度条背景线
        progress_bg = ttk.Frame(steps_content, height=2)
        progress_bg.place(relx=0, rely=0.5, relwidth=1, anchor="n")
        progress_bg.configure(style="ProgressBg.TFrame")
        
        # 步骤
        step_names = ["选择文件", "转换分析", "检查核对", "导出结果"]
        for i, name in enumerate(step_names):
            step_frame = ttk.Frame(steps_content)
            step_frame.place(relx=i/3, rely=0, relwidth=1/4, anchor="n")
            
            # 步骤圆圈
            circle_frame = ttk.Frame(step_frame, width=40, height=40)
            circle_frame.pack(side=tk.TOP, pady=8)
            circle_frame.pack_propagate(False)
            
            if i == 0:
                # 当前步骤
                circle_bg = tk.Frame(circle_frame, width=40, height=40)
                circle_bg.pack(fill="both", expand=True)
                circle_bg.configure(bg="#3b82f6")
                label = ttk.Label(circle_bg, text=str(i+1))
                label.place(relx=0.5, rely=0.5, anchor="center")
                label.configure(foreground="white", font=("Microsoft YaHei", 12, "bold"))
                label = ttk.Label(step_frame, text=name)
                label.pack(side=tk.TOP, pady=4)
                label.configure(foreground="#3b82f6", font=("Microsoft YaHei", 10, "bold"))
            else:
                # 未完成步骤
                circle_bg = tk.Frame(circle_frame, width=40, height=40)
                circle_bg.pack(fill="both", expand=True)
                circle_bg.configure(bg="#e2e8f0")
                label = ttk.Label(circle_bg, text=str(i+1))
                label.place(relx=0.5, rely=0.5, anchor="center")
                label.configure(foreground="#94a3b8", font=("Microsoft YaHei", 12, "bold"))
                label = ttk.Label(step_frame, text=name)
                label.pack(side=tk.TOP, pady=4)
                label.configure(foreground="#94a3b8", font=("Microsoft YaHei", 10))

    def build_main_content(self):
        content = ttk.Frame(self.root, style="Content.TFrame")
        content.pack(fill="both", expand=True, padx=32, pady=32)
        
        # 左侧：文件上传区
        left_frame = ttk.Frame(content, width=800)
        left_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=(0, 32))
        
        # 文件上传卡片
        upload_card = ttk.Frame(left_frame, style="Card.TFrame")
        upload_card.pack(fill="x", pady=(0, 24))
        
        # 上传标题
        upload_header = ttk.Frame(upload_card)
        upload_header.pack(fill="x", pady=24, padx=24)
        label = ttk.Label(upload_header, text="上传 TIA Portal DB 块源文件")
        label.pack(side=tk.LEFT)
        label.configure(foreground="#1e293b", font=("Microsoft YaHei", 14, "bold"))
        
        # 上传区域
        upload_area = ttk.Frame(upload_card, style="Card.TFrame")
        upload_area.pack(fill="x", pady=(0, 24), padx=24)
        
        # 上传图标
        icon_frame = ttk.Frame(upload_area, width=80, height=80)
        icon_frame.pack(side=tk.TOP, pady=24)
        icon_frame.pack_propagate(False)
        icon_bg = tk.Frame(icon_frame, width=80, height=80)
        icon_bg.pack(fill="both", expand=True)
        icon_bg.configure(bg="#eff6ff")
        label = ttk.Label(icon_bg, text="📄")
        label.pack(fill="both", expand=True)
        label.configure(font=("Arial", 32))
        
        # 上传提示
        label = ttk.Label(upload_area, text="点击或将文件拖拽至此处")
        label.pack(side=tk.TOP, pady=8)
        label.configure(foreground="#1e293b", font=("Microsoft YaHei", 14))
        label = ttk.Label(upload_area, text="支持 .db / .scl / .xml 格式 (最大 20MB)")
        label.pack(side=tk.TOP, pady=4)
        label.configure(foreground="#64748b", font=("Microsoft YaHei", 10))
        
        # 浏览按钮
        browse_btn = ttk.Button(upload_area, text="浏览本地文件", style="Accent.TButton", command=self.browse_file)
        browse_btn.pack(side=tk.TOP, pady=24, padx=100)
        
        # 已选择文件预览
        self.file_preview_frame = ttk.Frame(upload_card, style="Card.TFrame")
        self.file_preview_frame.pack(fill="x", pady=(0, 24), padx=24)
        
        # 文件路径输入
        file_path_frame = ttk.Frame(self.file_preview_frame)
        file_path_frame.pack(fill="x", pady=16)
        
        self.file_path_var = tk.StringVar()
        ttk.Entry(file_path_frame, textvariable=self.file_path_var).pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 8))
        ttk.Button(file_path_frame, text="浏览", command=self.browse_file).pack(side=tk.LEFT)
        
        # 文件内容预览
        self.file_content = scrolledtext.ScrolledText(self.file_preview_frame, height=10)
        self.file_content.pack(fill="x", pady=(0, 16))
        self.file_content.configure(font=("Courier", 9))
        
        # 操作提示
        tip_frame = ttk.Frame(left_frame, style="Card.TFrame")
        tip_frame.pack(fill="x")
        
        tip_content = ttk.Frame(tip_frame)
        tip_content.pack(fill="x", pady=16, padx=16)
        
        label = ttk.Label(tip_content, text="💡")
        label.pack(side=tk.LEFT, padx=12)
        label.configure(font=("Arial", 16))
        tip_text = ttk.Frame(tip_content)
        tip_text.pack(side=tk.LEFT, fill="x", expand=True)
        label = ttk.Label(tip_text, text="提示：")
        label.pack(anchor="w")
        label.configure(foreground="#d97706", font=("Microsoft YaHei", 10, "bold"))
        label = ttk.Label(tip_text, text="请确保 DB 块未启用""优化块访问""，否则无法准确计算偏移地址。对于数组类型，转换器将自动展开为单个点位。")
        label.pack(anchor="w")
        label.configure(foreground="#d97706", font=("Microsoft YaHei", 10))
        
        # 右侧：配置参数
        right_frame = ttk.Frame(content, width=300)
        right_frame.pack(side=tk.RIGHT, fill="y")
        
        # 配置卡片
        config_card = ttk.Frame(right_frame, style="Card.TFrame")
        config_card.pack(fill="x", pady=(0, 24))
        
        # 配置标题
        config_header = ttk.Frame(config_card)
        config_header.pack(fill="x", pady=24, padx=24)
        label = ttk.Label(config_header, text="转换配置参数")
        label.pack(side=tk.LEFT)
        label.configure(foreground="#1e293b", font=("Microsoft YaHei", 14, "bold"))
        
        # 配置项
        config_items = ttk.Frame(config_card)
        config_items.pack(fill="x", padx=24, pady=(0, 24))
        
        # 通道名称
        self.channel_name_var = tk.StringVar(value="以太网<192.168.10.11>")
        self._config_row(config_items, "通道名称", self.channel_name_var)
        
        # 设备名称
        self.device_name_var = tk.StringVar(value="PLC1")
        self._config_row(config_items, "设备名称", self.device_name_var)
        
        # 驱动类型
        self.driver_var = tk.StringVar(value="S71200Tcp")
        self._config_row(config_items, "驱动类型", self.driver_var, is_combobox=True, values=["S71500Tcp", "S71200Tcp", "S7300Tcp", "S7400Tcp"])
        
        # 设备系列
        self.device_series_var = tk.StringVar(value="S7-1200")
        self._config_row(config_items, "设备系列", self.device_series_var, is_combobox=True, values=["S7-1500", "S7-1200", "S7-300", "S7-400"])
        
        # 起始TagID
        self.start_tag_id_var = tk.IntVar(value=50000)
        self._config_row(config_items, "起始TagID", self.start_tag_id_var)
        
        # 默认DB号
        self.db_number_var = tk.IntVar(value=3)
        self._config_row(config_items, "默认DB号", self.db_number_var)
        
        # 分组名称
        self.tag_group_var = tk.StringVar(value="PLC1.Device")
        self._config_row(config_items, "分组名称", self.tag_group_var)
        
        # 采集周期
        self.collect_interval_var = tk.IntVar(value=1000)
        self._config_row(config_items, "采集周期(ms)", self.collect_interval_var)
        
        # 历史间隔
        self.his_interval_var = tk.IntVar(value=60)
        self._config_row(config_items, "历史间隔(s)", self.his_interval_var)
        
        # 开始转换按钮
        convert_btn = ttk.Button(config_card, text="开始转换分析", style="Accent.TButton", command=self.start_conversion)
        convert_btn.pack(fill="x", pady=24, padx=24)
        
        # 兼容性说明
        compat_card = ttk.Frame(right_frame, style="Card.TFrame")
        compat_card.pack(fill="x")
        
        # 兼容性标题
        compat_header = ttk.Frame(compat_card, style="DarkBg.TFrame")
        compat_header.pack(fill="x", pady=16, padx=16)
        label = ttk.Label(compat_header, text="兼容性说明")
        label.pack(side=tk.LEFT)
        label.configure(foreground="white", font=("Microsoft YaHei", 12, "bold"))
        
        # 兼容性列表
        compat_list = ttk.Frame(compat_card, style="DarkBg.TFrame")
        compat_list.pack(fill="x", padx=16, pady=(0, 16))
        
        compat_items = [
            "TIA Portal V14 / V15 / V16 / V17 / V18",
            "支持 UDT 用户自定义数据类型",
            "Kingscads V3.5+ 点表协议"
        ]
        
        for item in compat_items:
            item_frame = ttk.Frame(compat_list, style="DarkBg.TFrame")
            item_frame.pack(fill="x", pady=4)
            label = ttk.Label(item_frame, text="✓")
            label.pack(side=tk.LEFT, padx=8)
            label.configure(foreground="#10b981", font=("Arial", 10))
            label = ttk.Label(item_frame, text=item)
            label.pack(side=tk.LEFT)
            label.configure(foreground="#e2e8f0", font=("Microsoft YaHei", 10))

    def _config_row(self, parent, label, var, is_combobox=False, values=None):
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill="x", pady=8)
        
        label_widget = ttk.Label(row_frame, text=label)
        label_widget.pack(side=tk.TOP, anchor="w", pady=4)
        label_widget.configure(foreground="#64748b", font=("Microsoft YaHei", 9, "bold"))
        
        if is_combobox:
            combobox = ttk.Combobox(row_frame, textvariable=var, values=values, state="readonly")
            combobox.pack(fill="x")
        else:
            ttk.Entry(row_frame, textvariable=var).pack(fill="x")

    def build_footer(self):
        footer = ttk.Frame(self.root, style="Header.TFrame", height=60)
        footer.pack(fill="x", pady=0)
        footer.pack_propagate(False)
        
        label = ttk.Label(footer, text="© 2026 工业自动化点表工具 - 助力工程师实现效率飞跃")
        label.pack(side=tk.TOP, pady=20)
        label.configure(foreground="#64748b", font=("Microsoft YaHei", 10))

    # ============================================================
    # 功能方法
    # ============================================================
    def get_current_config(self):
        return {
            "default_db_number": self.db_number_var.get(),
            "start_tag_id": self.start_tag_id_var.get(),
            "device_name": self.device_name_var.get(),
            "driver": self.driver_var.get(),
            "device_series": self.device_series_var.get(),
            "tag_group": self.tag_group_var.get(),
            "collect_interval": self.collect_interval_var.get(),
            "his_interval": self.his_interval_var.get(),
            "channel_name": self.channel_name_var.get(),
        }

    def browse_file(self):
        fn = filedialog.askopenfilename()
        if fn:
            self.file_path_var.set(fn)
            with open(fn, "r", encoding="utf-8") as f:
                self.file_content.delete(1.0, tk.END)
                self.file_content.insert(1.0, f.read())

    def start_conversion(self):
        text = self.file_content.get(1.0, tk.END).strip()

        if not text:
            messagebox.showwarning("提示", "没有输入内容")
            return

        threading.Thread(target=self.do_conversion, args=(text,), daemon=True).start()

    def do_conversion(self, text):
        conv = TiaToKingscadaConverter(self.get_current_config())
        self.conversion_result = conv.convert(text)
        self.root.after(0, self.show_result)

    def show_result(self):
        # 创建结果窗口
        result_window = tk.Toplevel(self.root)
        result_window.title("转换结果")
        result_window.geometry("1000x600")
        
        # 结果内容
        result_frame = ttk.Frame(result_window)
        result_frame.pack(fill="both", expand=True, padx=24, pady=24)
        
        # 统计信息
        stats_frame = ttk.Frame(result_frame, style="Card.TFrame")
        stats_frame.pack(fill="x", pady=(0, 24))
        
        stats_text = tk.Text(stats_frame, height=5)
        stats_text.pack(fill="both", expand=True, pady=16, padx=16)
        stats_text.configure(font=("Microsoft YaHei", 9))
        stats = self.conversion_result["stats"]
        stats_text.insert(1.0, str(stats))
        
        # 结果表格
        cols = ("TagID","TagName","Description","TagDataType","ItemName")
        result_tree = ttk.Treeview(result_frame, columns=cols, show="headings")
        for c in cols:
            result_tree.heading(c, text=c)
            result_tree.column(c, width=160)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=result_tree.yview)
        result_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        result_tree.pack(fill="both", expand=True, pady=24)
        
        # 填充数据
        df = self.conversion_result["dataframe"]
        for _, r in df.head(50).iterrows():
            result_tree.insert("", tk.END, values=(
                r["TagID"], r["TagName"], r["Description"],
                r["TagDataType"], r["ItemName"]
            ))
        
        # 操作按钮
        btn_frame = ttk.Frame(result_frame)
        btn_frame.pack(fill="x", pady=24)
        
        ttk.Button(btn_frame, text="导出CSV", command=self.export_csv).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="关闭", command=result_window.destroy).pack(side=tk.RIGHT, padx=8)

    def export_csv(self):
        if not hasattr(self, "conversion_result"):
            return
        fn = filedialog.asksaveasfilename(defaultextension=".csv")
        if fn:
            self.conversion_result["dataframe"].to_csv(fn, index=False, encoding="gbk")


def main():
    root = tk.Tk()
    TiaToKingscadaGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
