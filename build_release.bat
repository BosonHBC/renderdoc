@echo off
chcp 65001 >nul 2>&1

REM ============================================================
REM  Auto-detect project root from script location
REM  No more hardcoded paths - works from any drive/directory
REM ============================================================
set "RDOC_ROOT=%~dp0"
REM Remove trailing backslash
if "%RDOC_ROOT:~-1%"=="\" set "RDOC_ROOT=%RDOC_ROOT:~0,-1%"

echo ============================================================
echo  Building RenderDoc Release x64
echo  (with placed texture optimization patch)
echo  Project root: %RDOC_ROOT%
echo ============================================================
echo.

REM ============================================================
REM  Detect Visual Studio installation
REM ============================================================
set "VCVARSALL="
if exist "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARSALL=C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat"
) else if exist "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARSALL=C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat"
) else if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARSALL=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"
) else if exist "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARSALL=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
)

if "%VCVARSALL%"=="" (
    echo ERROR: Could not find VS2022 build tools
    echo Checked: Professional, Enterprise, Community, BuildTools
    pause
    exit /b 1
)

echo Using VS: %VCVARSALL%
call "%VCVARSALL%" x64
if errorlevel 1 (
    echo ERROR: vcvarsall.bat failed
    pause
    exit /b 1
)

echo.
echo [1/7] Building breakpad_common...
msbuild "%RDOC_ROOT%\renderdoc\3rdparty\breakpad\client\windows\common.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=%RDOC_ROOT%\\" /v:m
if errorlevel 1 goto :failed

echo [2/7] Building crash_generation_client...
msbuild "%RDOC_ROOT%\renderdoc\3rdparty\breakpad\client\windows\crash_generation\crash_generation_client.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=%RDOC_ROOT%\\" /v:m
if errorlevel 1 goto :failed

echo [3/7] Building crash_generation_server...
msbuild "%RDOC_ROOT%\renderdoc\3rdparty\breakpad\client\windows\crash_generation\crash_generation_server.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=%RDOC_ROOT%\\" /v:m
if errorlevel 1 goto :failed

echo [4/7] Building exception_handler...
msbuild "%RDOC_ROOT%\renderdoc\3rdparty\breakpad\client\windows\handler\exception_handler.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=%RDOC_ROOT%\\" /v:m
if errorlevel 1 goto :failed

echo [5/7] Building renderdoc.dll...
msbuild "%RDOC_ROOT%\renderdoc\renderdoc.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=%RDOC_ROOT%\\" /v:m
if errorlevel 1 goto :failed

echo [6/7] Building renderdoccmd.exe...
msbuild "%RDOC_ROOT%\renderdoccmd\renderdoccmd.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=%RDOC_ROOT%\\" /v:m
if errorlevel 1 goto :failed

echo [7/7] Building qrenderdoc.exe (GUI)...
msbuild "%RDOC_ROOT%\qrenderdoc\qrenderdoc_local.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=%RDOC_ROOT%\\" /v:m
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo  BUILD SUCCESS!
echo ============================================================
echo.
echo  Output directory: %RDOC_ROOT%\x64\Release\
echo.
echo    renderdoc.dll    - Core capture library
echo    renderdoccmd.exe - Command-line capture tool
echo    qrenderdoc.exe   - GUI (same as RenderDoc UI)
echo.
echo  To launch GUI:
echo    %RDOC_ROOT%\x64\Release\qrenderdoc.exe
echo.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED
pause
exit /b 1
