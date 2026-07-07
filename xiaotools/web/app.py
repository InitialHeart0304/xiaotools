from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, Response
import pandas as pd
import re
import json
import os
import sys
from datetime import datetime
import tempfile
from openpyxl.styles import Font, Border
import asyncio
import zipfile
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import uuid

# 添加父目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入核心转换功能
from src.core.converter import TiaToKingscadaConverter

# 尝试导入edge-tts
try:
    import edge_tts
except ImportError:
    edge_tts = None

app = Flask(__name__)

# 配置密钥，用于会话管理
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')

# 配置上传文件大小限制（16MB）
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 配置模板目录 - 使用绝对路径
app.root_path = os.path.dirname(os.path.abspath(__file__))
app.template_folder = os.path.join(app.root_path, 'templates')
app.static_folder = os.path.join(app.root_path, 'static')
print(f"App root path: {app.root_path}")
print(f"Template folder: {app.template_folder}")
print(f"Static folder: {app.static_folder}")

# 用户数据文件路径
USERS_FILE = os.path.join(app.root_path, 'data', 'users.json')

# 临时文件存储
TEMP_DIR = tempfile.gettempdir()
current_result = None

# 批量任务进度存储 {task_id: {"total": int, "completed": int, "failed": int, "done": bool, "error": str}}
_batch_progress = {}
_batch_lock = threading.Lock()
_batch_async_lock = asyncio.Lock()

def check_ffmpeg_available():
    try:
        import shutil
        # 检查ffmpeg是否可用
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            # 如果找到ffmpeg，配置pydub使用它
            try:
                from pydub import AudioSegment
                AudioSegment.converter = ffmpeg_path
            except ImportError:
                pass
            return True
        return False
    except Exception as e:
        print(f"[Init] ffmpeg check error: {e}")
        return False

FFMPEG_AVAILABLE = check_ffmpeg_available()
print(f"[Init] ffmpeg available: {FFMPEG_AVAILABLE}")

MINIAUDIO_AVAILABLE = False
try:
    import miniaudio
    MINIAUDIO_AVAILABLE = True
    print(f"[Init] miniaudio available: True")
except ImportError:
    print(f"[Init] miniaudio available: False")

VOICES = {
    "xiaoxiao": ("晓晓 (中文女声)", "zh-CN-XiaoxiaoNeural"),
    "xiaoyi": ("晓伊 (中文女声)", "zh-CN-XiaoyiNeural"),
    "yunjian": ("云健 (中文男声)", "zh-CN-YunjianNeural"),
    "yunyang": ("云扬 (中文男声)", "zh-CN-YunyangNeural"),
    "yunxi": ("云夕 (中文女声)", "zh-CN-YunxiNeural"),
    "yunze": ("云泽 (中文男声)", "zh-CN-YunzeNeural"),
    "xiaoxiao-multi": ("晓晓-多语言", "zh-CN-XiaoxiaoMultilingualNeural"),
}

TEXT_COL_KEYWORDS = ["文本", "文字", "text", "content", "内容", "语音", "语句", "句子"]
FILENAME_COL_KEYWORDS = ["文件名", "文件", "名称", "name", "filename", "标题", "标识", "编号", "code", "id"]

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def check_login():
    return 'username' in session

# ==================== 音频处理工具辅助函数 ====================

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = name.strip().strip(".")
    if len(name) > 80:
        name = name[:80]
    return name or "unnamed"

def format_filename(template: str, index: int, text: str, total: int = 0) -> str:
    now = datetime.now()
    short_text = sanitize_filename(text[:12]) if text else ""
    replacements = {
        "{序号}": f"{index:03d}",
        "{序号4}": f"{index:04d}",
        "{总数}": f"{total:03d}",
        "{日期}": now.strftime("%Y%m%d"),
        "{时间}": now.strftime("%H%M%S"),
        "{年月日}": now.strftime("%Y-%m-%d"),
        "{时分秒}": now.strftime("%H-%M-%S"),
        "{日期时间}": now.strftime("%Y%m%d_%H%M%S"),
        "{文本}": short_text,
    }
    result = template if template else "output_{序号}"
    for key, val in replacements.items():
        result = result.replace(key, val)
    return sanitize_filename(result)

