import importlib

from curb_utils.io_tools import load_from_yaml
from pydantic import BaseModel

from smart_prototype.config import Config


def load_step_configs(config: Config) -> dict[str, type[BaseModel]]:
    configs = {}
    # loop over each item in Config.steps
    for step_name, step_config in config.steps:
        if step_config.run:
            # get the config class for this module
            config_class = _get_module_config_class(step_name)

            # load the config file for this step
            step_specific_config = config_class(**load_from_yaml(step_config.path))

            configs[step_name] = step_specific_config

    return configs


def _get_module_config_class(module_name: str) -> type[BaseModel]:
    """Get a module config class based on a module name.
    do this by converting from snake case to camel case and appending "Config".

    """
    # split the module name by underscores, capitalize each word, and join them together
    words = module_name.split("_")
    capitalized_words = [word.capitalize() for word in words]
    capitalized_words.append("Config")
    config_class_name = "".join(capitalized_words)

    # Import and return the config class for this module
    module = importlib.import_module(f"{module_name}.config")
    config_class = getattr(module, config_class_name)
    return config_class
