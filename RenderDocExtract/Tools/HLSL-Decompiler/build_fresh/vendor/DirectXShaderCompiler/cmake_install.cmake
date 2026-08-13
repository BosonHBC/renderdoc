# Install script for directory: C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/DirectXShaderCompiler

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
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/lib/Support/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/lib/MSSupport/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/lib/TableGen/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/utils/TableGen/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/include/llvm/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/include/dxc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/utils/hct/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/external/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/lib/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/utils/version/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/projects/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/tools/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/cmake/modules/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "llvm-headers" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE DIRECTORY FILES
    "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/DirectXShaderCompiler/include/llvm"
    "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/DirectXShaderCompiler/include/llvm-c"
    FILES_MATCHING REGEX "/[^/]*\\.def$" REGEX "/[^/]*\\.h$" REGEX "/[^/]*\\.td$" REGEX "/[^/]*\\.inc$" REGEX "/license\\.txt$" REGEX "/\\.svn$" EXCLUDE)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "llvm-headers" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE DIRECTORY FILES "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/include/llvm" FILES_MATCHING REGEX "/[^/]*\\.def$" REGEX "/[^/]*\\.h$" REGEX "/[^/]*\\.gen$" REGEX "/[^/]*\\.inc$" REGEX "/cmakefiles$" EXCLUDE REGEX "/config\\.h$" EXCLUDE REGEX "/\\.svn$" EXCLUDE)
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
if(CMAKE_INSTALL_COMPONENT)
  if(CMAKE_INSTALL_COMPONENT MATCHES "^[a-zA-Z0-9_.+-]+$")
    set(CMAKE_INSTALL_MANIFEST "install_manifest_${CMAKE_INSTALL_COMPONENT}.txt")
  else()
    string(MD5 CMAKE_INST_COMP_HASH "${CMAKE_INSTALL_COMPONENT}")
    set(CMAKE_INSTALL_MANIFEST "install_manifest_${CMAKE_INST_COMP_HASH}.txt")
    unset(CMAKE_INST_COMP_HASH)
  endif()
else()
  set(CMAKE_INSTALL_MANIFEST "install_manifest.txt")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/DirectXShaderCompiler/${CMAKE_INSTALL_MANIFEST}"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
