// Prism qualification fixture, GPL-3.0-only. Built against the pinned VST3 SDK.
#include "public.sdk/source/vst/vstaudioeffect.h"
#include "public.sdk/source/vst/vsteditcontroller.h"
#include "public.sdk/source/main/pluginfactory_constexpr.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"
#include "base/source/fstreamer.h"
#include <array>
#include <algorithm>

using namespace Steinberg;
using namespace Steinberg::Vst;

#ifndef PRISM_MONO
#define PRISM_MONO 0
#endif
namespace {
constexpr TUID processorUID = INLINE_UID(0x42ABCC11, 0x22134455, 0x66778899, 0x10111213 + PRISM_MONO);
constexpr TUID controllerUID = INLINE_UID(0x42ABCC12, 0x22134455, 0x66778899, 0x10111213 + PRISM_MONO);
constexpr int latency = 64;
constexpr ParamID gainID = 0;

class Controller : public EditController {
public:
    static FUnknown* create(void*) { return static_cast<IEditController*>(new Controller); }
    tresult PLUGIN_API initialize(FUnknown* context) override {
        auto result = EditController::initialize(context);
        if (result != kResultOk) return result;
        parameters.addParameter(STR16("Gain"), nullptr, 0, 0.5,
                                ParameterInfo::kCanAutomate, gainID);
        return kResultOk;
    }
    tresult PLUGIN_API setComponentState(IBStream* state) override {
        IBStreamer stream(state, kLittleEndian);
        double value;
        if (!stream.readDouble(value)) return kResultFalse;
        return setParamNormalized(gainID, value);
    }
};

class Processor : public AudioEffect {
    std::array<std::array<float, latency>, 2> buffer {};
    int cursor = 0;
    double gain = 0.5;
public:
    Processor() { setControllerClass(FUID::fromTUID(controllerUID)); }
    static FUnknown* create(void*) { return static_cast<IAudioProcessor*>(new Processor); }
    tresult PLUGIN_API initialize(FUnknown* context) override {
        auto result = AudioEffect::initialize(context);
        if (result != kResultOk) return result;
        addAudioInput(STR16("Input"), SpeakerArr::kStereo);
        addAudioOutput(STR16("Output"), PRISM_MONO ? SpeakerArr::kMono : SpeakerArr::kStereo);
        return kResultOk;
    }
    uint32 PLUGIN_API getLatencySamples() override { return latency; }
    tresult PLUGIN_API setProcessing(TBool state) override {
        if (state) { buffer = {}; cursor = 0; }
        return kResultOk;
    }
    tresult PLUGIN_API setBusArrangements(SpeakerArrangement* ins, int32 ni,
                                         SpeakerArrangement* outs, int32 no) override {
        if (ni != 1 || no != 1 || ins[0] != SpeakerArr::kStereo ||
            outs[0] != (PRISM_MONO ? SpeakerArr::kMono : SpeakerArr::kStereo))
            return kResultFalse;
        return AudioEffect::setBusArrangements(ins, ni, outs, no);
    }
    tresult PLUGIN_API getState(IBStream* state) override {
        IBStreamer stream(state, kLittleEndian);
        return stream.writeDouble(gain) ? kResultOk : kResultFalse;
    }
    tresult PLUGIN_API setState(IBStream* state) override {
        IBStreamer stream(state, kLittleEndian);
        return stream.readDouble(gain) ? kResultOk : kResultFalse;
    }
    tresult PLUGIN_API process(ProcessData& data) override {
        IParamValueQueue* queue = nullptr;
        if (data.inputParameterChanges) {
            for (int32 i = 0; i < data.inputParameterChanges->getParameterCount(); ++i) {
                auto* candidate = data.inputParameterChanges->getParameterData(i);
                if (candidate && candidate->getParameterId() == gainID) queue = candidate;
            }
        }
        int32 point = 0;
        auto update = [&](int32 sample) {
            while (queue && point < queue->getPointCount()) {
                int32 offset; ParamValue value;
                if (queue->getPoint(point, offset, value) != kResultOk || offset > sample) break;
                gain = value;
                ++point;
            }
        };
        if (data.numSamples == 0) { update(0); return kResultOk; }
        if (data.numInputs != 1 || data.numOutputs != 1 || data.symbolicSampleSize != kSample32)
            return kResultFalse;
        data.outputs[0].silenceFlags = 0;
        for (int32 i = 0; i < data.numSamples; ++i) {
            update(i);
            // Read both inputs before writing: hosts may use in-place buffers.
            float left = data.inputs[0].channelBuffers32[0][i];
            float right = data.inputs[0].channelBuffers32[1][i];
            for (int channel = 0; channel < (PRISM_MONO ? 1 : 2); ++channel) {
                float input = PRISM_MONO ? (left + right) * 0.5f : (channel ? right : left);
                data.outputs[0].channelBuffers32[channel][i] = buffer[channel][cursor];
                buffer[channel][cursor] = static_cast<float>(input * gain);
            }
            cursor = (cursor + 1) % latency;
        }
        return kResultOk;
    }
};
}

BEGIN_FACTORY_DEF("Prism", "https://github.com/SeucheAchat9115/Prism", "prism@example.invalid", 2)
DEF_CLASS(processorUID, PClassInfo::kManyInstances, kVstAudioEffectClass,
          "Prism Gain Latency", kDistributable, "Fx", "1.0.0", kVstVersionString,
          Processor::create, nullptr)
DEF_CLASS(controllerUID, PClassInfo::kManyInstances, kVstComponentControllerClass,
          "Prism Gain Controller", 0, "", "1.0.0", kVstVersionString,
          Controller::create, nullptr)
END_FACTORY
