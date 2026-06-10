@echo off
chcp 65001 >nul 2>&1

echo ============================================================
echo  Building RenderDoc Release x64
echo  (with placed texture optimization patch)
echo ============================================================
echo.

call "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat" x64
if errorlevel 1 (
    echo ERROR: Could not find VS2022 build tools
    pause
    exit /b 1
)

echo.
echo [1/7] Building breakpad_common...
msbuild D:\UGit\renderdoc\renderdoc\3rdparty\breakpad\client\windows\common.vcxproj /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=D:\UGit\renderdoc\\" /v:m
if errorlevel 1 goto :failed

echo [2/7] Building crash_generation_client...
msbuild D:\UGit\renderdoc\renderdoc\3rdparty\breakpad\client\windows\crash_generation\crash_generation_client.vcxproj /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=D:\UGit\renderdoc\\" /v:m
if errorlevel 1 goto :failed

echo [3/7] Building crash_generation_server...
msbuild D:\UGit\renderdoc\renderdoc\3rdparty\breakpad\client\windows\crash_generation\crash_generation_server.vcxproj /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=D:\UGit\renderdoc\\" /v:m
if errorlevel 1 goto :failed

echo [4/7] Building exception_handler...
msbuild D:\UGit\renderdoc\renderdoc\3rdparty\breakpad\client\windows\handler\exception_handler.vcxproj /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=D:\UGit\renderdoc\\" /v:m
if errorlevel 1 goto :failed

echo [5/7] Building renderdoc.dll...
msbuild D:\UGit\renderdoc\renderdoc\renderdoc.vcxproj /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=D:\UGit\renderdoc\\" /v:m
if errorlevel 1 goto :failed

echo [6/7] Building renderdoccmd.exe...
msbuild D:\UGit\renderdoc\renderdoccmd\renderdoccmd.vcxproj /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=D:\UGit\renderdoc\\" /v:m
if errorlevel 1 goto :failed

echo [7/7] Building qrenderdoc.exe (GUI)...
msbuild D:\UGit\renderdoc\qrenderdoc\qrenderdoc_local.vcxproj /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:SolutionDir=D:\UGit\renderdoc\\" /v:m
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo  BUILD SUCCESS!
echo ============================================================
echo.
echo  Output directory: D:\UGit\renderdoc\x64\Release\
echo.
echo    renderdoc.dll    - Core capture library
echo    renderdoccmd.exe - Command-line capture tool
echo    qrenderdoc.exe   - GUI (same as RenderDoc UI)
echo.
echo  To launch GUI:
echo    D:\UGit\renderdoc\x64\Release\qrenderdoc.exe
echo.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED
pause
exit /b 1
