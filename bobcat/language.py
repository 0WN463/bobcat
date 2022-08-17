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

    languages = [Language(lang,
                          LANGUAGE_CONF[lang]['ext'],
                          LANGUAGE_CONF[lang]['build'],
                          LANGUAGE_CONF[lang]['exec']) for lang in LANGUAGE_CONF]

    return Languages(languages)
