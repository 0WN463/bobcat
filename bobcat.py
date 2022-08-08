#!/usr/bin/python
import glob
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
import zipfile
import io
import re
import time
import os
import configparser
from pathlib import Path
import urllib.parse
import getpass
import shutil
import subprocess
from ast import literal_eval

config = configparser.ConfigParser()

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

if os.path.exists(SKIP_FILE):
    with open(SKIP_FILE, 'r') as f:
        skipped_questions = f.read().strip().split('\n')
else:
    skipped_questions = []

SCRIPT_PATH = os.path.realpath(__file__)
DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(SCRIPT_PATH), 'config.ini')
config.read([DEFAULT_CONFIG_FILE, CONFIG_FILE])

HOST = config['config']["host"]
SOLUTION_FILE = config['config']['solution_file']
CACHE_DIR = config['config']['cache']
Path(CACHE_DIR).mkdir( parents=True, exist_ok=True )

secret_conf = configparser.ConfigParser()
secret_conf.read(os.path.join(CONFIG_DIR, '.secret.ini'))
LANGUAGE_CONF = config["languages"]
LANGUAGE_CONF = {k: literal_eval(v) for k, v in LANGUAGE_CONF.items()}

@dataclass
class Language:
    name: str # Sent to Kattis to identify language
    ext: str
    build_cmd: str
    run_cmd: str

LANGUAGES = [
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
                )
        ]

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

def get_lang(file: str, languages:list[Language]=LANGUAGES) -> Language | None:
    ext = Path(file).suffix
    lang = next((lang for lang in languages if lang.ext == ext), None)
    return lang

def get_probs(s) -> list[Problem]:
    PROBLEM_LIST_URL = urllib.parse.urljoin(HOST, "/problems?order=%2Bdifficulty_category&show_solved=off&show_tried=on&show_untried=on")
    res = s.get(PROBLEM_LIST_URL)
    soup = BeautifulSoup(res.text, features='lxml')

    trs = [tr for tr in soup.table.tbody.find_all('tr')]

    return [Problem(title=tr.td.text, 
        path=tr.td.a['href'], 
        difficulty=tr.findAll('td')[6].span.text) 
        for tr in trs]

def download_samples(s, path: str, save_to=CACHE_DIR) -> None:
    shutil.rmtree(save_to)
    Path(save_to).mkdir( parents=True, exist_ok=True )
    SAMPLE_URL = urllib.parse.urljoin(HOST, f"{path}/file/statement/samples.zip")
    r = s.get(SAMPLE_URL, stream=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(save_to)

def get_prob(s, path: str):
    r = s.get(f"https://open.kattis.com{path}")
    soup = BeautifulSoup(r.text, features='lxml')

    body = soup.find('div', {'class': 'problembody'})
    samples = [t.extract() for t in body.find_all(class_='sample')]

    for p in body.find_all('p'):
        p.replace_with(re.sub(r'\s+', ' ', p.text))
    return body, samples

def print_sample(sample, i: int):
    sample.tr.extract()
    print(f"Input {i}")
    print(sample.tr.td.extract().text.strip())
    print()
    print(f"Output {i}")
    print(sample.tr.td.extract().text.strip())
    print()

def submit(s, problem_path, source_file) -> int:
    with open(source_file, 'r') as f:
        source = f.read()

    file_name = Path(source_file).name
    language = get_lang(source_file)

    if not language:
        print(f"File extension not supported: {file_name}")
        return 0

    prob = problem_path.replace('/problems/', '')
    code_file = {"code": source, "filename": file_name, "id": 0, "session": None}
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
        raise ValueError()

    return int(m.group(1))


def local_run(solution_file=SOLUTION_FILE, test_case_dir=CACHE_DIR):
    lang = get_lang(solution_file)

    if not lang:
        raise ValueError("Unsupported language")

    in_files = sorted(glob.glob(f'{test_case_dir}/*.in'))

    for file in in_files:
        out_file = file.replace("in", "out")
        ans_file = file.replace("in", "ans")

        build_cmd = lang.build_cmd.format(sol=solution_file, cache_dir=test_case_dir)
        subprocess.Popen(build_cmd, shell=True, stdout=subprocess.PIPE).wait()

        run_cmd = lang.run_cmd.format(source_file=solution_file, cache_dir=test_case_dir)
        run_cmd = f'{run_cmd} < {file}'
        out = subprocess.Popen(run_cmd, shell=True, stdout=subprocess.PIPE).stdout.read().decode('ascii')

        print(f"Input: ")

        with open(file, 'r') as f:
            print(f.read())

        print("Output: ")
        print(out)



def local_test(solution_file=SOLUTION_FILE, test_case_dir=CACHE_DIR) -> bool:
    lang = get_lang(solution_file)

    if not lang:
        raise ValueError("Unsupported language")

    in_files = sorted(glob.glob(f'{test_case_dir}/*.in'))

    is_correct = True
    for file in in_files:
        out_file = file.replace("in", "out")
        ans_file = file.replace("in", "ans")

        build_cmd = lang.build_cmd.format(sol=solution_file, cache_dir=test_case_dir)
        subprocess.Popen(build_cmd, shell=True, stdout=subprocess.PIPE).wait()

        run_cmd = lang.run_cmd.format(source_file=solution_file, cache_dir=test_case_dir)
        diff_cmd = f'{run_cmd} < {file} > {out_file}'
        subprocess.Popen(diff_cmd, shell=True, stdout=subprocess.PIPE).wait()

        diff = subprocess.Popen(f'diff --unified {ans_file} {out_file}', shell=True, stdout=subprocess.PIPE).stdout.read().decode('ascii')

        if diff:
            print(f"Solution produces different output for {file}")
            print(f"Input: ")

            with open(file, 'r') as f:
                print(f.read())

            print("Diff: ")
            print(diff)
            is_correct = False

    return is_correct
    

def get_result(s, submission_id: int) -> (str, str):
    r = s.get(f'https://open.kattis.com/submissions/{submission_id}')
    soup = BeautifulSoup(r.text, features='lxml')
    result = soup.find('div', class_='status').text
    test_cases = soup.find('div', class_='horizontal_item').find_all(text=True)[0]
    return result, test_cases

def on_exit():
    Path(SKIP_DIR).mkdir( parents=True, exist_ok=True )

    with open(SKIP_FILE, 'w+') as f:
        f.write("\n".join(skipped_questions))

if __name__ == '__main__':
    def show_prob(prob):
        desc, samples = get_prob(s, prob.path)
        download_samples(s, prob.path)

        print(f"{prob.title} ({prob.difficulty})")
        print()
        print(desc.text.strip())
        print()
        for i, sample in enumerate(samples, start=1):
            print_sample(sample, i)


    has_cred = secret_conf.has_section('credentials') and 'user' in secret_conf['credentials'] and 'password' in secret_conf['credentials']
    user = secret_conf['credentials']['user'] if has_cred else input("User: ")
    password = secret_conf['credentials']['password'] if has_cred else getpass.getpass()  

    s = login(user, password)
    probs = get_probs(s)

    index = 0
    probs = [ p for p in probs if p.path not in skipped_questions ]
    prob = probs[index]
    show_prob(prob)

    while True:
        key = input("Enter command: ")

        if key.upper() in ['Q', 'EXIT', 'QUIT']:
            on_exit()
            exit()
        if key.upper() in ['>', 'SKIP']:
            skipped_questions.append(prob.path)
            probs = [ p for p in probs if p.path not in skipped_questions ]
            prob = probs[index]
            show_prob(prob)
            print(skipped_questions)
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
        else:
            print(f'"{key}" is not a valid command')

