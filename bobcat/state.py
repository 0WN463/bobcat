from dataclasses import dataclass
from requests import Session

from . import model

@dataclass
class State:
    session: Session
    problems: list[model.Problem]
    index: int
    curr_prob: model.Problem

    def __str__(self):
        return f"{len(self.problems)} problems. index: {self.index}. prob: {self.curr_prob.path}"
