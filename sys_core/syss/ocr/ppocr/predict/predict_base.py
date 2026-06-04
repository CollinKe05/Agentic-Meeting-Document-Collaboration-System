# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：predict_base
# @Date   ：2024/7/31 17:48
# @Author ：leemysw

# 2024/7/31 17:48   Create
# =====================================================

import onnxruntime


class PredictBase(object):
    def __init__(self):
        pass

    @staticmethod
    def get_onnx_session(model_dir, use_gpu):
        # 使用gpu
        cpu_provider_options = {"arena_extend_strategy": "kSameAsRequested", }
        if use_gpu:
            cuda_provider_options = {
                "cudnn_conv_algo_search": "EXHAUSTIVE",  # 使用穷举搜索找到最佳卷积算法
                "arena_extend_strategy": "kSameAsRequested",
                "do_copy_in_default_stream": True,
                "gpu_mem_limit": 2 * 1024 * 1024 * 1024,
            }
            providers = [
                ('CUDAExecutionProvider', cuda_provider_options), ('CPUExecutionProvider', cpu_provider_options)
            ]
        else:
            providers = [('CPUExecutionProvider', cpu_provider_options)]

        # 添加会话选项以优化性能
        session_options = onnxruntime.SessionOptions()
        session_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        # session_options.intra_op_num_threads = 1  # 对于GPU执行这个设置不太重要
        # session_options.log_severity_level = 3  # 只显示警告和错误

        onnx_session = onnxruntime.InferenceSession(model_dir, session_options, providers=providers)
        return onnx_session

    @staticmethod
    def get_output_name(onnx_session):
        """
        output_name = onnx_session.get_outputs()[0].name
        :param onnx_session:
        :return:
        """
        output_name = []
        for node in onnx_session.get_outputs():
            output_name.append(node.name)
        return output_name

    @staticmethod
    def get_input_name(onnx_session):
        """
        input_name = onnx_session.get_inputs()[0].name
        :param onnx_session:
        :return:
        """
        input_name = []
        for node in onnx_session.get_inputs():
            input_name.append(node.name)
        return input_name

    @staticmethod
    def get_input_feed(input_name, image_numpy):
        """
        input_feed={self.input_name: image_numpy}
        :param input_name:
        :param image_numpy:
        :return:
        """
        input_feed = {}
        for name in input_name:
            input_feed[name] = image_numpy
        return input_feed
