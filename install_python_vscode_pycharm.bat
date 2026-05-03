@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
title Python^&VSCode^&PyCharm 智能安装器
echo ================================================
echo    Python ^& VSCode ^& PyCharm 智能安装器
echo    自动检测已安装程序，避免重复安装
echo    兼容 Windows XP / 7 / 8 / 10 / 11
echo ================================================
echo.

:: ----------------- 1. 检测操作系统版本 -----------------
for /f "tokens=2 delims=[]" %%a in ('ver') do set "ver_str=%%a"
for /f "tokens=2-3 delims=. " %%b in ("%ver_str%") do (
    set "os_major=%%b"
    set "os_minor=%%c"
)

if %os_major% leq 5 (
    set "OS_CLASS=winxp"
) else if %os_major% equ 6 (
    if %os_minor% leq 1 (
        set "OS_CLASS=win7"
    ) else (
        set "OS_CLASS=modern"
    )
) else (
    set "OS_CLASS=modern"
)
echo [*] 系统类别: %OS_CLASS%

:: ----------------- 2. 检测系统架构 -----------------
set "ARCH=32"
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" set "ARCH=64"
if "%PROCESSOR_ARCHITEW6432%"=="AMD64" set "ARCH=64"
if "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=ARM64"
echo [*] 系统架构: %ARCH%

:: ----------------- 3. 准备临时目录 -----------------
set "TMPDIR=%TEMP%\pyvscode_setup"
if not exist "%TMPDIR%" mkdir "%TMPDIR%"

:: ----------------- 4. 检测 Python 是否已安装 -----------------
set "PY_INSTALLED=0"
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_INSTALLED=1"
) else (
    rem XP/旧版可能未加入PATH，检查安装目标路径
    if "%OS_CLASS%"=="winxp" (
        if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python34\python.exe" set "PY_INSTALLED=1"
    ) else if "%OS_CLASS%"=="win7" (
        if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python38\python.exe" set "PY_INSTALLED=1"
    ) else (
        rem 现代系统，检查默认 Python 安装路径 (3.12)
        if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" set "PY_INSTALLED=1"
    )
)
if "!PY_INSTALLED!"=="1" (
    echo [OK] 检测到 Python 已安装，跳过下载与安装。
)

:: ----------------- 5. 检测编辑器是否已安装 -----------------
set "EDITOR_INSTALLED=0"
if not "%OS_CLASS%"=="winxp" (
    where code >nul 2>&1
    if %errorlevel% equ 0 set "EDITOR_INSTALLED=1"
    if "!EDITOR_INSTALLED!"=="1" echo [OK] 检测到 VS Code 已安装，跳过下载与安装。
) else (
    rem XP 检查 PyCharm 路径
    if "%ARCH%"=="64" (
        if exist "%USERPROFILE%\AppData\Local\Programs\JetBrains\PyCharm Community Edition 2019.3\bin\pycharm64.exe" set "EDITOR_INSTALLED=1"
    ) else (
        if exist "%USERPROFILE%\AppData\Local\Programs\JetBrains\PyCharm Community Edition 2019.3\bin\pycharm.exe" set "EDITOR_INSTALLED=1"
    )
    if "!EDITOR_INSTALLED!"=="1" echo [OK] 检测到 PyCharm 已安装，跳过下载与安装。
)

:: ----------------- 6. 设置下载链接 -----------------
if "%OS_CLASS%"=="modern" (
    if "!PY_INSTALLED!"=="0" (
        echo [*] 正在获取最新 Python 3.12 版本...
        for /f "usebackq delims=" %%i in (`powershell -Command "& {$r=Invoke-WebRequest 'https://www.python.org/ftp/python/' -UseBasicParsing; [regex]::Matches($r.Content,'3\.12\.\d+/')|%%{$_.Value.TrimEnd('/')}|Sort-Object {[version]$_} -Descending|Select-Object -First 1}"`) do set "py_ver=%%i"
        if "!py_ver!"=="" set "py_ver=3.12.0"
        echo [-] 最新 Python 版本: !py_ver!

        if "%ARCH%"=="ARM64" (
            set "PY_URL=https://www.python.org/ftp/python/!py_ver!/python-!py_ver!-arm64.exe"
        ) else if "%ARCH%"=="64" (
            set "PY_URL=https://www.python.org/ftp/python/!py_ver!/python-!py_ver!-amd64.exe"
        ) else (
            set "PY_URL=https://www.python.org/ftp/python/!py_ver!/python-!py_ver!.exe"
        )
    )
    if "!EDITOR_INSTALLED!"=="0" (
        if "%ARCH%"=="ARM64" (
            set "CODE_URL=https://update.code.visualstudio.com/latest/win32-arm64-user/stable"
        ) else if "%ARCH%"=="64" (
            set "CODE_URL=https://update.code.visualstudio.com/latest/win32-x64-user/stable"
        ) else (
            set "CODE_URL=https://update.code.visualstudio.com/latest/win32-user/stable"
        )
    )
)

