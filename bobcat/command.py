import os
import glob
import re
import subprocess
import time

from dataclasses import dataclass, field
from typing import Callable

from . import state
from . import kattis
from . import config
from . import model
from . import language


@dataclass
class Command:
    label: str
    description: str
    keywords: list[str] = field(default_factory=list)
    func: Callable[[state.State, str], state.State] = field(init=False)


conf, _, skipped_questions = config.get_conf()

TIMEOUT = conf['config'].getint("timeout")
SOLUTION_FILE = conf['config']['solution_file']
CACHE_DIR = conf['config']['cache']
LOCAL_TEST = conf['config'].getboolean('local_test')
Q_FILTERS = conf['config']['filters'].strip().split(" ")
Q_ORDER = conf['config']['sort_order'].strip()

LANGUAGES = language.make_languages(conf)

COMMANDS: list[Command] = []


def register_command(cmd: Command):
    def decorator_reg(func):
        def inner(*args, **kwargs):
            return func(*args, **kwargs)
        cmd.func = func
        return inner

    COMMANDS.append(cmd)
    return decorator_reg


@register_command(Command("(n)ext [N=1]", "go to next N question", ['N']))
def cmd_next(s: state.State, command: str) -> state.State:
    if not (m := re.match(r'(n|N)(\s+(\d*))?', command)):
        return s

    os.system('clear')
    num = m.group(3) if m.group(3) else 1

    if s.index == len(s.problems) - 1:
        new_probs = kattis.get_probs(s.session, Q_FILTERS, Q_ORDER, 1)
        s.problems.extend(new_probs)

    index = min(s.index + int(num), len(s.problems) - 1)
    new_state = s.with_index(index)
    show_prob(new_state)

    return new_state


@register_command(Command("(p)revious", "go to previous question", ["P"]))
def cmd_prev(s: state.State, *_: str) -> state.State:
    index = max(0, s.index - 1)
    new_state = s.with_index(index)

    # Need to repopulate samples of previous problem
    kattis.download_samples(s.session, new_state.curr_prob.path)

    show_prob(new_state)
    return new_state


@register_command(Command("(>)/skip",
                  "skips current question", [">", "SKIP"]))
def cmd_skip(s: state.State, *_: str) -> state.State:
    skipped_questions.append(s.curr_prob.path)

    new_state = s.with_index(s.index)
    new_state.problems = [
        p for p in s.problems if p.path not in skipped_questions]
    show_prob(new_state)
    return new_state


@register_command(Command("(i)nfo",
                          "show information (description and samples) of current question",
                          ["I",
                           "INFO"]))
def cmd_info(s: state.State, *_: str) -> state.State:
    show_prob(s)
    return s


@register_command(Command("(d)escription",
                  "show description of current question", ["D"]))
def cmd_desc(s: state.State, *_: str) -> state.State:
    os.system('clear')
    print_desc(s.curr_prob)

    return s


@register_command(Command("(e)xample",
                  "show samples of current question", ["E"]))
def cmd_example(s: state.State, *_: str) -> state.State:
    os.system('clear')

    if not s.curr_prob.samples:
        print("No samples")
        return s

    for i, sample in enumerate(s.curr_prob.samples):
        print_sample(sample, i)

    return s


@register_command(
    Command(
        "(t)est [SOLUTION_FILE]",
        f"runs solution file against sample and checks against expected output. Default file: {SOLUTION_FILE}",
        ["T"]))
def cmd_test(s: state.State, command: str) -> state.State:
    if not (m := re.match(r'(t|T)(\s+(\S*))?', command)):
        return s

    os.system('clear')
    solution_file = m.group(3) if m.group(3) else SOLUTION_FILE
    print(f"Testing {solution_file}")

    try:
        if local_test(solution_file):
            print("Passed all test cases")
    except language.ExtensionNotSupported as e:
        print(e)
    finally:
        return s


@register_command(
    Command(
        "(r)un [SOLUTION_FILE]",
        f"runs solution file against sample. Default file: {SOLUTION_FILE}",
        ["R"]))
def cmd_run(s: state.State, command: str) -> state.State:
    if not (m := re.match(r'(r|R)(\s+(\S*))?', command)):
        return s
    os.system('clear')
    solution_file = m.group(3) if m.group(3) else SOLUTION_FILE
    print(f"Running {solution_file}")

    try:
        local_run(solution_file)
    except language.ExtensionNotSupported as e:
        print(e)
    finally:
        return s


