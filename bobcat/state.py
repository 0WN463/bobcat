from dataclasses import dataclass
from requests import Session

from . import model


@dataclass
class State:
    session: Session
    problems: list[model.Problem | model.ConcreteProblem]
    index: int
    curr_prob: model.ConcreteProblem
    page: int

    def __str__(self):
        return f"{len(self.problems)} problems. index: {self.index}. page: {self.page}. prob: {self.curr_prob.path}"

    def with_index(self, idx: int):
        return State(self.session, self.problems, idx, self.problems[idx], self.page)
