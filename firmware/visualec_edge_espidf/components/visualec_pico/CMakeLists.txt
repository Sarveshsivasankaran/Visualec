idf_build_get_property(component_targets __COMPONENT_TARGETS)
if ("___idf_espressif__esp-dl" IN_LIST component_targets)
    idf_component_get_property(espdl_dir espressif__esp-dl COMPONENT_DIR)
elseif ("___idf_esp-dl" IN_LIST component_targets)
    idf_component_get_property(espdl_dir esp-dl COMPONENT_DIR)
endif()

idf_component_register(SRCS "visualec_pico_detect.cpp" INCLUDE_DIRS "." REQUIRES esp-dl)

if(CONFIG_VISUALEC_USE_CUSTOM_MODEL)
    if(NOT DEFINED ENV{VISUALEC_MODEL_ARTIFACT})
        message(FATAL_ERROR "VISUALEC_MODEL_ARTIFACT must point to the verified visualec_pico.espdl release")
    endif()
    set(model_file $ENV{VISUALEC_MODEL_ARTIFACT})
    if(NOT EXISTS ${model_file})
        message(FATAL_ERROR "Verified model artifact does not exist: ${model_file}")
    endif()
    set(packed_model ${BUILD_DIR}/espdl_models/visualec_pico.espdl)
    file(MAKE_DIRECTORY ${BUILD_DIR}/espdl_models)
    include(${espdl_dir}/fbs_loader/cmake/utilities.cmake)
    add_custom_command(
        OUTPUT ${packed_model}
        COMMENT "Pack verified Visualec-Pico model"
        COMMAND python ${espdl_dir}/fbs_loader/pack_espdl_models.py --model_path ${model_file} --out_file ${packed_model}
        DEPENDS ${model_file}
        VERBATIM
    )
    add_custom_target(VISUALEC_PICO_MODEL ALL DEPENDS ${packed_model})
    add_dependencies(flash VISUALEC_PICO_MODEL)
    esptool_py_flash_to_partition(flash "pedestrian_det" ${packed_model})
endif()