@register_command(
    Command(
        "(s)ubmit [SOLUTION_FILE]",
        f"submit solution. Default file: {SOLUTION_FILE}",
        ["S"]))
def cmd_submit(s: state.State, command: str) -> state.State:
    if not (m := re.match(r'(s|S)(\s+(\S*))?', command)):
        return s

    os.system('clear')
    solution_file = m.group(3) if m.group(3) else SOLUTION_FILE

    try:
        if LOCAL_TEST and not local_test(solution_file):
            print("Local test failed")
            if input("Submit anyways? (y/N): ").upper() != 'Y':
                return s

        submission_id = kattis.submit(
            s.session, s.curr_prob.path, solution_file, LANGUAGES)
        print(f"Submitted. ID: {submission_id}")

        while result := kattis.get_result(s.session, submission_id):
            status, test_cases, _ = result
            print(f"{status}: ({test_cases})")
            if status not in ['Running', 'New', 'Compiling']:
                break

            time.sleep(1)

        print(result)
    except language.ExtensionNotSupported as e:
        print(e)
    finally:
        return s


@register_command(Command("(o)pen PROBLEM_ID",
                  "loads the problem with the problem ID", ["O"]))
def cmd_open(s: state.State, command: str) -> state.State:
    if not (m := re.match(r'(o|O)\s+(\S*)', command)):
        return s

    os.system('clear')

    if not m.group(2):
        print("Problem ID required")
        return s

    path = f"/problems/{m.group(2)}"

    try:
        desc, samples, difficulty, title = kattis.fetch_prob(
            s.session, path, with_details=True)
    except kattis.ProblemNotFound:
        print(f"No problems found that has a ID of {m.group(2)}")
        return s

    prob = model.ConcreteProblem(
        difficulty=difficulty,
        path=path,
        title=title,
        description=desc,
        samples=samples)
    kattis.download_samples(s.session, prob.path)

    print_desc(prob)
    for i, sample in enumerate(prob.samples, start=1):
        print_sample(sample, i)

    return state.State(s.session, s.problems, s.index, prob)


@register_command(Command("(c)hoose SOLUTION_FILE",
                          "sets default solution file to use when running/submitting",
                          ['C']))
def cmd_choose(s: state.State, command: str) -> state.State:
    if not (m := re.match(r'(c|C)\s+(\S+)', command)):
        print("Please supply a path to the target solution file")
        return s

    if not m.group(2):
        print("Please supply a path to the target solution file")
        return s

    os.system('clear')

    global SOLUTION_FILE
    SOLUTION_FILE = m.group(2)
    return s


@register_command(Command("(h)elp", "displays help", ["H", "?"]))
def cmd_help(s: state.State, *_: str, clear=True) -> state.State:
    if clear:
        os.system('clear')
    msg = "\n".join(f"{c.label}: {c.description}" for c in COMMANDS)
    print("Commands:")
    print(msg)
    print()

    return s


@register_command(Command("(q)uit", "exits the program",
                  ['Q', 'EXIT', 'QUIT']))
def cmd_quit(*_: str) -> state.State:
    config.save_skipped(skipped_questions)
    exit()


def print_desc(prob: model.ConcreteProblem):
    print(f"{prob.path}")
    print(f"{prob.title} ({prob.difficulty})")
    print()
    print(prob.description)
    print()


def print_sample(sample: model.Sample, i: int):
    print(f"Input {i}")
    print(sample.input_)
    print()
    print(f"Output {i}")
    print(sample.output_)
    print()


def show_prob(s: state.State):
    os.system('clear')
    if not isinstance(s.curr_prob, model.ConcreteProblem):
        kattis.download_samples(s.session, s.curr_prob.path)

        desc, samples = kattis.fetch_prob(s.session, s.curr_prob.path)
        s.curr_prob = model.ConcreteProblem(
            **s.curr_prob.__dict__, description=desc, samples=samples)
        s.problems[s.index] = s.curr_prob

    print_desc(s.curr_prob)
    for i, sample in enumerate(s.curr_prob.samples, start=1):
        print_sample(sample, i)


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
            print("Input: ")

            with open(file, 'r') as f:
                print(f.read())

            print()

            print("Diff: ")
            print(diff)
            print()
            is_correct = False

    return is_correct
