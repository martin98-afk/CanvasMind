from loguru import logger

def get_logger(module_name: str):
    return logger.bind(module=module_name)