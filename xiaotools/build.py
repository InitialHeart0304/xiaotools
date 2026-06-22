import os
import subprocess

# 尝试使用不同的图标路径
icon_paths = [
    os.path.abspath('assets/images/logo.ico'),
    os.path.abspath('web/img/logo.ico'),
    os.path.abspath('web/ico/hat_star_icon.ico'),
    os.path.abspath('assets/icons/hat_star_icon.ico'),
]

ico_path = None
for path in icon_paths:
    if os.path.exists(path):
        ico_path = path
        break

if ico_path:
    print(f'使用图标: {ico_path}')
else:
    print('未找到图标文件，使用默认图标')

# 创建版本信息文件
version_file_content = '''# UTF-8
#
# For more details about fixed file info 'ffi' see:
# https://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 1),
    prodvers=(1, 0, 0, 1),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,  # Win32
    fileType=0x1,  # Application
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904b0',  # English (US)
          [
            StringStruct(u'CompanyName', u'TIA DB Converter'),
            StringStruct(u'FileDescription', u'TIA DB块转Kingscada点表工具'),
            StringStruct(u'FileVersion', u'1.0.0.1'),
            StringStruct(u'InternalName', u'TIA-DB-Converter'),
            StringStruct(u'OriginalFilename', u'TIA-DB-Converter.exe'),
            StringStruct(u'ProductName', u'TIA DB转换工具'),
            StringStruct(u'ProductVersion', u'1.0.0.1'),
            StringStruct(u'LegalCopyright', u'© 2026 TIA DB Converter. ZHONGCANXIAO.')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1252])])  # English (US)
  ]
)'''

# 确保dist目录存在
if not os.path.exists('web/dist'):
    os.makedirs('web/dist')

# 切换到web目录
os.chdir('web')

# 删除旧的文件
if os.path.exists('TIA-DB-Converter.spec'):
    os.remove('TIA-DB-Converter.spec')
if os.path.exists('build'):
    import shutil
    shutil.rmtree('build')

# 写入版本信息文件
with open('version.txt', 'w', encoding='utf-8') as f:
    f.write(version_file_content)

print(f'版本信息文件已创建: web/version.txt')

# 执行打包命令
print('开始打包应用...')
args = [
        'pyinstaller',
        '--name', 'TIA-DB-Converter',
        '--onefile',
        # '--windowed',  # 显示控制台窗口
        '--add-data', 'templates;templates',
        '--add-data', 'static;static',
        '--add-data', '..\\src;src',
        '--icon', ico_path,
        '--version-file', 'version.txt',
        '--clean',
        'app.py'
    ]

subprocess.run(args)

print('打包完成！')
print('可执行文件位置: web/dist/TIA-DB-Converter.exe')
print('\n提示：如果图标没有立即显示，请尝试重启文件资源管理器或清除图标缓存。')