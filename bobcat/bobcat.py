#!/usr/bin/env python
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from . import config
import getpass
import glob
import io
from . import language
import os
import re
import requests
import shutil
import subprocess
import time
import urllib.parse
import zipfile


conf, secret_conf, skipped_questions = config.get_conf()

HOST = conf['config']["host"]
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


class AuthError(Exception):
    pass


class ProblemNotFound(Exception):
    pass



def login(username: str, password: str):
    LOGIN_URL = urllib.parse.urljoin(HOST, 'login')
    s = requests.Session()
    data = {"user": username, "password": password, "script": True}

    res = s.post(LOGIN_URL, data=data)

    if res.status_code != 200:
        raise AuthError("Unable to login")

    return s


@dataclass
class Problem:
    title: str
    path: str
    difficulty: str


@dataclass
class Sample:
    input_: str
    output_: str


@dataclass
class ConcreteProblem(Problem):
    description: str
    samples: list[Sample]


def get_probs(s, filters: list[str], ordering: str) -> list[Problem]:
    filter_params = [f"show_{f}=off" for f in filters if f in [
        "tried", "untried", "solved"]]
    order_params = [f'order={ordering.replace("+", "%2B")}']
    query_param = "&".join([*order_params, *filter_params])

    PROBLEM_LIST_URL = urllib.parse.urljoin(
        HOST, f"/problems?{query_param}")
    res = s.get(PROBLEM_LIST_URL)
    soup = BeautifulSoup(res.text, features='lxml')

    trs = [tr for tr in soup.table.tbody.find_all('tr')]

    return [Problem(title=tr.td.text,
                    path=tr.td.a['href'],
                    difficulty=tr.findAll('td')[6].span.text)
            for tr in trs]


def download_samples(s: requests.Session, path: str, save_to=CACHE_DIR) -> None:
    shutil.rmtree(save_to)
    Path(save_to).mkdir(parents=True, exist_ok=True)
    SAMPLE_URL = urllib.parse.urljoin(
        HOST, f"{path}/file/statement/samples.zip")
    r = s.get(SAMPLE_URL, stream=True)

    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(save_to)
    except Exception:
        print("No samples")


def fetch_prob(s: requests.Session, path: str, with_details: bool = False) -> tuple[str, list[Sample]] | tuple[str, list[Sample], str, str]:
    r = s.get(f"https://open.kattis.com{path}")
    soup = BeautifulSoup(r.text, features='lxml')
    if '404' in soup.find('title').text:
        raise ProblemNotFound("Problem not found")

    body = soup.find('div', {'class': 'problembody'})

    samples = [t.extract() for t in body.find_all(class_='sample')]
    _ = [s.tr.extract() for s in samples]

    # We will face error trying to extract samples of "interactive" problems
    try:
        samples = [Sample(input_=s.tr.td.extract().text.strip(),
                          output_=s.tr.td.extract().text.strip()) for s in samples]
    except Exception:
        body.text.strip(), []

    for p in body.find_all('p'):
        p.replace_with(re.sub(r'\s+', ' ', p.text))

    if with_details:
        return body.text.strip(), samples, soup.find('span', {'class': 'difficulty_number'}).text.strip(), soup.find('h1', {'class': 'book-page-heading'}).text.strip(),

    return body.text.strip(), samples


def submit(s: requests.Session, problem_path, source_file) -> int:
    with open(os.path.expanduser(source_file), 'r') as f:
        source = f.read()

    file_name = Path(source_file).name
    lang = LANGUAGES.get_lang(source_file)

    prob = problem_path.replace('/problems/', '')
    code_file = {"code": source, "filename": file_name,
                 "id": 0, "session": None}
    data = {"files": [code_file],
            "language": lang.name,
            "problem": prob,
            "mainclass": "",
            "submit": True,
            }

    r = s.post(f"https://open.kattis.com{problem_path}/submit", json=data)

    m = re.match(r'Submission received\. Submission ID: (\d+)\.', r.text)

    if not m:
        raise ValueError("Unable to submit solution")

    return int(m.group(1))