def preprocess_text(text: str) -> str:
    """文本预处理：下划线替换为空格，英文字母单独读出"""
    if not text:
        return text
    
    # 下划线替换为空格
    text = text.replace('_', ' ')
    
    # 英文字母单独读出
    text = re.sub(r'([a-zA-Z])', lambda m: ' ' + m.group(0) + ' ', text)
    
    # 清理多余空格
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def generate_audio_sync(text, voice_code, rate="+0%", volume="+0%", fmt="mp3", timeout=60, retry=3):
    """生成音频，返回 (BytesIO对象, 实际格式)"""
    fmt = fmt.lower().strip() if fmt else "mp3"
    if fmt not in ("mp3", "wav"):
        fmt = "mp3"
    
    text = preprocess_text(text)
    
    for attempt in range(retry):
        loop = None
        mp3_path = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            communicate = edge_tts.Communicate(text, voice_code, rate=rate, volume=volume)
            fd, mp3_path = tempfile.mkstemp(suffix=".mp3", prefix="tts_")
            os.close(fd)
            
            future = asyncio.wait_for(communicate.save(mp3_path), timeout=timeout)
            loop.run_until_complete(future)
            
            with open(mp3_path, 'rb') as f:
                mp3_data = f.read()
            
            if fmt == "mp3":
                buffer = io.BytesIO(mp3_data)
                buffer.seek(0)
                return buffer, "mp3"
            
            wav_data = mp3_to_wav_bytes(mp3_data)
            buffer = io.BytesIO(wav_data)
            buffer.seek(0)
            return buffer, "wav"
        
        except asyncio.TimeoutError:
            print(f"[Audio] 超时，重试 ({attempt+1}/{retry})")
            if attempt == retry - 1:
                raise Exception(f"音频生成超时（{timeout}秒）")
        except Exception as e:
            print(f"[Audio] 生成失败 ({attempt+1}/{retry}): {type(e).__name__}: {str(e)}")
            if attempt == retry - 1:
                raise
        finally:
            try:
                if loop:
                    loop.close()
            except Exception:
                pass
            if mp3_path and os.path.exists(mp3_path):
                try:
                    os.unlink(mp3_path)
                except OSError:
                    pass

