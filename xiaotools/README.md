# TIA DB-Kingscada 转换工具

工业自动化点表转换工具，用于将 TIA Portal 导出的变量表转换为 KingSCADA 点表格式。

## 功能特性

- 支持多种数据类型转换（Bool, Int, UInt, Real, DInt, Word, DWord）
- 自动识别设备行和变量行
- 生成完整的 KingSCADA 点表（包含 47 个字段）
- 支持自定义配置（DB编号、起始TagID、设备名称等）
- 实时统计分析和可视化展示
- 支持 CSV 格式导出

## 技术栈

- Python 3.11+
- Flask 2.3+
- pandas 2.1+
- Tailwind CSS 3
- ECharts

## 本地开发

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行开发服务器

```bash
python wsgi.py
```

访问 http://localhost:8080

## 部署到 Render

### 步骤 1：准备 GitHub 仓库

1. 将项目推送到 GitHub
2. 确保项目包含以下文件：
   - `wsgi.py` - WSGI 入口文件
   - `requirements.txt` - 依赖列表
   - `web/app.py` - Flask 应用
   - `src/core/converter.py` - 核心转换模块

### 步骤 2：在 Render 上创建 Web Service

1. 登录 [Render](https://render.com/)
2. 点击 "New +" -> "Web Service"
3. 选择你的 GitHub 仓库
4. 配置部署设置：
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:app`
   - **Environment**: Python 3.11
   - **Port**: 使用环境变量 `PORT`（Render 自动设置）

### 步骤 3：环境变量

无需额外环境变量，端口由 Render 自动提供。

### 步骤 4：部署

点击 "Create Web Service" 开始部署。

## 项目结构

```
├── src/
│   └── core/
│       └── converter.py    # 核心转换逻辑
├── web/
│   ├── app.py              # Flask 应用
│   ├── templates/          # HTML 模板
│   │   └── index.html      # 主页面
│   └── static/             # 静态资源
├── wsgi.py                 # WSGI 入口
├── requirements.txt        # 依赖列表
├── .gitignore              # Git 忽略文件
└── README.md               # 项目说明
```

## 使用说明

1. 在主页上传或粘贴 TIA 变量表内容
2. 配置转换参数（可选）
3. 点击"开始转换"按钮
4. 查看转换结果和统计信息
5. 导出 CSV 文件

## 输入格式

支持以下格式的 TIA 导出文件：
- 制表符分隔的文本文件
- 空格分隔的文本文件

输入示例：
```
DOS_FL_FIT0102    磁混凝(东)_2#加药流量计
W_DDZ    Bool    0.0    0    复位死区设置
F_PV    Real    0.0    0    瞬时流量(m3/h)
F_SP    Real    4.0    0    设定值(m3/h)
```

## 输出格式

输出 KingSCADA 点表格式，包含以下关键字段：
- TagID, TagName, Description
- TagDataType, ItemDataType
- ChannelName, DeviceName, ChannelDriver
- ItemName (寄存器地址)
- CollectInterval, HisInterval
- TagGroup

## License

MIT