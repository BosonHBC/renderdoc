# Install script for directory: C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/DirectXShaderCompiler/tools

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "C:/Program Files (x86)/LLVM")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "Release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/llvm-config/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/opt/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/llvm-as/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/llvm-dis/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/dxexp/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/llvm-link/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/llvm-extract/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/llvm-diff/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/llvm-bcanalyzer/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/llvm-stress/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/verify-uselistorder/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/cmake_install.cmake")
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
