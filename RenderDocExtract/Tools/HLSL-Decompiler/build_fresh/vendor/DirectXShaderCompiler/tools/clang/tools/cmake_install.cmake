# Install script for directory: C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/DirectXShaderCompiler/tools/clang/tools

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
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/driver/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/libclang/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxcompiler/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxclib/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxcvalidator/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxildll/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxa/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxopt/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxl/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxr/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxv/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/d3dcomp/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxrfallbackcompiler/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dxlib-sample/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/dotnetc/cmake_install.cmake")
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/clang/tools/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
