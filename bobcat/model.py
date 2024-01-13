from dataclasses import dataclass


@dataclass
class Sample:
    input_: str
    output_: str


@dataclass
class Problem:
    title: str
    path: str
    difficulty: str


@dataclass
class ConcreteProblem(Problem):
    description: str
    samples: list[Sample]


@dataclass
class SearchProblem:
    title: str
    path: str
