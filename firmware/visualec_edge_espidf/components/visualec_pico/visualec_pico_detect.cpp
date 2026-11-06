#include "visualec_pico_detect.hpp"

#include "dl_image_preprocessor.hpp"
#include "dl_model_base.hpp"

namespace visualec_pico {
Model::Model(float score_threshold, float nms_threshold)
{
    m_model = new dl::Model("pedestrian_det", "visualec_pico.espdl", fbs::MODEL_LOCATION_IN_FLASH_PARTITION);
    m_model->minimize();
    // ESP-DL 3.3 accepts the img_t pixel type directly during preprocess.
    // Earlier ESP-DL releases exposed a RGB565 capability argument here;
    // that overload is no longer present in the managed 3.3 component.
    m_image_preprocessor = new dl::image::ImagePreprocessor(
        m_model,
        {0, 0, 0},
        {255, 255, 255});
    m_image_preprocessor->enable_letterbox({114, 114, 114});
    m_postprocessor = new dl::detect::ESPDetPostProcessor(
        m_model,
        m_image_preprocessor,
        score_threshold,
        nms_threshold,
        10,
        {{8, 8, 4, 4}, {16, 16, 8, 8}, {32, 32, 16, 16}});
}
} // namespace visualec_pico

VisualecPicoDetect::VisualecPicoDetect(bool lazy_load)
{
    m_score_thr[0] = 0.25f;
    m_nms_thr[0] = 0.7f;
    if (lazy_load) m_model = nullptr;
    else load_model();
}

void VisualecPicoDetect::load_model()
{
    m_model = new visualec_pico::Model(m_score_thr[0], m_nms_thr[0]);
}