def mp3_to_wav_bytes(mp3_data):
    """将MP3字节数据转换为WAV字节数据，优先使用miniaudio（纯Python，无需ffmpeg）"""
    if MINIAUDIO_AVAILABLE:
        import miniaudio
        decoded = miniaudio.decode(mp3_data, nchannels=2, sample_rate=24000)
        wav_buf = io.BytesIO()
        import wave
        with wave.open(wav_buf, 'wb') as wf:
            wf.setnchannels(decoded.nchannels)
            wf.setsampwidth(2)
            wf.setframerate(decoded.sample_rate)
            wf.writeframes(decoded.samples.tobytes())
        wav_buf.seek(0)
        return wav_buf.read()
    
    if FFMPEG_AVAILABLE:
        mp3_fd, mp3_path = tempfile.mkstemp(suffix=".mp3", prefix="tts_mp3_")
        wav_fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="tts_wav_")
        os.close(mp3_fd)
        os.close(wav_fd)
        try:
            with open(mp3_path, 'wb') as f:
                f.write(mp3_data)
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(mp3_path, format="mp3")
                audio.export(wav_path, format="wav")
            except ImportError:
                import subprocess
                result = subprocess.run(
                    ["ffmpeg", "-i", mp3_path, "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "2", wav_path, "-y"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    raise Exception(f"ffmpeg转换失败: {result.stderr}")
            with open(wav_path, 'rb') as f:
                return f.read()
        finally:
            for p in [mp3_path, wav_path]:
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
    
    raise Exception("无法转换为WAV格式：服务器未安装ffmpeg且miniaudio不可用。")


async def generate_audio_async(text, voice_code, rate="+0%", volume="+0%", fmt="mp3", timeout=120):
    """异步生成音频，返回 (bytes数据, 实际格式)"""
    fmt = fmt.lower().strip() if fmt else "mp3"
    if fmt not in ("mp3", "wav"):
        fmt = "mp3"
    
    text = preprocess_text(text)
    
    mp3_path = None
    try:
        communicate = edge_tts.Communicate(text, voice_code, rate=rate, volume=volume)
        fd, mp3_path = tempfile.mkstemp(suffix=".mp3", prefix="tts_")
        os.close(fd)
        
        await asyncio.wait_for(communicate.save(mp3_path), timeout=timeout)
        
        with open(mp3_path, 'rb') as f:
            mp3_data = f.read()
        
        if fmt == "mp3":
            return mp3_data, "mp3"
        
        wav_data = mp3_to_wav_bytes(mp3_data)
        return wav_data, "wav"
    
    finally:
        if mp3_path and os.path.exists(mp3_path):
            try:
                os.unlink(mp3_path)
            except OSError:
                pass

async def generate_audio_with_retry_async(text, voice_code, rate="+0%", volume="+0%", fmt="mp3", timeout=120, retry=5, semaphore=None):
    """带重试的异步音频生成，支持 Semaphore 并发限制"""
    async def _do_generate():
        return await generate_audio_async(text, voice_code, rate, volume, fmt, timeout)
    
    for attempt in range(retry):
        try:
            if semaphore:
                async with semaphore:
                    return await _do_generate()
            else:
                return await _do_generate()
        except asyncio.TimeoutError:
            print(f"[Audio] 超时，重试 ({attempt+1}/{retry})")
            if attempt == retry - 1:
                raise
        except Exception as e:
            print(f"[Audio] 生成失败 ({attempt+1}/{retry}): {str(e)}")
            if attempt == retry - 1:
                raise

def detect_columns(headers):
    """智能识别文本列和文件名列的位置"""
    def score(h, keywords):
        if not h:
            return 0
        s = str(h).strip().lower()
        score = 0
        for kw in keywords:
            k = kw.lower()
            if s == k:
                score += 100
            elif k in s:
                score += 50
        return score
    
    text_scores = [(score(h, TEXT_COL_KEYWORDS), i) for i, h in enumerate(headers)]
    name_scores = [(score(h, FILENAME_COL_KEYWORDS), i) for i, h in enumerate(headers)]
    
    text_scores.sort(reverse=True)
    name_scores.sort(reverse=True)
    
    text_col = text_scores[0][1] if text_scores and text_scores[0][0] > 0 else None
    name_col = name_scores[0][1] if name_scores and name_scores[0][0] > 0 else None
    
    # 避免选中同一列
    if text_col is not None and name_col == text_col:
        name_col = next((s[1] for s in name_scores if s[1] != text_col and s[0] > 0), None)
    
    return text_col, name_col

def _read_xlsx(file_storage):
    """读取上传的 Excel 文件（纯 Python 实现）"""
    data = file_storage.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        # 读取shared strings
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_tree = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            for si in ss_tree.findall('s:si', ns):
                texts = [t.text or '' for t in si.findall('.//s:t', ns)]
                shared.append(''.join(texts))
        # 读取sheet1
        sheet_xml = zf.read("xl/worksheets/sheet1.xml")
        tree = ET.fromstring(sheet_xml)
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        rows = []
        for row in tree.findall('.//s:row', ns):
            cells = row.findall('s:c', ns)
            values = []
            for cell in cells:
                t = cell.get('t')
                v = cell.find('s:v', ns)
                if v is None:
                    values.append(None)
                    continue
                val = v.text
                if t == 's' and val is not None:
                    idx = int(val)
                    values.append(shared[idx] if idx < len(shared) else '')
                else:
                    values.append(val)
            rows.append(values)
        zf.close()
        
        if not rows:
            return [], []
        headers = [str(h).strip() if h else f"列{i+1}" for i, h in enumerate(rows[0])]
        return headers, rows[1:]
    except Exception as e:
        raise RuntimeError(f"Excel解析失败: {e}")


def _build_xlsx(headers, rows):
    """构建 XLSX 文件，返回 BytesIO（纯 Python 实现）"""
    all_strings = []
    string_index = {}

    def add_string(s):
        s = str(s)
        if s not in string_index:
            string_index[s] = len(all_strings)
            all_strings.append(s)
        return string_index[s]

    for h in headers:
        add_string(h)
    for row in rows:
        for cell in row:
            if cell is not None:
                add_string(cell)

    from xml.sax.saxutils import escape as xml_escape
    ss_xml_parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="' +
                    str(len(all_strings)) + '" uniqueCount="' + str(len(all_strings)) + '">']
    for s in all_strings:
        ss_xml_parts.append(f'<si><t>{xml_escape(s)}</t></si>')
    ss_xml_parts.append('</sst>')
    shared_strings = ''.join(ss_xml_parts)

    col_count = len(headers)
    total_rows = len(rows) + 1

    sheet_parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="x14ac" xmlns:x14ac="http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac">',
        '<dimension ref="A1:' + chr(ord('A') + col_count - 1) + str(total_rows) + '"/>',
        '<sheetViews><sheetView tabSelected="1" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
        '<sheetFormatPr defaultRowHeight="15"/>',
        '<cols>'
    ]
    for i, width in enumerate([50, 25, 20] + [15] * max(0, col_count - 3)):
        sheet_parts.append(f'<col min="{i+1}" max="{i+1}" width="{width}" customWidth="1"/>')
    sheet_parts.append('</cols><sheetData>')

    def col_letter(idx):
        return chr(ord('A') + idx)

    def write_row(r, cells, row_idx):
        row_xml = [f'<row r="{row_idx+1}" spans="1:{len(cells)}">']
        for i, val in enumerate(cells):
            if val is None:
                continue
            ref = col_letter(i) + str(row_idx + 1)
            is_header = row_idx == 0
            idx = add_string(val)
            if is_header:
                row_xml.append(f'<c r="{ref}" t="s" s="1"><v>{idx}</v></c>')
            else:
                row_xml.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
        row_xml.append('</row>')
        return ''.join(row_xml)

    sheet_parts.append(write_row(1, headers, 0))
    for i, row in enumerate(rows):
        sheet_parts.append(write_row(i+2, row, i+1))

    sheet_parts.append('</sheetData><phoneticPr fontId="1" type="noConversion"/>')
    sheet_parts.append('<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>')
    sheet_parts.append('</worksheet>')
    sheet_xml = ''.join(sheet_parts)

    workbook_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="语音文本" sheetId="1" r:id="rId1"/></sheets></workbook>'''

    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF4472C4"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''

    rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>'''

    wb_rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>'''

    core_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>TTS Tool</dc:creator><cp:lastModifiedBy>TTS Tool</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">2026-06-17T12:00:00Z</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">2026-06-17T12:00:00Z</dcterms:modified></cp:coreProperties>'''

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>''')
        zf.writestr('_rels/.rels', rels_xml)
        zf.writestr('xl/workbook.xml', workbook_xml)
        zf.writestr('xl/_rels/workbook.xml.rels', wb_rels_xml)
        zf.writestr('xl/worksheets/sheet1.xml', sheet_xml)
        zf.writestr('xl/styles.xml', styles_xml)
        zf.writestr('xl/sharedStrings.xml', shared_strings)
        zf.writestr('docProps/core.xml', core_xml)

    buffer.seek(0)
    return buffer

@app.route('/')
def index():
    # 移除登录检查，允许未登录用户访问音频处理功能
    # if not check_login():
    #     return redirect(url_for('login'))
    
    current_date = datetime.now().strftime("%Y年%m月%d日")
    current_user = session.get('username', '')
    # 打印模板文件路径，用于调试
    template_path = os.path.join(app.template_folder, 'index.html')
    print(f"Template path: {template_path}")
    print(f"Template exists: {os.path.exists(template_path)}")
    return render_template('index.html', current_date=current_date, current_user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        for user in users:
            if user['username'] == username and user['password'] == password:
                session['username'] = username
                return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': '用户名或密码错误'})
    
    if check_login():
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/ico/<path:filename>')
def serve_ico(filename):
    return send_file(os.path.join(app.root_path, 'ico', filename))

@app.route('/upload', methods=['POST'])
def upload_file():
    if not check_login():
        return jsonify({'success': False, 'error': '请先登录'})
        
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'})
    
    if file:
        # 读取文件内容
        content = file.read().decode('utf-8')
        return jsonify({'success': True, 'content': content})

@app.route('/convert', methods=['POST'])
def convert():
    if not check_login():
        return jsonify({'success': False, 'error': '请先登录'})
        
    global current_result
    
    # 获取文件内容
    file_content = request.form.get('file_content')
    if not file_content:
        return jsonify({'success': False, 'error': 'No file content'})
    
    # 获取配置参数
    conversion_config = {
        "default_db_number": int(request.form.get('db_number', 3)),
        "start_tag_id": int(request.form.get('start_tag_id', 50000)),
        "device_name": request.form.get('device_name', 'PLC1'),
        "driver": request.form.get('driver', 'S71200Tcp'),
        "device_series": request.form.get('device_series', 'S7-1200'),
        "tag_group": request.form.get('tag_group', 'PLC1.Device'),
        "collect_interval": int(request.form.get('collect_interval', 1000)),
        "his_interval": int(request.form.get('his_interval', 60)),
        "channel_name": request.form.get('channel_name', '以太网<192.168.10.11>'),
    }
    
    try:
        # 执行转换
        conv = TiaToKingscadaConverter(conversion_config)
        result = conv.convert(file_content)
        
        # 保存结果
        current_result = result
        
        # 准备返回数据（只返回前端显示需要的列）
        data = []
        for _, row in result['dataframe'].iterrows():
            data.append({
                'TagID': row['TagID'],
                'TagName': row['TagName'],
                'Description': row['Description'],
                'TagDataType': row['TagDataType'],
                'ItemName': row['ItemName']
            })
        
        # 打印统计信息，用于调试
        print("转换结果统计:", result['stats'])
        print("数据框长度:", len(result['dataframe']))
        print("数据框列数:", len(result['dataframe'].columns))
        print("数据框列名:", result['dataframe'].columns.tolist())
        
        return jsonify({
            'success': True,
            'stats': result['stats'],
            'data': data
        })
    except Exception as e:
        print("转换错误:", str(e))
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download')
def download():
    if not check_login():
        return jsonify({'success': False, 'error': '请先登录'})
        
    global current_result
    
    if not current_result:
        return jsonify({'success': False, 'error': 'No conversion result'})
    
    # 获取格式参数
    export_format = request.args.get('format', 'csv').lower()
    filename = request.args.get('filename', 'conversion_result')
    
    try:
        if export_format == 'excel' or export_format == 'xlsx':
            # Excel格式（单Sheet）- 导出完整列
            temp_file = os.path.join(TEMP_DIR, f"{filename}_{datetime.now().timestamp()}.xlsx")
            current_result['dataframe'].to_excel(temp_file, index=False, engine='openpyxl')
            return send_file(temp_file, as_attachment=True, download_name=f'{filename}.xlsx')
        elif export_format == 'excel-multi':
            # Excel格式（多Sheet）- 按数据类型分Sheet
            conv = TiaToKingscadaConverter({
                'default_db_number': 3,
                'start_tag_id': 50000,
                'device_name': 'PLC1',
                'driver': 'S71200Tcp',
                'device_series': 'S7-1200',
                'tag_group': 'PLC1.Device',
                'collect_interval': 1000,
                'his_interval': 60,
                'channel_name': '以太网<192.168.10.11>'
            })
            sheets = conv.create_multi_sheet_dataframes(current_result['dataframe'])
            temp_file = os.path.join(TEMP_DIR, f"{filename}_{datetime.now().timestamp()}.xlsx")
            with pd.ExcelWriter(temp_file, engine='openpyxl') as writer:
                for sheet_name, df in sheets.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    # 获取工作表对象，将第一行字体设为非粗体
                    worksheet = writer.sheets[sheet_name]
                    for cell in worksheet[1]:   # 第一行所有单元格
                        cell.font = Font(bold=False)
                        cell.border = Border()  # 等同于无边框
            return send_file(temp_file, as_attachment=True, download_name=f'{filename}.xlsx')
        elif export_format == 'json':
            # JSON格式 - 导出完整数据
            temp_file = os.path.join(TEMP_DIR, f"{filename}_{datetime.now().timestamp()}.json")
            result_data = current_result['dataframe'].to_dict('records')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            return send_file(temp_file, as_attachment=True, download_name=f'{filename}.json')
        else:
            # 默认CSV格式 - 导出完整列
            temp_file = os.path.join(TEMP_DIR, f"{filename}_{datetime.now().timestamp()}.csv")
            current_result['dataframe'].to_csv(temp_file, index=False, encoding='gbk')
            return send_file(temp_file, as_attachment=True, download_name=f'{filename}.csv')
    except Exception as e:
        print("下载错误:", str(e))
        return jsonify({'success': False, 'error': str(e)})


# ==================== 音频处理工具API路由 ====================

@app.route('/audio/api/status', methods=["GET"])
def audio_api_status():
    return jsonify({
        "edge_tts_available": edge_tts is not None,
        "ffmpeg_available": FFMPEG_AVAILABLE,
        "supported_formats": ["mp3"] + (["wav"] if FFMPEG_AVAILABLE else []),
    })

@app.route('/audio/api/preview', methods=["POST"])
def audio_api_preview():
    data = request.json
    text = (data.get("text") or "").strip()
    voice_key = data.get("voice", "xiaoxiao")
    rate = data.get("rate", "+0%")
    volume = data.get("volume", "+0%")
    fmt = data.get("format", "mp3")
    
    print(f"[Audio Preview] text={text[:50]}, voice={voice_key}, rate={rate}, volume={volume}, fmt={fmt}")
    
    if not text:
        return jsonify({"error": "文本不能为空"}), 400
    
    voice_code = VOICES.get(voice_key, VOICES["xiaoxiao"])[1]
    try:
        audio_buffer, actual_fmt = generate_audio_sync(text, voice_code, rate, volume, fmt)
        print(f"[Audio Preview] Generated format: {actual_fmt}")
        
        mime = "audio/wav" if actual_fmt == "wav" else "audio/mpeg"
        return send_file(audio_buffer, mimetype=mime, as_attachment=False)
    except Exception as e:
        print(f"[Audio Preview Error] {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/audio/api/batch', methods=["POST"])
def audio_api_batch():
    data = request.json
    lines = [l.strip() for l in data.get("lines", []) if l and l.strip()]
    voice_key = data.get("voice", "xiaoxiao")
    rate = data.get("rate", "+0%")
    volume = data.get("volume", "+0%")
    filename_template = data.get("filename", "output_{序号}")
    fmt = data.get("format", "mp3")
    task_id = data.get("task_id")
    
    if not lines:
        return jsonify({"error": "文本行不能为空"}), 400
    
    voice_code = VOICES.get(voice_key, VOICES["xiaoxiao"])[1]
    total = len(lines)
    
    if task_id:
        with _batch_lock:
            _batch_progress[task_id] = {"total": total, "completed": 0, "failed": 0, "done": False, "error": None}
    
    async def batch_generate():
        semaphore = asyncio.Semaphore(5)
        
        async def create_task(index, text):
            try:
                audio_data, actual_fmt = await generate_audio_with_retry_async(
                    text, voice_code, rate, volume, fmt, semaphore=semaphore
                )
                base_name = format_filename(filename_template, index, text, total)
                out_name = f"{base_name}.{actual_fmt}"
                
                if task_id:
                    async with _batch_async_lock:
                        if task_id in _batch_progress:
                            _batch_progress[task_id]["completed"] += 1
                
                return {"success": True, "index": index, "name": out_name, "data": audio_data}
            except Exception as e:
                if task_id:
                    async with _batch_async_lock:
                        if task_id in _batch_progress:
                            _batch_progress[task_id]["failed"] += 1
                return {"success": False, "index": index, "text": text[:50] + "..." if len(text) > 50 else text, "error": str(e)}
        
        tasks = [create_task(i + 1, line) for i, line in enumerate(lines)]
        results = await asyncio.gather(*tasks)
        return results
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results = loop.run_until_complete(batch_generate())
    loop.close()
    
    used_names = set()
    success_count = 0
    failed_count = 0
    
    for r in results:
        if r["success"]:
            base_name = r["name"].rsplit('.', 1)[0]
            final_name = base_name
            n = 1
            while final_name in used_names:
                final_name = f"{base_name}_{n}"
                n += 1
            used_names.add(final_name)
            r["final_name"] = final_name + "." + r["name"].rsplit('.', 1)[1]
            success_count += 1
        else:
            failed_count += 1
    
    if task_id:
        with _batch_lock:
            if task_id in _batch_progress:
                _batch_progress[task_id]["done"] = True
                _batch_progress[task_id]["success_count"] = success_count
                _batch_progress[task_id]["failed_count"] = failed_count
    
    if success_count == 0:
        return jsonify({"error": "所有文件都生成失败"}), 500
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            if r["success"]:
                zf.writestr(r["final_name"], r["data"])
    
    zip_buffer.seek(0)
    filename = f"tts_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    response = send_file(zip_buffer, mimetype="application/zip",
                         as_attachment=True,
                         download_name=filename)
    
    response.headers['X-Success-Count'] = str(success_count)
    response.headers['X-Failed-Count'] = str(failed_count)
    
    return response

@app.route('/audio/api/custom-batch', methods=["POST"])
def audio_api_custom_batch():
    try:
        data = request.json
        items = data.get("items", [])
        voice_key = data.get("voice", "xiaoxiao")
        rate = data.get("rate", "+0%")
        volume = data.get("volume", "+0%")
        default_template = data.get("default_template", "output_{序号}")
        fmt = data.get("format", "mp3")
        task_id = data.get("task_id")
        
        if not items:
            return jsonify({"error": "文本行不能为空"}), 400
        
        voice_code = VOICES.get(voice_key, VOICES["xiaoxiao"])[1]
        total = len(items)
        
        valid_items = [(i + 1, item) for i, item in enumerate(items) if (item.get("text") or "").strip()]
        
        if task_id:
            with _batch_lock:
                _batch_progress[task_id] = {"total": len(valid_items), "completed": 0, "failed": 0, "done": False, "error": None}
        
        async def batch_generate():
            semaphore = asyncio.Semaphore(5)
            
            async def create_task(index, item):
                text = (item.get("text") or "").strip()
                custom_name = (item.get("filename") or "").strip()
                try:
                    audio_data, actual_fmt = await generate_audio_with_retry_async(
                        text, voice_code, rate, volume, fmt, semaphore=semaphore
                    )
                    base_name = sanitize_filename(custom_name) if custom_name \
                        else format_filename(default_template, index, text, total)
                    out_name = f"{base_name}.{actual_fmt}"
                    
                    if task_id:
                        async with _batch_async_lock:
                            if task_id in _batch_progress:
                                _batch_progress[task_id]["completed"] += 1
                    
                    return {"success": True, "index": index, "name": out_name, "data": audio_data}
                except Exception as e:
                    if task_id:
                        async with _batch_async_lock:
                            if task_id in _batch_progress:
                                _batch_progress[task_id]["failed"] += 1
                    return {"success": False, "index": index, "text": text[:50] + "..." if len(text) > 50 else text, "error": str(e)}
            
            tasks = [create_task(idx, item) for idx, item in valid_items]
            results = await asyncio.gather(*tasks)
            return results
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(batch_generate())
        loop.close()
        
        used_names = set()
        success_count = 0
        failed_count = 0
        
        for r in results:
            if r["success"]:
                base_name = r["name"].rsplit('.', 1)[0]
                final_name = base_name
                n = 1
                while final_name in used_names:
                    final_name = f"{base_name}_{n}"
                    n += 1
                used_names.add(final_name)
                r["final_name"] = final_name + "." + r["name"].rsplit('.', 1)[1]
                success_count += 1
            else:
                failed_count += 1
        
        if task_id:
            with _batch_lock:
                if task_id in _batch_progress:
                    _batch_progress[task_id]["done"] = True
                    _batch_progress[task_id]["success_count"] = success_count
                    _batch_progress[task_id]["failed_count"] = failed_count
        
        if success_count == 0:
            return jsonify({"error": "所有文件都生成失败"}), 500
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in results:
                if r["success"]:
                    zf.writestr(r["final_name"], r["data"])
        
        zip_buffer.seek(0)
        filename = f"tts_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        response = send_file(zip_buffer, mimetype="application/zip",
                             as_attachment=True,
                             download_name=filename)
        
        response.headers['X-Success-Count'] = str(success_count)
        response.headers['X-Failed-Count'] = str(failed_count)
        
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/audio/api/progress/<task_id>')
def audio_api_progress(task_id):
    """查询批量生成进度"""
    with _batch_lock:
        progress = _batch_progress.get(task_id)
    
    if not progress:
        return jsonify({"error": "任务不存在"}), 404
    
    return jsonify(progress)


@app.route('/audio/api/cleanup-progress', methods=["POST"])
def audio_api_cleanup_progress():
    """清理已完成的进度记录"""
    data = request.json or {}
    task_id = data.get("task_id")
    
    with _batch_lock:
        if task_id and task_id in _batch_progress:
            del _batch_progress[task_id]
            return jsonify({"success": True})
    
    return jsonify({"success": False, "error": "任务不存在"})


@app.route('/audio/api/progress-stream/<task_id>')
def audio_api_progress_stream(task_id):
    """SSE 进度流"""
    def event_stream():
        import time
        while True:
            with _batch_lock:
                progress = _batch_progress.get(task_id)
            
            if not progress:
                yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                break
            
            yield f"data: {json.dumps(progress)}\n\n"
            
            if progress.get("done"):
                with _batch_lock:
                    if task_id in _batch_progress:
                        del _batch_progress[task_id]
                break
            
            time.sleep(0.5)
    
    return Response(event_stream(), mimetype="text/event-stream")


@app.route('/audio/api/parse-excel', methods=["POST"])
def audio_api_parse_excel():
    # 音频处理工具不需要登录
    # if not check_login():
    #     return jsonify({'error': '请先登录'}), 401
        
    if "file" not in request.files:
        return jsonify({"error": "未找到文件"}), 400
    
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "文件名为空"}), 400
    
    try:
        headers, rows = _read_xlsx(f)
        if not headers:
            return jsonify({"error": "无法读取 Excel 文件"}), 400
        
        text_col, name_col = detect_columns(headers)
        
        if text_col is None:
            text_col = 0
        
        lines = []
        custom_names = []
        has_custom = False
        for row in rows:
            if not row:
                continue
            if text_col < len(row) and row[text_col] is not None:
                text = str(row[text_col]).strip()
                if text:
                    lines.append(text)
                    if name_col is not None and name_col < len(row) and row[name_col]:
                        custom_names.append(str(row[name_col]).strip())
                        has_custom = True
                    else:
                        custom_names.append("")
        
        detected_info = {
            "headers": headers,
            "text_column": headers[text_col] if text_col is not None else None,
            "text_column_index": text_col,
            "filename_column": headers[name_col] if name_col is not None else None,
            "filename_column_index": name_col,
        }
        
        return jsonify({
            "lines": lines,
            "custom_names": custom_names,
            "has_custom_names": has_custom,
            "count": len(lines),
            "detected": detected_info,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Excel 模板下载 ----------
@app.route('/audio/api/download-template', methods=["GET"])
def audio_api_download_template():
    # 音频处理工具不需要登录
    # if not check_login():
    #     return jsonify({'error': '请先登录'}), 401
        
    headers = ["文本", "文件名"]
    sample_rows = [
        ["生化池（东）_厌氧推流器1号_综合故障", "BIO_M0201_A_TFLT"],
        ["生化池（东）_厌氧推流器2号_故障信号", "BIO_M0202_A_FLT"],
        ["生化池（西）_缺氧推流器2号_综合故障", "BIO_M0203_A_TFLT"],
        ["欢迎光临我们的店铺", "欢迎语"],
        ["正在为您查询信息", "查询提示"],
        ["感谢您的耐心等待", "结束语"],
    ]
    
    try:
        buffer = _build_xlsx(headers, sample_rows)
        filename = f"语音转写模板_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return send_file(
            buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- 单文件生成 ----------
@app.route('/audio/api/generate', methods=["POST"])
def audio_api_generate():
    # 音频处理工具不需要登录
    # if not check_login():
    #     return jsonify({'error': '请先登录'}), 401
        
    data = request.json
    text = (data.get("text") or "").strip()
    voice_key = data.get("voice", "xiaoxiao")
    rate = data.get("rate", "+0%")
    volume = data.get("volume", "+0%")
    filename_template = data.get("filename", "tts_{日期时间}")
    fmt = data.get("format", "mp3")

    if not text:
        return jsonify({"error": "文本不能为空"}), 400

    voice_code = VOICES.get(voice_key, VOICES["xiaoxiao"])[1]
    try:
        audio_buffer, actual_fmt = generate_audio_sync(text, voice_code, rate, volume, fmt)
        filename = format_filename(filename_template, 1, text, 1) + f".{actual_fmt}"
        mime = "audio/wav" if actual_fmt == "wav" else "audio/mpeg"
        return send_file(audio_buffer, mimetype=mime, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- 文件名模板预览 ----------
@app.route('/audio/api/test-filename', methods=["POST"])
def audio_api_test_filename():
    # 音频处理工具不需要登录
    # if not check_login():
    #     return jsonify({'error': '请先登录'}), 401
        
    data = request.json
    template = data.get("template", "output_{序号}")
    sample_text = data.get("text", "示例文本内容")
    sample_total = max(int(data.get("total", 5)), 1)
    fmt = data.get("format", "mp3")

    preview = []
    for i in range(1, min(5, sample_total) + 1):
        preview.append(format_filename(template, i, sample_text, sample_total) + "." + fmt)
    return jsonify({"preview": preview, "template": template})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
