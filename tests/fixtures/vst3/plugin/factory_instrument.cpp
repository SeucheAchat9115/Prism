#include "mdaPianoController.h"
#include "mdaPianoProcessor.h"
#include "public.sdk/source/main/pluginfactory_constexpr.h"

#define stringCompanyName "Prism"
#define stringCompanyWeb "https://github.com/SeucheAchat9115/Prism"
#define stringCompanyEmail "prism@example.invalid"

BEGIN_FACTORY_DEF(stringCompanyName, stringCompanyWeb, stringCompanyEmail, 1)

DEF_CLASS(
    Steinberg::Vst::mda::PianoProcessor::uid,
    Steinberg::PClassInfo::kManyInstances,
    kVstAudioEffectClass,
    "Prism Fixture Piano",
    Steinberg::Vst::kDistributable,
    "Instrument|Synth",
    "1.0.0",
    kVstVersionString,
    Steinberg::Vst::mda::PianoProcessor::createInstance,
    nullptr)

DEF_CLASS(
    Steinberg::Vst::mda::PianoController::uid,
    Steinberg::PClassInfo::kManyInstances,
    kVstComponentControllerClass,
    "Prism Fixture Piano Controller",
    0,
    "",
    "1.0.0",
    kVstVersionString,
    Steinberg::Vst::mda::PianoController::createInstance,
    nullptr)

END_FACTORY
