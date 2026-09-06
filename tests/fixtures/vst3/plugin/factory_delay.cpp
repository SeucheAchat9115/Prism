#include "adelaycontroller.h"
#include "adelayids.h"
#include "adelayprocessor.h"
#include "public.sdk/source/main/pluginfactory_constexpr.h"

#define stringCompanyName "Prism"
#define stringCompanyWeb "https://github.com/SeucheAchat9115/Prism"
#define stringCompanyEmail "prism@example.invalid"

BEGIN_FACTORY_DEF(stringCompanyName, stringCompanyWeb, stringCompanyEmail, 1)

DEF_CLASS(
    Steinberg::Vst::ADelayProcessorUID,
    Steinberg::PClassInfo::kManyInstances,
    kVstAudioEffectClass,
    "Prism Fixture Delay",
    Steinberg::Vst::kDistributable,
    "Fx|Delay",
    "1.0.0",
    kVstVersionString,
    Steinberg::Vst::ADelayProcessor::createInstance,
    nullptr)

DEF_CLASS(
    Steinberg::Vst::ADelayControllerUID,
    Steinberg::PClassInfo::kManyInstances,
    kVstComponentControllerClass,
    "Prism Fixture Delay Controller",
    0,
    "",
    "1.0.0",
    kVstVersionString,
    Steinberg::Vst::ADelayController::createInstance,
    nullptr)

END_FACTORY
