# CMake generated Testfile for 
# Source directory: C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools
# Build directory: C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/dxil-spirv/third_party/SPIRV-Tools
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
if(CTEST_CONFIGURATION_TYPE MATCHES "^([Dd][Ee][Bb][Uu][Gg])$")
  add_test([=[spirv-tools-copyrights]=] "C:/Users/bosonhuang/AppData/Local/Python/pythoncore-3.14-64/python.exe" "utils/check_copyright.py")
  set_tests_properties([=[spirv-tools-copyrights]=] PROPERTIES  WORKING_DIRECTORY "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools" _BACKTRACE_TRIPLES "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools/CMakeLists.txt;369;add_test;C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ee][Aa][Ss][Ee])$")
  add_test([=[spirv-tools-copyrights]=] "C:/Users/bosonhuang/AppData/Local/Python/pythoncore-3.14-64/python.exe" "utils/check_copyright.py")
  set_tests_properties([=[spirv-tools-copyrights]=] PROPERTIES  WORKING_DIRECTORY "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools" _BACKTRACE_TRIPLES "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools/CMakeLists.txt;369;add_test;C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Mm][Ii][Nn][Ss][Ii][Zz][Ee][Rr][Ee][Ll])$")
  add_test([=[spirv-tools-copyrights]=] "C:/Users/bosonhuang/AppData/Local/Python/pythoncore-3.14-64/python.exe" "utils/check_copyright.py")
  set_tests_properties([=[spirv-tools-copyrights]=] PROPERTIES  WORKING_DIRECTORY "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools" _BACKTRACE_TRIPLES "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools/CMakeLists.txt;369;add_test;C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ww][Ii][Tt][Hh][Dd][Ee][Bb][Ii][Nn][Ff][Oo])$")
  add_test([=[spirv-tools-copyrights]=] "C:/Users/bosonhuang/AppData/Local/Python/pythoncore-3.14-64/python.exe" "utils/check_copyright.py")
  set_tests_properties([=[spirv-tools-copyrights]=] PROPERTIES  WORKING_DIRECTORY "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools" _BACKTRACE_TRIPLES "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools/CMakeLists.txt;369;add_test;C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/dxil-spirv/third_party/SPIRV-Tools/CMakeLists.txt;0;")
else()
  add_test([=[spirv-tools-copyrights]=] NOT_AVAILABLE)
endif()
subdirs("external")
subdirs("source")
subdirs("tools")
subdirs("test")
subdirs("examples")
