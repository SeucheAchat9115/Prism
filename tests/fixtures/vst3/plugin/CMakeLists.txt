cmake_minimum_required(VERSION 3.25.0)

set(ADelay_SOURCE_DIR "${SDK_ROOT}/samples/vst/adelay/source")
set(MDA_SOURCE_DIR "${SDK_ROOT}/samples/vst/mda-vst3/source")

smtg_add_vst3plugin(prism-fixture-delay
    factory_delay.cpp
    "${ADelay_SOURCE_DIR}/adelaycontroller.cpp"
    "${ADelay_SOURCE_DIR}/adelaycontroller.h"
    "${ADelay_SOURCE_DIR}/adelayids.h"
    "${ADelay_SOURCE_DIR}/adelayprocessor.cpp"
    "${ADelay_SOURCE_DIR}/adelayprocessor.h"
)
target_include_directories(prism-fixture-delay PRIVATE "${ADelay_SOURCE_DIR}")
smtg_target_setup_as_vst3_example(prism-fixture-delay)

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
target_include_directories(prism-fixture-instrument PRIVATE "${MDA_SOURCE_DIR}")
smtg_target_setup_as_vst3_example(prism-fixture-instrument)
