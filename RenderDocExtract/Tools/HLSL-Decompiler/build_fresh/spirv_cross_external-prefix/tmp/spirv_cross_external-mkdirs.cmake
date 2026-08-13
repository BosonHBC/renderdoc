# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file LICENSE.rst or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION ${CMAKE_VERSION}) # this file comes with cmake

# If CMAKE_DISABLE_SOURCE_CHANGES is set to true and the source directory is an
# existing directory in our source tree, calling file(MAKE_DIRECTORY) on it
# would cause a fatal error, even though it would be a no-op.
if(NOT EXISTS "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/SPIRV-Cross")
  file(MAKE_DIRECTORY "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/vendor/SPIRV-Cross")
endif()
file(MAKE_DIRECTORY
  "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/vendor/SPIRV-Cross"
  "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/spirv_cross_external-prefix"
  "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/spirv_cross_external-prefix/tmp"
  "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/spirv_cross_external-prefix/src/spirv_cross_external-stamp"
  "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/spirv_cross_external-prefix/src"
  "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/spirv_cross_external-prefix/src/spirv_cross_external-stamp"
)

set(configSubDirs Debug;Release;MinSizeRel;RelWithDebInfo)
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/spirv_cross_external-prefix/src/spirv_cross_external-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "C:/LQTech/UGit/renderdoc/RenderDocExtract/Tools/HLSL-Decompiler/build_fresh/spirv_cross_external-prefix/src/spirv_cross_external-stamp${cfgdir}") # cfgdir has leading slash
endif()
