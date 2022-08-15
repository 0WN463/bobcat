from configparser import ConfigParser
import os
from pathlib import Path


if 'XDG_CONFIG_HOME' in os.environ:
    CONFIG_DIR = os.path.join(os.environ.get('XDG_CONFIG_HOME'), 'bobcat')
    CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.ini')
else:
    CONFIG_DIR = Path.home()
    CONFIG_FILE = os.path.join(CONFIG_DIR, '.bobcat.ini')

SKIP_DIR = os.path.join(os.environ.get('XDG_STATE_HOME'), 'bobcat') \
    if 'XDG_STATE_HOME' in os.environ \
    else os.path.join(Path.home(), '.local', 'state', 'bobcat')

SKIP_FILE = os.path.join(SKIP_DIR, 'skipped')


def get_conf() -> tuple[ConfigParser, ConfigParser, list[str]]:
    config = ConfigParser()
    config.optionxform = str
    script_path = os.path.realpath(__file__)
    DEFAULT_CONFIG_FILE = os.path.join(
        os.path.dirname(script_path), 'config.ini')
    config.read([DEFAULT_CONFIG_FILE, CONFIG_FILE])

    secret_conf = ConfigParser()
    secret_conf.read(os.path.join(CONFIG_DIR, '.secret.ini'))

    if os.path.exists(SKIP_FILE):
        with open(SKIP_FILE, 'r') as f:
            skipped_questions = f.read().strip().split('\n')
    else:
        skipped_questions = []

    return config, secret_conf, skipped_questions


def save_skipped(skipped_questions: list[str]):
    Path(SKIP_DIR).mkdir(parents=True, exist_ok=True)

    with open(SKIP_FILE, 'w+') as f:
        f.write("\n".join(skipped_questions))