def local_run(solution_file=SOLUTION_FILE, test_case_dir=CACHE_DIR):
    lang = LANGUAGES.get_lang(solution_file)

    in_files = sorted(glob.glob(f'{test_case_dir}/*.in'))

    for file in in_files:
        build_cmd = lang.build_cmd.format(
            source_file=solution_file, cache_dir=test_case_dir)
        subprocess.Popen(build_cmd, shell=True, stdout=subprocess.PIPE).wait()

        run_cmd = lang.run_cmd.format(
            source_file=solution_file, cache_dir=test_case_dir)
        run_cmd = f'{run_cmd} < {file}'
        p = subprocess.Popen(
            run_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ret_code = p.wait()
        out = p.stdout.read().decode('ascii')
        err = p.stderr.read().decode('ascii')

        print(f"Input: ")

        with open(file, 'r') as f:
            print(f.read())

        print("Output: ")
        print(out)

        if ret_code or err:
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
        subprocess.Popen(build_cmd, shell=True, stdout=subprocess.PIPE).wait()

        run_cmd = lang.run_cmd.format(
            source_file=solution_file, cache_dir=test_case_dir)
        diff_cmd = f'{run_cmd} < {file} > {out_file}'
        p = subprocess.Popen(diff_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        ret_code = p.wait()
        err = p.stderr.read().decode('ascii')

        if err or ret_code:
            print(f"Input: ")

            with open(file, 'r') as f:
                print(f.read())

            print(f"Program terminated with exit code of {ret_code}")
            print(err)
            print()
            is_correct = False
            continue

        diff = subprocess.Popen(f'diff --unified {ans_file} {out_file}',
                                shell=True, stdout=subprocess.PIPE).stdout.read().decode('ascii')

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


def get_result(s: requests.Session, submission_id: int) -> tuple[str, str]:
    r = s.get(f'https://open.kattis.com/submissions/{submission_id}')
    soup = BeautifulSoup(r.text, features='lxml')
    result = soup.find('div', class_='status').text
    test_cases = soup.find(
        'div', class_='horizontal_item').find_all(text=True)[0]
    return result, test_cases


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
            download_samples(s, prob.path)

            desc, samples = fetch_prob(s, prob.path)
            prob = ConcreteProblem(
                **prob.__dict__, description=desc, samples=samples)
            probs[index] = prob

        print_desc(prob)
        for i, sample in enumerate(prob.samples, start=1):
            print_sample(sample, i)

    has_cred = secret_conf.has_section(
        'credentials') and 'user' in secret_conf['credentials'] and 'password' in secret_conf['credentials']
    user = secret_conf['credentials']['user'] if has_cred else input("User: ")
    password = secret_conf['credentials']['password'] if has_cred else getpass.getpass(
    )
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

    s = login(user, password)
    probs = get_probs(s, Q_FILTERS, Q_ORDER)

    index = 0
    probs = [p for p in probs if p.path not in skipped_questions]
    show_prob(probs[index])
    prob = probs[index]

    @register_command(Command("(n)ext", "go to next question", ['N']))
    def cmd_next(*_: str):
        nonlocal index, prob, probs
        index += 1
        show_prob(probs[index])
        prob = probs[index]

    @register_command(Command("(p)revious", "go to previous question", ["P"]))
    def cmd_prev(*_: str):
        nonlocal index, prob, probs
        index = max(0, index - 1)
        show_prob(probs[index])
        prob = probs[index]
        # Need to repopulate samples of previous problem
        download_samples(s, prob.path)

    @register_command(Command("(>)/skip", "skips current question", [">", "SKIP"]))
    def cmd_skip(*_: str):
        nonlocal index, prob, probs
        skipped_questions.append(prob.path)
        probs = [p for p in probs if p.path not in skipped_questions]
        show_prob(probs[index])
        prob = probs[index]

    @register_command(Command("(i)nfo", "show information (description and samples) of current question", ["I", "INFO"]))
    def cmd_info(*_: str):
        show_prob(prob)

    @register_command(Command("(d)escription", "show description of current question", ["D"]))
    def cmd_desc(*_: str):
        os.system('clear')
        print_desc(prob)

    @register_command(Command("(e)xample", "show samples of current question", ["E"]))
    def cmd_example(*_: str):
        os.system('clear')

        if not prob.samples:
            print("No samples")
            return

        for i, sample in enumerate(prob.samples):
            print_sample(sample, i)

    @register_command(Command("(t)est [solution_file]", f"runs solution file against sample and checks against expected output. Default file: {SOLUTION_FILE}", ["T"]))
    def cmd_test(command: str):
        if not (m := re.match(r'(t|T)(\s+(\S*))?', command)):
            return

        os.system('clear')
        solution_file = m.group(3) if m.group(3) else SOLUTION_FILE
        print(f"Testing {solution_file}")
    
        try:
            if local_test(solution_file):
                print(f"Passed all test cases")
        except language.ExtensionNotSupported as e:
            print(e)


    @register_command(Command("(r)un [solution_file]", f"runs solution file against sample. Default file: {SOLUTION_FILE}", ["R"]))
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

    @register_command(Command("(s)ubmit [solution_file]", f"submit solution. Default file: {SOLUTION_FILE}", ["S"]))
    def cmd_submit(command: str):
        if not(m := re.match(r'(s|S)(\s+(\S*))?', command)):
            return

        os.system('clear')
        solution_file = m.group(3) if m.group(3) else SOLUTION_FILE

        try:
            if LOCAL_TEST and not local_test(solution_file):
                print("Local test failed")
                if input("Submit anyways? (y/N): ").upper() != 'Y':
                    return

            submission_id = submit(s, prob.path, solution_file)
            print(f"Submitted. ID: {submission_id}")

            while result := get_result(s, submission_id):
                status, test_cases = result
                print(f"Running... ({test_cases})")
                if status not in ['Running', 'New', 'Compiling']:
                    break

                time.sleep(1)

            print(result)
        except language.ExtensionNotSupported as e:
            print(e)

    @register_command(Command("(o)pen PROBLEM_ID", "Loads the problem with the problem ID", ["O"]))
    def cmd_open(command: str):
        if not (m := re.match(r'(o|O)\s+(\S*)', command)):
            return

        os.system('clear')

        if not m.group(2):
            print("Problem ID required")
            return

        path = f"/problems/{m.group(2)}"

        try:
            desc, samples, difficulty, title = fetch_prob(
                s, path, with_details=True)
        except ProblemNotFound:
            print(f"No problems found that has a ID of {m.group(2)}")
            return

        nonlocal prob
        prob = ConcreteProblem(
            difficulty=difficulty, path=path, title=title, description=desc, samples=samples)
        download_samples(s, prob.path)

        print_desc(prob)
        for i, sample in enumerate(prob.samples, start=1):
            print_sample(sample, i)

    @register_command(Command("(h)elp", "displays help", ["H", "?"]))
    def cmd_help(*_: str, clear=True):
        if clear:
            os.system('clear')
        msg = "\n".join(f"{c.label}: {c.description}" for c in COMMANDS)
        print("Commands:")
        print(msg)
        print()

    @register_command(Command("(q)uit", "exits the program", ['Q', 'EXIT', 'QUIT']))
    def cmd_quit(*_: str):
        config.save_skipped(skipped_questions)
        exit()

    while True:
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
