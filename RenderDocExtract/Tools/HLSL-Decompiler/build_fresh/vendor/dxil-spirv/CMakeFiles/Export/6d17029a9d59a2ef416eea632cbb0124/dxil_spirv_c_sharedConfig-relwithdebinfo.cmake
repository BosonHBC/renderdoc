#----------------------------------------------------------------
# Generated CMake target import file for configuration "RelWithDebInfo".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "dxil-spirv-c-shared" for configuration "RelWithDebInfo"
set_property(TARGET dxil-spirv-c-shared APPEND PROPERTY IMPORTED_CONFIGURATIONS RELWITHDEBINFO)
set_target_properties(dxil-spirv-c-shared PROPERTIES
  IMPORTED_IMPLIB_RELWITHDEBINFO "${_IMPORT_PREFIX}/lib/dxil-spirv-c-shared.lib"
  IMPORTED_LOCATION_RELWITHDEBINFO "${_IMPORT_PREFIX}/bin/dxil-spirv-c-shared.dll"
  )

list(APPEND _cmake_import_check_targets dxil-spirv-c-shared )
list(APPEND _cmake_import_check_files_for_dxil-spirv-c-shared "${_IMPORT_PREFIX}/lib/dxil-spirv-c-shared.lib" "${_IMPORT_PREFIX}/bin/dxil-spirv-c-shared.dll" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
