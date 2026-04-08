"""
MUGEN trigger / expression parser.
Evaluates CNS trigger expressions such as:
  AnimTime = 0
  P2BodyDist X < 100
  Life < 100 && Power >= 3000
"""

import re
import operator
from typing import Any, Dict, Optional, Callable


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"(?P<float>[0-9]+\.[0-9]*|[0-9]*\.[0-9]+)"
    r"|(?P<int>[0-9]+)"
    r"|(?P<op>[<>!=&|+\-*/%^(),]+)"
    r"|(?P<id>[A-Za-z_][A-Za-z0-9_.]*)"
    r"|(?P<ws>\s+)"
)


def _tokenise(expr: str):
    tokens = []
    for m in _TOKEN_RE.finditer(expr):
        kind = m.lastgroup
        if kind == "ws":
            continue
        tokens.append((kind, m.group()))
    return tokens


# ---------------------------------------------------------------------------
# Simple recursive-descent evaluator
# ---------------------------------------------------------------------------

class ExpressionParser:
    """
    Evaluates a MUGEN trigger expression string.

    Usage::

        ctx = {"Life": 500, "Power": 1000, "AnimTime": 0}
        ep  = ExpressionParser(ctx)
        result = ep.eval("Life < 600 && Power >= 1000")
        # → True

    The *context* dict maps MUGEN variable names (case-insensitive) to their
    current values.  Variable lookups fall through to ``self.resolve(name)``,
    which subclasses can override.
    """

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context: Dict[str, Any] = {}
        if context:
            self.context = {k.lower(): v for k, v in context.items()}

        self._tokens: list = []
        self._pos: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def eval(self, expr: str) -> Any:
        """Parse and evaluate *expr*.  Returns a numeric or bool result."""
        self._tokens = _tokenise(expr)
        self._pos = 0
        try:
            return self._parse_or()
        except Exception:
            return 0

    def set_var(self, name: str, value: Any) -> None:
        self.context[name.lower()] = value

    def resolve(self, name: str) -> Any:
        """Look up a variable name; subclasses may override for game state."""
        return self.context.get(name.lower(), 0)

    # ------------------------------------------------------------------
    # Grammar  (simplified MUGEN subset)
    # ------------------------------------------------------------------
    # or      → and ('||' and)*
    # and     → cmp ('&&' cmp)*
    # cmp     → add (('<'|'<='|'>'|'>='|'='|'!='|'='') add)?
    # add     → mul (('+' | '-') mul)*
    # mul     → unary (('*' | '/' | '%') unary)*
    # unary   → ('-' | '!') unary | primary
    # primary → float | int | id ['(' args ')'] | '(' or ')'

    def _peek(self):
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self):
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _parse_or(self):
        left = self._parse_and()
        while self._peek() and self._peek()[1] == "||":
            self._consume()
            right = self._parse_and()
            left = int(bool(left) or bool(right))
        return left

    def _parse_and(self):
        left = self._parse_cmp()
        while self._peek() and self._peek()[1] == "&&":
            self._consume()
            right = self._parse_cmp()
            left = int(bool(left) and bool(right))
        return left

    _CMP_OPS: Dict[str, Callable] = {
        "<":  operator.lt,
        "<=": operator.le,
        ">":  operator.gt,
        ">=": operator.ge,
        "=":  operator.eq,
        "!=": operator.ne,
        "!=": operator.ne,
    }

    def _parse_cmp(self):
        left = self._parse_add()
        tok = self._peek()
        if tok and tok[1] in self._CMP_OPS:
            op = self._consume()[1]
            right = self._parse_add()
            return int(self._CMP_OPS[op](left, right))
        return left

    def _parse_add(self):
        left = self._parse_mul()
        while True:
            tok = self._peek()
            if tok and tok[1] in ("+", "-"):
                op = self._consume()[1]
                right = self._parse_mul()
                left = left + right if op == "+" else left - right
            else:
                break
        return left

    def _parse_mul(self):
        left = self._parse_unary()
        while True:
            tok = self._peek()
            if tok and tok[1] in ("*", "/", "%"):
                op = self._consume()[1]
                right = self._parse_unary()
                if op == "*":
                    left = left * right
                elif op == "/":
                    left = left / right if right != 0 else 0
                else:
                    left = left % right if right != 0 else 0
            else:
                break
        return left

    def _parse_unary(self):
        tok = self._peek()
        if tok:
            if tok[1] == "-":
                self._consume()
                return -self._parse_unary()
            if tok[1] == "!":
                self._consume()
                return int(not self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self):
        tok = self._peek()
        if tok is None:
            return 0

        if tok[0] == "float":
            self._consume()
            return float(tok[1])

        if tok[0] == "int":
            self._consume()
            return int(tok[1])

        if tok[0] == "id":
            self._consume()
            name = tok[1]
            # Function call?
            if self._peek() and self._peek()[1] == "(":
                self._consume()  # '('
                args = []
                while self._peek() and self._peek()[1] != ")":
                    args.append(self._parse_or())
                    if self._peek() and self._peek()[1] == ",":
                        self._consume()
                if self._peek():
                    self._consume()  # ')'
                return self._call_function(name, args)
            return self.resolve(name)

        if tok[1] == "(":
            self._consume()
            val = self._parse_or()
            if self._peek() and self._peek()[1] == ")":
                self._consume()
            return val

        # Unknown token — skip it
        self._consume()
        return 0

    def _call_function(self, name: str, args: list) -> Any:
        """Built-in MUGEN functions."""
        n = name.lower()
        if n == "abs" and args:
            return abs(args[0])
        if n == "max" and len(args) == 2:
            return max(args[0], args[1])
        if n == "min" and len(args) == 2:
            return min(args[0], args[1])
        if n == "floor" and args:
            return int(args[0])
        if n == "ceil" and args:
            import math
            return int(math.ceil(args[0]))
        # Unknown function → 0
        return 0
