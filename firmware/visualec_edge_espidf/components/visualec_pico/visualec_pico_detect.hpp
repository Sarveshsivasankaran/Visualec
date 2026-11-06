#pragma once

#include "dl_detect_base.hpp"
#include "dl_detect_espdet_postprocessor.hpp"

namespace visualec_pico {
class Model : public dl::detect::DetectImpl {
public:
    Model(float score_threshold, float nms_threshold);
};
} // namespace visualec_pico

class VisualecPicoDetect : public dl::detect::DetectWrapper {
public:
    explicit VisualecPicoDetect(bool lazy_load = true);

private:
    void load_model() override;
};
