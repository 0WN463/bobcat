#!/usr/bin/env python

import getpass
import glob
import os
import re
import subprocess
import time

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import config
from .model import Sample, Problem, ConcreteProblem
from . import state
from . import language
from . import kattis

conf, secret_conf, skipped_questions = config.get_conf()

TIMEOUT = conf['config'].getint("timeout")
SOLUTION_FILE = conf['config']['solution_file']
CACHE_DIR = conf['config']['cache']
LOCAL_TEST = conf['config'].getboolean('local_test')
Q_FILTERS = conf['config']['filters'].strip().split(" ")
Q_ORDER = conf['config']['sort_order'].strip()


@dataclass
class Command:
    label: str
    description: str
    keywords: list[str] = field(default_factory=list)
    func: Callable[[str], None] = field(init=False)


COMMANDS: list[Command] = []


def register_command(cmd: Command):
    def decorator_reg(func):
        def inner(*args, **kwargs):
            return func(*args, **kwargs)
        cmd.func = func
        return inner

    COMMANDS.append(cmd)
    return decorator_reg


LANGUAGES = language.make_languages(conf)


def local_run(solution_file=SOLUTION_FILE, test_case_dir=CACHE_DIR):
    lang = LANGUAGES.get_lang(solution_file)

    in_files = sorted(glob.glob(f'{test_case_dir}/*.in'))

    for file in in_files:
        build_cmd = lang.build_cmd.format(
            source_file=solution_file, cache_dir=test_case_dir)
        build_code = subprocess.Popen(
            build_cmd, shell=True, stdout=subprocess.PIPE).wait()

        if build_code > 0:
            print("Build failed")
            break

        run_cmd = lang.run_cmd.format(
            source_file=solution_file, cache_dir=test_case_dir)
        run_cmd = f'timeout {TIMEOUT} {run_cmd} < {file}'
        p = subprocess.Popen(
            run_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        ret_code = p.wait()
        out = p.stdout.read().decode('utf8')
        err = p.stderr.read().decode('utf8')

        print("Input: ")

        with open(file, 'r', encoding='utf-8') as f:
            print(f.read())

        print("Output: ")
        print(out)

        if ret_code == 124:
            print("Program timed out")
        elif ret_code or err:
            print(f"Program terminated with exit code {ret_code}")
            print(err)

        print()


def local_test(solution_file=SOLUTION_FILE, test_case_dir=CACHE_DIR) -> bool:
    lang = LANGUAGES.get_lang(solution_file)

    in_files = sorted(glob.glob(f'{test_case_dir}/*.in'))

    is_correct = True
    for file in in_files:
        out_file = file.replace(".in", ".out")
        ans_file = file.replace(".in", ".ans")

        build_cmd = lang.build_cmd.format(
            source_file=solution_file, cache_dir=test_case_dir)
        build_code = subprocess.Popen(
            build_cmd, shell=True, stdout=subprocess.PIPE).wait()

        if build_code > 0:
            print("Build failed")
            return False

        run_cmd = lang.run_cmd.format(
            source_file=solution_file, cache_dir=test_case_dir)
        diff_cmd = f'timeout {TIMEOUT} {run_cmd} < {file} > {out_file}'
        p = subprocess.Popen(diff_cmd, shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        ret_code = p.wait()
        err = p.stderr.read().decode('ascii')

        if err or ret_code:
            print("Input: ")

            with open(file, 'r', encoding="utf-8") as f:
                print(f.read())

            if ret_code == 124:
                print("Program timed out")
            else:
                print(f"Program terminated with exit code of {ret_code}")
                print(err)
            print()
            is_correct = False
            continue

        diff = subprocess.Popen(
            f'diff --unified {ans_file} {out_file}',
            shell=True,
            stdout=subprocess.PIPE).stdout.read().decode('ascii')

        if diff:
            print(f"Solution produces different output for {file}")
            print(f"Input: ")

            with open(file, 'r') as f:
                print(f.read())

            print()

            print("Diff: ")
            print(diff)
            print()
            is_correct = False

    return is_correct


def main():
    def print_desc(prob: ConcreteProblem):
        print(f"{prob.path}")
        print(f"{prob.title} ({prob.difficulty})")
        print()
        print(prob.description)
        print()

    def print_sample(sample: Sample, i: int):
        print(f"Input {i}")
        print(sample.input_)
        print()
        print(f"Output {i}")
        print(sample.output_)
        print()

    def show_prob(prob: Problem | ConcreteProblem):
        os.system('clear')
        if not isinstance(prob, ConcreteProblem):
            kattis.download_samples(s, prob.path)

            desc, samples = kattis.fetch_prob(s, prob.path)
            prob = ConcreteProblem(
                **prob.__dict__, description=desc, samples=samples)
            probs[index] = prob

        print_desc(prob)
        for i, sample in enumerate(prob.samples, start=1):
            print_sample(sample, i)

    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

    has_cred = secret_conf.has_section(
        'credentials') and 'user' in secret_conf['credentials'] and 'password' in secret_conf['credentials']
    user = secret_conf['credentials']['user'] if has_cred else input("User: ")
    password = secret_conf['credentials']['password'] if has_cred else getpass.getpass(
    )

    s = kattis.login(user, password)
    probs = [p for p in kattis.get_probs(s, Q_FILTERS, Q_ORDER, 0) if p.path not in skipped_questions]
    index = 0
    show_prob(probs[index])
    prob = probs[index]

    @register_command(Command("(n)ext [N=1]", "go to next N question", ['N']))
    def cmd_next(command: str):
        if not (m := re.match(r'(n|N)(\s+(\d*))?', command)):
            return

        os.system('clear')
        num = m.group(3) if m.group(3) else 1

        nonlocal index, prob, probs

        if index == len(probs) - 1:
            new_probs = kattis.get_probs(s, Q_FILTERS, Q_ORDER, 1)
            probs.extend(new_probs)

        index += int(num)
        index = min(index, len(probs) - 1)
        show_prob(probs[index])
        prob = probs[index]
        print(index, len(probs))

    @register_command(Command("(p)revious", "go to previous question", ["P"]))
    def cmd_prev(*_: str):
        nonlocal index, prob, probs
        index = max(0, index - 1)
        show_prob(probs[index])
        prob = probs[index]
        # Need to repopulate samples of previous problem
        kattis.download_samples(s, prob.path)

    @register_command(Command("(>)/skip",
                      "skips current question", [">", "SKIP"]))
    def cmd_skip(*_: str):
        nonlocal index, prob, probs
        skipped_questions.append(prob.path)
        probs = [p for p in probs if p.path not in skipped_questions]
        show_prob(probs[index])
        prob = probs[index]

    @register_command(Command("(i)nfo",
                              "show information (description and samples) of current question",
                              ["I",
                               "INFO"]))
    def cmd_info(*_: str):
        show_prob(prob)

    @register_command(Command("(d)escription",
                      "show description of current question", ["D"]))
    def cmd_desc(*_: str):
        os.system('clear')
        print_desc(prob)

    @register_command(Command("(e)xample",
                      "show samples of current question", ["E"]))
    def cmd_example(*_: str):
        os.system('clear')

        if not prob.samples:
            print("No samples")
            return

        for i, sample in enumerate(prob.samples):
            print_sample(sample, i)

    @register_command(
        Command(
            "(t)est [SOLUTION_FILE]",
            f"runs solution file against sample and checks against expected output. Default file: {SOLUTION_FILE}",
            ["T"]))
    def cmd_test(command: str):
        if not (m := re.match(r'(t|T)(\s+(\S*))?', command)):
            return

        os.system('clear')
        solution_file = m.group(3) if m.group(3) else SOLUTION_FILE
        print(f"Testing {solution_file}")

        try:
            if local_test(solution_file):
                print("Passed all test cases")
        except language.ExtensionNotSupported as e:
            print(e)

    @register_command(
        Command(
            "(r)un [SOLUTION_FILE]",
            f"runs solution file against sample. Default file: {SOLUTION_FILE}",
            ["R"]))
    def cmd_run(command: str):
        if not (m := re.match(r'(r|R)(\s+(\S*))?', command)):
            return
        os.system('clear')
        solution_file = m.group(3) if m.group(3) else SOLUTION_FILE
        print(f"Running {solution_file}")

        try:
            local_run(solution_file)
        except language.ExtensionNotSupported as e:
            print(e)

    @register_command(
        Command(
            "(s)ubmit [SOLUTION_FILE]",
            f"submit solution. Default file: {SOLUTION_FILE}",
            ["S"]))
    def cmd_submit(command: str):
        if not (m := re.match(r'(s|S)(\s+(\S*))?', command)):
            return

        os.system('clear')
        solution_file = m.group(3) if m.group(3) else SOLUTION_FILE

        try:
            if LOCAL_TEST and not local_test(solution_file):
                print("Local test failed")
                if input("Submit anyways? (y/N): ").upper() != 'Y':
                    return

            submission_id = kattis.submit(
                s, prob.path, solution_file, LANGUAGES)
            print(f"Submitted. ID: {submission_id}")

            while result := kattis.get_result(s, submission_id):
                status, test_cases, _ = result
                print(f"{status}: ({test_cases})")
                if status not in ['Running', 'New', 'Compiling']:
                    break

                time.sleep(1)

            print(result)
        except language.ExtensionNotSupported as e:
            print(e)

    @register_command(Command("(o)pen PROBLEM_ID",
                      "loads the problem with the problem ID", ["O"]))
    def cmd_open(command: str):
        if not (m := re.match(r'(o|O)\s+(\S*)', command)):
            return

        os.system('clear')

        if not m.group(2):
            print("Problem ID required")
            return

        path = f"/problems/{m.group(2)}"

        try:
            desc, samples, difficulty, title = kattis.fetch_prob(
                s, path, with_details=True)
        except kattis.ProblemNotFound:
            print(f"No problems found that has a ID of {m.group(2)}")
            return

        nonlocal prob
        prob = ConcreteProblem(
            difficulty=difficulty,
            path=path,
            title=title,
            description=desc,
            samples=samples)
        kattis.download_samples(s, prob.path)

        print_desc(prob)
        for i, sample in enumerate(prob.samples, start=1):
            print_sample(sample, i)

    @register_command(Command("(c)hoose SOLUTION_FILE",
                              "sets default solution file to use when running/submitting",
                              ['C']))
    def cmd_choose(command: str):
        if not (m := re.match(r'(c|C)\s+(\S+)', command)):
            print("Please supply a path to the target solution file")
            return

        if not m.group(2):
            print("Please supply a path to the target solution file")
            return

        os.system('clear')

        global SOLUTION_FILE
        SOLUTION_FILE = m.group(2)

    @register_command(Command("(h)elp", "displays help", ["H", "?"]))
    def cmd_help(*_: str, clear=True):
        if clear:
            os.system('clear')
        msg = "\n".join(f"{c.label}: {c.description}" for c in COMMANDS)
        print("Commands:")
        print(msg)
        print()

    @register_command(Command("(q)uit", "exits the program",
                      ['Q', 'EXIT', 'QUIT']))
    def cmd_quit(*_: str):
        config.save_skipped(skipped_questions)
        exit()

    while True:
        curr_state = state.State(s, probs, index, prob)
        print(curr_state)
        key = input("Enter command: ")
        keyword = key.split(" ")[0].upper()

        for cmd in COMMANDS:
            if keyword in cmd.keywords:
                cmd.func(key)
                break
        else:
            os.system('clear')
            print(f'"{key}" is not a valid command\n')
            cmd_help(clear=False)
            continue
