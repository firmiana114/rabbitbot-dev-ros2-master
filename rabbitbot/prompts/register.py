from dataclasses import is_dataclass

_prompt_provider_dict = {}


def register_prompt_provider(pp):
    assert (
        isinstance(pp, type)
        and is_dataclass(pp)
        and hasattr(pp, 'name')
    ), f"Illformed prompt provider, can't register!, got: {pp}"
    _prompt_provider_dict[pp.name] = pp


def get_prompt_provider(name: str):
    return _prompt_provider_dict[name]
