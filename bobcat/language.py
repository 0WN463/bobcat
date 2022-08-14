import configparser
from dataclasses import dataclass
from ast import literal_eval
from pathlib import Path


@dataclass
class Language:
    name: str  # Sent to Kattis to identify language
    ext: str
    build_cmd: str
    run_cmd: str

class ExtensionNotSupported(Exception):
    pass

@dataclass
class Languages:
    languages: list[Language]

    def get_lang(self, file: str) -> Language:
        ext = Path(file).suffix
        lang = next((lang for lang in self.languages if lang.ext == ext), None)

        if not lang:
            raise ExtensionNotSupported(f"'{ext}' is not supported.")
        return lang


def make_languages(config: configparser.ConfigParser) -> Languages:
    LANGUAGE_CONF = config["languages"]
    LANGUAGE_CONF = {k: literal_eval(v) for k, v in LANGUAGE_CONF.items()}

    languages = [
        Language(
            "Python 3",
            ".py",
            LANGUAGE_CONF['python']['build'],
            LANGUAGE_CONF['python']['exec'],
        ),
        Language(
            "Haskell",
            ".hs",
            LANGUAGE_CONF['haskell']['build'],
            LANGUAGE_CONF['haskell']['exec'],
        ),
        Language(
            "C++",
            ".cpp",
            LANGUAGE_CONF['c++']['build'],
            LANGUAGE_CONF['c++']['exec'],
        ),
        Language(
            "Rust",
            ".rs",
            LANGUAGE_CONF['rust']['build'],
            LANGUAGE_CONF['rust']['exec'],
        )
    ]

    return Languages(languages)
