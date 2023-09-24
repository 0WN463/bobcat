import io
import os
import re
import shutil
import unicodedata
import zipfile

from pathlib import Path
from urllib.parse import urljoin
from typing import overload, Literal, Final

import requests
from bs4 import BeautifulSoup

from . import config
from .language import Languages
from .model import Sample, Problem


conf, secret_conf, skipped_questions = config.get_conf()

HOST = conf['config']["host"]
CACHE_DIR = conf['config']['cache']


class ProblemNotFound(Exception):
    pass


class AuthError(Exception):
    pass


def login(username: str, password: str):
    LOGIN_URL = urljoin(HOST, 'login')
    s = requests.Session()
    data = {"user": username, "password": password, "script": True}

    res = s.post(LOGIN_URL, data=data)

    if res.status_code != 200:
        raise AuthError("Unable to login")

    return s


def submit(
        s: requests.Session,
        problem_path,
        source_file,
        langs: Languages) -> int:
    with open(os.path.expanduser(source_file), 'r') as f:
        source = f.read()

    file_name = Path(source_file).name
    lang = langs.get_lang(source_file)

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


@overload
def fetch_prob(s: requests.Session,
               path: str) -> tuple[str,
                                   list[Sample]]: ...


@overload
def fetch_prob(s: requests.Session,
               path: str,
               with_details: Literal[False]) -> tuple[str,
                                                      list[Sample]]: ...


@overload
def fetch_prob(s: requests.Session,
               path: str,
               with_details: Literal[True]) -> tuple[str,
                                                     list[Sample],
                                                     str,
                                                     str]: ...


def fetch_prob(s: requests.Session,
               path: str,
               with_details: bool = False) -> tuple[str,
                                                    list[Sample]] | tuple[str,
                                                                          list[Sample],
                                                                          str,
                                                                          str]:
    r = s.get(f"https://open.kattis.com{path}")
    soup = BeautifulSoup(r.text, features='lxml')
    if '404' in soup.find('title').text:
        raise ProblemNotFound("Problem not found")

    body = soup.find('div', {'class': 'problembody'})

    samples = [t.extract() for t in body.find_all(class_='sample')]
    _ = [s.tr.extract() for s in samples]

    # We will face error trying to extract samples of "interactive" problems
    try:
        samples = [Sample(input_=s.tr.td.extract().text,
                          output_=s.tr.td.extract().text) for s in samples]
    except Exception:
        return body.text.strip(), []

    for p in body.find_all('p'):
        p.replace_with(re.sub(r'\s+', ' ', p.text))

    if with_details:
        return body.text.strip(), samples, soup.find(
            'span', {
                'class': 'difficulty_number'}).text.strip(), soup.find(
            'h1', {
                'class': 'book-page-heading'}).text.strip()

    return body.text.strip(), samples


def get_result(s: requests.Session,
               submission_id: int) -> tuple[str, str, str]:
    r = s.get(f'https://open.kattis.com/submissions/{submission_id}')
    soup = BeautifulSoup(r.text, features='lxml')
    result = soup.find('div', class_='status').text
    time_taken = soup.find('td', {'data-type': 'cpu'}).text
    time_taken = unicodedata.normalize("NFKD", time_taken)
    test_cases = soup.find(
        'div', class_='horizontal_item').find_all(text=True)[0]
    return result, test_cases, time_taken


def download_samples(
        s: requests.Session,
        path: str,
        save_to=CACHE_DIR) -> None:
    shutil.rmtree(save_to)
    Path(save_to).mkdir(parents=True, exist_ok=True)
    sample_url: Final = urljoin(
        HOST, f"{path}/file/statement/samples.zip")
    r = s.get(sample_url, stream=True)

    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(save_to)
    except Exception:
        print("No samples")


FILTERS: Final[dict[str, str]] = {
    "untried": "f_untried",
    "partial": "f_partial-score",
    "tried": "f_tried",
    "solved": "f_solved"
}
ORDERS: Final[dict[str, str]] = {
    "difficulty_category": "difficulty_data",
    "subrat": 'submission_ratio',
    "name": 'title_link',
    "fastest": 'fastest_solution',
    "subtot": 'submissions',
    "subacc": 'accepted_submissions',
}


def get_probs(
        s: requests.Session,
        filters: list[str],
        ordering: str,
        page: int) -> list[Problem]:
    filter_params = [
        f"{q}={'off' if f in filters else 'on'}" for f,
        q in FILTERS.items()]
    ordering = ORDERS[re.sub(r'^[-+]', '', ordering)]
    order_params = [
        f'order={"-" if ordering.startswith("-") else ""}{ordering}']
    page_params = [f'page={page + 1}']
    query_param = "&".join([*order_params, *filter_params, *page_params])

    url: Final = urljoin(
        HOST, f"/problems?{query_param}")
    res = s.get(url)

    soup = BeautifulSoup(res.text, features='lxml')

    trs = list(soup.table.tbody.find_all('tr'))

    return [
        Problem(
            title=tr.td.text,
            path=tr.td.a['href'],
            difficulty=tr.find(
                'span',
                class_='difficulty_number').text) for tr in trs]
