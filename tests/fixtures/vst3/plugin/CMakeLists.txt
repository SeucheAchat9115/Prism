cmake_minimum_required(VERSION 3.25.0)

set(ADelay_SOURCE_DIR "${PRISM_VST3_SDK_ROOT}/public.sdk/samples/vst/adelay/source")
set(MDA_SOURCE_DIR "${PRISM_VST3_SDK_ROOT}/public.sdk/samples/vst/mda-vst3/source")

smtg_add_vst3plugin(prism-fixture-delay
    factory_delay.cpp
    "${ADelay_SOURCE_DIR}/adelaycontroller.cpp"
    "${ADelay_SOURCE_DIR}/adelaycontroller.h"
    "${ADelay_SOURCE_DIR}/adelayids.h"
    "${ADelay_SOURCE_DIR}/adelayprocessor.cpp"
    "${ADelay_SOURCE_DIR}/adelayprocessor.h"
)
target_include_directories(prism-fixture-delay PRIVATE
    "${PRISM_VST3_SDK_ROOT}"
    "${ADelay_SOURCE_DIR}"
)

target_compile_features(prism-fixture-delay PRIVATE cxx_std_17)
target_link_libraries(prism-fixture-delay PRIVATE sdk)

smtg_add_vst3plugin(prism-fixture-instrument
    factory_instrument.cpp
    "${MDA_SOURCE_DIR}/helpers.h"
    "${MDA_SOURCE_DIR}/mdaBaseController.cpp"
    "${MDA_SOURCE_DIR}/mdaBaseController.h"
    "${MDA_SOURCE_DIR}/mdaBaseProcessor.cpp"
    "${MDA_SOURCE_DIR}/mdaBaseProcessor.h"
    "${MDA_SOURCE_DIR}/mdaParameter.cpp"
    "${MDA_SOURCE_DIR}/mdaParameter.h"
    "${MDA_SOURCE_DIR}/mdaPianoController.cpp"
    "${MDA_SOURCE_DIR}/mdaPianoController.h"
    "${MDA_SOURCE_DIR}/mdaPianoData.h"
    "${MDA_SOURCE_DIR}/mdaPianoProcessor.cpp"
    "${MDA_SOURCE_DIR}/mdaPianoProcessor.h"
)
target_include_directories(prism-fixture-instrument PRIVATE
    "${PRISM_VST3_SDK_ROOT}"
    "${MDA_SOURCE_DIR}"
)

target_compile_features(prism-fixture-instrument PRIVATE cxx_std_17)
target_link_libraries(prism-fixture-instrument PRIVATE sdk)

foreach(variant latency mono)
    smtg_add_vst3plugin(prism-fixture-${variant} latency.cpp)
    target_include_directories(prism-fixture-${variant} PRIVATE "${PRISM_VST3_SDK_ROOT}")
    target_compile_features(prism-fixture-${variant} PRIVATE cxx_std_17)
    target_link_libraries(prism-fixture-${variant} PRIVATE sdk)
endforeach()
target_compile_definitions(prism-fixture-mono PRIVATE PRISM_MONO=1)
