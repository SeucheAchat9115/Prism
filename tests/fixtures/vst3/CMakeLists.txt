cmake_minimum_required(VERSION 3.25.0)

project(prism-vst3-fixtures VERSION 0.1.0 LANGUAGES CXX)

if(NOT DEFINED PRISM_VST3_SDK_ROOT)
    message(FATAL_ERROR "PRISM_VST3_SDK_ROOT must point to the pinned VST3 SDK checkout")
endif()

set(SMTG_ENABLE_VST3_PLUGIN_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_HOSTING_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VSTGUI_SUPPORT OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_WAYLAND_SUPPORT OFF CACHE BOOL "" FORCE)
set(SMTG_CREATE_PLUGIN_LINK OFF CACHE BOOL "" FORCE)

add_subdirectory("${PRISM_VST3_SDK_ROOT}" "vst3sdk")
# The fixture is outside the SDK tree, so restore the source-root variable
# that the SDK's package helper uses when adding its platform entry point.
set(public_sdk_SOURCE_DIR "${PRISM_VST3_SDK_ROOT}/public.sdk")
add_subdirectory(plugin)
