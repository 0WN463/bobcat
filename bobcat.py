#!/usr/bin/python
import glob
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
import zipfile
import io
import re
import time
from pathlib import Path
import urllib.parse
import getpass
import shutil
import subprocess
import language
import config

conf, secret_conf, skipped_questions = config.get_conf()

HOST = conf['config']["host"]
SOLUTION_FILE = conf['config']['solution_file']
CACHE_DIR = conf['config']['cache']

HELP_MSG = f"""
Commands:
(n)ext: go to next question
(p)revious: go to previous question
(s)ubmit [solution_file]: submit solution. Default file: {SOLUTION_FILE}
(r)un [solution_file]: runs solution file against sample. Default file: {SOLUTION_FILE}
(t)est [solution_file]: runs solution file against sample and checks against expected output. Default file: {SOLUTION_FILE}
(>)/skip: skips current question
(h)/help: shows this message
(q)uit/exit: exits program

"""

LANGUAGES = language.make_languages(conf)

class AuthError(Exception):
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


def get_probs(s) -> list[Problem]:
    PROBLEM_LIST_URL = urllib.parse.urljoin(
        HOST, "/problems?order=%2Bdifficulty_category&show_solved=off&show_tried=on&show_untried=on")
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


def get_prob(s: requests.Session, path: str) -> tuple[str, list]:
    r = s.get(f"https://open.kattis.com{path}")
    soup = BeautifulSoup(r.text, features='lxml')

    body = soup.find('div', {'class': 'problembody'})
    samples = [t.extract() for t in body.find_all(class_='sample')]

    for p in body.find_all('p'):
        p.replace_with(re.sub(r'\s+', ' ', p.text))
    return body.text.strip(), samples


def print_sample(sample, i: int):
    sample.tr.extract()
    print(f"Input {i}")
    print(sample.tr.td.extract().text.strip())
    print()
    print(f"Output {i}")
    print(sample.tr.td.extract().text.strip())
    print()


def submit(s: requests.Session, problem_path, source_file) -> int:
    with open(source_file, 'r') as f:
        source = f.read()

    file_name = Path(source_file).name
    language = LANGUAGES.get_lang(source_file)

    if not language:
        raise ValueError(f"File extension not supported: {file_name}")

    prob = problem_path.replace('/problems/', '')
    code_file = {"code": source, "filename": file_name,
                 "id": 0, "session": None}
    data = {"files": [code_file],
            "language": language.name,
            "problem": prob,
            "mainclass": "",
            "submit": True,
            }
    print(data)
    r = s.post(f"https://open.kattis.com{problem_path}/submit", json=data)

    m = re.match(r'Submission received\. Submission ID: (\d+)\.', r.text)

    if not m:
        raise ValueError("Unable to submit solution")

    return int(m.group(1))


def local_run(solution_file=SOLUTION_FILE, test_case_dir=CACHE_DIR):
    lang = LANGUAGES.get_lang(solution_file)

    if not lang:
        raise ValueError("Unsupported language")

    in_files = sorted(glob.glob(f'{test_case_dir}/*.in'))

    for file in in_files:
        build_cmd = lang.build_cmd.format(
            sol=solution_file, cache_dir=test_case_dir)
        subprocess.Popen(build_cmd, shell=True, stdout=subprocess.PIPE).wait()

        run_cmd = lang.run_cmd.format(
            source_file=solution_file, cache_dir=test_case_dir)
        run_cmd = f'{run_cmd} < {file}'
        out = subprocess.Popen(
            run_cmd, shell=True, stdout=subprocess.PIPE).stdout.read().decode('ascii')

        print(f"Input: ")

        with open(file, 'r') as f:
            print(f.read())

        print("Output: ")
        print(out)
        print()


def local_test(solution_file=SOLUTION_FILE, test_case_dir=CACHE_DIR) -> bool:
    lang = LANGUAGES.get_lang(solution_file)

    if not lang:
        raise ValueError("Unsupported language")

    in_files = sorted(glob.glob(f'{test_case_dir}/*.in'))

    is_correct = True
    for file in in_files:
        out_file = file.replace("in", "out")
        ans_file = file.replace("in", "ans")

        build_cmd = lang.build_cmd.format(
            sol=solution_file, cache_dir=test_case_dir)
        subprocess.Popen(build_cmd, shell=True, stdout=subprocess.PIPE).wait()

        run_cmd = lang.run_cmd.format(
            source_file=solution_file, cache_dir=test_case_dir)
        diff_cmd = f'{run_cmd} < {file} > {out_file}'
        subprocess.Popen(diff_cmd, shell=True, stdout=subprocess.PIPE).wait()

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


if __name__ == '__main__':
    def show_prob(prob):
        desc, samples = get_prob(s, prob.path)
        download_samples(s, prob.path)

        print(f"{prob.title} ({prob.difficulty})")
        print()
        print(desc)
        print()
        for i, sample in enumerate(samples, start=1):
            print_sample(sample, i)

    has_cred = secret_conf.has_section(
        'credentials') and 'user' in secret_conf['credentials'] and 'password' in secret_conf['credentials']
    user = secret_conf['credentials']['user'] if has_cred else input("User: ")
    password = secret_conf['credentials']['password'] if has_cred else getpass.getpass(
    )
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

    s = login(user, password)
    probs = get_probs(s)

    index = 0
    probs = [p for p in probs if p.path not in skipped_questions]
    prob = probs[index]
    show_prob(prob)

    while True:
        key = input("Enter command: ")

        if key.upper() in ['Q', 'EXIT', 'QUIT']:
            config.save_skipped(skipped_questions)
            exit()
        if key.upper() in ['>', 'SKIP']:
            skipped_questions.append(prob.path)
            probs = [p for p in probs if p.path not in skipped_questions]
            prob = probs[index]
            show_prob(prob)
        elif m := re.match(r'(t|T)(\s+(\S*))?', key):
            solution_file = m.group(3) if m.group(3) else SOLUTION_FILE
            print(f"Testing {solution_file}")

            if local_test(solution_file):
                print(f"Passed all test cases")
        elif m := re.match(r'(r|R)(\s+(\S*))?', key):
            solution_file = m.group(3) if m.group(3) else SOLUTION_FILE
            print(f"Running {solution_file}")
            local_run(solution_file)

        elif m := re.match(r'(s|S)(\s+(\S*))?', key):
            solution_file = m.group(3) if m.group(3) else SOLUTION_FILE
            print(f"Submitting {solution_file}")

            if not local_test(solution_file):
                if input("Submit anyways? (y/N): ").upper() != 'Y':
                    continue

            submission_id = submit(s, prob.path, solution_file)
            print(f"Submitted. ID: {submission_id}")

            while result := get_result(s, submission_id):
                status, test_cases = result
                print(f"Running... ({test_cases})")
                if status not in ['Running', 'New', 'Compiling']:
                    break

                time.sleep(1)

            print(result)
        elif key.upper() == 'N':
            index += 1
            prob = probs[index]
            show_prob(prob)
        elif key.upper() == 'P':
            index = max(0, index - 1)
            prob = probs[index]
            show_prob(prob)
        elif key.upper() == 'H':
            print(HELP_MSG)
        else:
            print(f'"{key}" is not a valid command')
            print(HELP_MSG)

