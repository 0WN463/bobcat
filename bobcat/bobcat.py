#!/usr/bin/env python

import getpass
import os

from pathlib import Path

from . import config
from . import state
from . import kattis
from . import command

conf, secret_conf, skipped_questions = config.get_conf()

CACHE_DIR = conf['config']['cache']
Q_FILTERS = conf['config']['filters'].strip().split(" ")
Q_ORDER = conf['config']['sort_order'].strip()


def main():
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

    has_cred = secret_conf.has_section(
        'credentials') and 'user' in secret_conf['credentials'] and 'password' in secret_conf['credentials']
    user = secret_conf['credentials']['user'] if has_cred else input("User: ")
    password = secret_conf['credentials']['password'] if has_cred else getpass.getpass(
    )

    s = kattis.login(user, password)
    probs = [
        p for p in kattis.get_probs(
            s,
            Q_FILTERS,
            Q_ORDER,
            0) if p.path not in skipped_questions]
    curr_state = state.State(s, probs, 0, probs[0])
    command.show_prob(curr_state)

    while True:
        usr_input = input("Enter command: ")
        keyword = usr_input.split(" ")[0].upper()

        for cmd in command.COMMANDS:
            if keyword in cmd.keywords:
                curr_state = cmd.func(curr_state, usr_input)
                print(curr_state)
                break
        else:
            os.system('clear')
            print(f'"{usr_input}" is not a valid command\n')
            command.cmd_help(curr_state, clear=False)
            continue