if "%OS_CLASS%"=="win7" (
    if "!PY_INSTALLED!"=="0" (
        echo [*] 将为 Windows 7 安装 Python 3.8.10
        if "%ARCH%"=="64" (
            set "PY_URL1=https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe"
            set "PY_URL2=https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe"
        ) else (
            set "PY_URL1=https://www.python.org/ftp/python/3.8.10/python-3.8.10.exe"
            set "PY_URL2=https://www.python.org/ftp/python/3.8.10/python-3.8.10.exe"
        )
    )
    if "!EDITOR_INSTALLED!"=="0" (
        echo [*] 将为 Windows 7 安装 VS Code 1.70.3
        if "%ARCH%"=="64" (
            set "CODE_URL1=https://update.code.visualstudio.com/1.70.2/win32-x64-user/stable"
            set "CODE_URL2=https://update.code.visualstudio.com/1.69.2/win32-x64-user/stable"
        ) else (
            set "CODE_URL1=https://update.code.visualstudio.com/1.70.2/win32-user/stable"
            set "CODE_URL2=https://update.code.visualstudio.com/1.69.2/win32-user/stable"
        )
    )
)

if "%OS_CLASS%"=="winxp" (
    if "!PY_INSTALLED!"=="0" (
        echo [*] 将为 Windows XP 安装 Python 3.4.4
        set "PY_URL1=https://www.python.org/ftp/python/3.4.4/python-3.4.4.msi"
        set "PY_URL2=https://www.python.org/ftp/python/3.4.3/python-3.4.3.msi"
    )
    if "!EDITOR_INSTALLED!"=="0" (
        echo [*] 将为 Windows XP 安装 PyCharm 2019.3.6
        set "PYCHARM_URL1=https://download.jetbrains.com/python/pycharm-community-2019.3.6.exe"
        set "PYCHARM_URL2=https://download.jetbrains.com/python/pycharm-community-2019.3.5.exe"
    )
)

:: ----------------- 7. 下载并安装 Python -----------------
if "!PY_INSTALLED!"=="0" (
    echo.
    echo [1] 开始下载 Python...
    if defined PY_URL1 (
        call :download "%PY_URL1%" "%TMPDIR%\python_installer" || (
            echo [!] 主链接失败，使用备用链接...
            call :download "%PY_URL2%" "%TMPDIR%\python_installer"
        )
    ) else (
        call :download "%PY_URL%" "%TMPDIR%\python_installer"
    )
    if errorlevel 1 (
        echo [X] Python 下载失败，请检查网络。
        goto :cleanup
    )
    echo [OK] Python 下载完成，开始安装...
    if "%OS_CLASS%"=="winxp" (
        msiexec /i "%TMPDIR%\python_installer" /qn ADDLOCAL=ALL TARGETDIR="%USERPROFILE%\AppData\Local\Programs\Python\Python34" /norestart
    ) else (
        "%TMPDIR%\python_installer" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    )
    if errorlevel 1 (
        echo [X] Python 安装失败，请尝试以管理员身份运行。
    ) else (
        echo [OK] Python 安装完成。
    )
)

:: ----------------- 8. 下载并安装编辑器 -----------------
if "!EDITOR_INSTALLED!"=="0" (
    if not "%OS_CLASS%"=="winxp" (
        echo.
        echo [2] 开始下载 Visual Studio Code...
        if defined CODE_URL1 (
            call :download "%CODE_URL1%" "%TMPDIR%\vscode_installer" || (
                echo [!] 主链接失败，使用备用链接...
                call :download "%CODE_URL2%" "%TMPDIR%\vscode_installer"
            )
        ) else (
            call :download "%CODE_URL%" "%TMPDIR%\vscode_installer"
        )
        if errorlevel 1 (
            echo [X] VS Code 下载失败。
            goto :cleanup
        )
        echo [OK] VS Code 下载完成，开始安装...
        "%TMPDIR%\vscode_installer" /verysilent /suppressmsgboxes /mergetasks=!runcode,addcontextmenufiles,addcontextmenufolders,addtopath
        if errorlevel 1 (
            echo [X] VS Code 安装失败。
        ) else (
            echo [OK] VS Code 安装完成。
        )
    )

    if "%OS_CLASS%"=="winxp" (
        echo.
        echo [2] 开始下载 PyCharm 社区版...
        call :download "%PYCHARM_URL1%" "%TMPDIR%\pycharm_installer" || (
            echo [!] 主链接失败，使用备用链接...
            call :download "%PYCHARM_URL2%" "%TMPDIR%\pycharm_installer"
        )
        if errorlevel 1 (
            echo [X] PyCharm 下载失败。
            goto :cleanup
        )
        echo [OK] PyCharm 下载完成，开始安装...
        "%TMPDIR%\pycharm_installer" /S /D=%USERPROFILE%\AppData\Local\Programs\JetBrains\PyCharm Community Edition 2019.3
        if errorlevel 1 (
            echo [X] PyCharm 安装失败。
        ) else (
            echo [OK] PyCharm 安装完成。
        )
    )
)

:: ----------------- 9. 清理临时文件 -----------------
:cleanup
echo.
echo [*] 清理临时文件...
del /f /q "%TMPDIR%\python_installer" >nul 2>&1
if exist "%TMPDIR%\vscode_installer" del /f /q "%TMPDIR%\vscode_installer" >nul 2>&1
if exist "%TMPDIR%\pycharm_installer" del /f /q "%TMPDIR%\pycharm_installer" >nul 2>&1
rd "%TMPDIR%" >nul 2>&1

echo.
echo ================================================
echo    处理完成！若命令行找不到 python 或 code，
echo    请重新打开命令提示符即可。
echo ================================================
pause
exit /b

:: ==================== 下载子程序 ====================
:download
set "url=%~1"
set "dest=%~2"
echo    - 来源: %url%
bitsadmin /transfer "Job_%RANDOM%" /download /priority normal "%url%" "%dest%"
exit /b