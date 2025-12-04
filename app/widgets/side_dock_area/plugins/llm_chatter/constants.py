

PARAM_UI_MAP = {
        "API_KEY": "password",
        "温度": "slider",
        "是否思考": "checkbox",
        "temp": "slider",
        "最大Token": "slider",
        "max_new_tokens": "spinbox",
        "top_p": "slider",
        "frequency_penalty": "slider",
        "presence_penalty": "slider",
    }


PARAM_RANGE_MAP = {
    "温度": {"min": 0.0, "max": 2.0, "step": 0.01, "type": "float"},
    "temp": {"min": 0.0, "max": 2.0, "step": 0.01, "type": "float"},
    "最大Token": {"min": 1, "max": 32768, "step": 1, "type": "int"},
    "最大新Token": {"min": 1, "max": 8192, "step": 1, "type": "int"},
    "top_p": {"min": 0.0, "max": 1.0, "step": 0.01, "type": "float"},
    "frequency_penalty": {"min": -2.0, "max": 2.0, "step": 0.01, "type": "float"},
    "presence_penalty": {"min": -2.0, "max": 2.0, "step": 0.01, "type": "float"},
}


