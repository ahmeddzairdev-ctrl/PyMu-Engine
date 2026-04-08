"""
MUGEN CNS state controller interpreter.
Executes StateController blocks loaded by CharacterLoader.
"""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from mugen.expression_parser import ExpressionParser

if TYPE_CHECKING:
    from game.character import Character


class StateControllerExecutor:
    """
    Evaluates and executes a single StateController dict for a character.

    Each controller has:
    - ``type``        : action to perform (ChangeState, VelSet, HitDef, …)
    - ``trigger_all`` : list of expressions that ALL must be true
    - ``triggers``    : dict of numbered trigger groups (any group can be true)
    - ``params``      : action-specific parameters
    """

    def __init__(self, character: "Character"):
        self.character = character
        self._parser = ExpressionParser()

    # ------------------------------------------------------------------

    def _build_context(self) -> Dict[str, Any]:
        """Build the variable context from the character's current state."""
        c = self.character
        return {
            "Life":         getattr(c, "life", 0),
            "LifeMax":      getattr(c, "max_life", 1000),
            "Power":        getattr(c, "power", 0),
            "PowerMax":     getattr(c, "max_power", 3000),
            "StateNo":      getattr(c, "state_no", 0),
            "PrevStateNo":  getattr(c, "prev_state_no", 0),
            "AnimTime":     getattr(c, "anim_time", 0),
            "AnimElem":     getattr(c, "anim_elem", 0),
            "Ctrl":         getattr(c, "ctrl", 1),
            "Time":         getattr(c, "state_time", 0),
            "MoveType":     0,  # simplified
            "1":            1,  # trigger1 = 1 means always
        }

    def _eval(self, expr: str, context: Dict[str, Any]) -> Any:
        self._parser.context = {k.lower(): v for k, v in context.items()}
        return self._parser.eval(expr)

    def _triggers_pass(self, controller: Any, context: Dict[str, Any]) -> bool:
        """Return True if the controller's triggers are satisfied."""
        # TriggerAll — every expression must be true
        for expr in controller.trigger_all:
            if not self._eval(expr, context):
                return False

        # Numbered triggers — at least one group must be fully true
        if not controller.triggers:
            return True

        for group_exprs in controller.triggers.values():
            if all(self._eval(e, context) for e in group_exprs):
                return True

        return False

    def execute(self, controller: Any) -> None:
        """Evaluate triggers and, if they pass, execute the controller."""
        context = self._build_context()

        if not self._triggers_pass(controller, context):
            return

        self._dispatch(controller, context)

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        ctype = ctrl.type.lower() if ctrl.type else ""
        handler = getattr(self, f"_do_{ctype}", self._do_unknown)
        handler(ctrl, ctx)

    def _do_unknown(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        pass   # Unimplemented controller — silently skip

    # ------------------------------------------------------------------
    # Core controllers
    # ------------------------------------------------------------------

    def _do_changestate(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        value = ctrl.params.get("value", "0")
        new_state = int(self._eval(str(value), ctx))
        self.character.change_state(new_state)

    def _do_velset(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        c = self.character
        vx, vy = c.velocity if hasattr(c, "velocity") else (0.0, 0.0)
        x_expr = ctrl.params.get("x")
        y_expr = ctrl.params.get("y")
        if x_expr:
            vx = float(self._eval(str(x_expr), ctx))
        if y_expr:
            vy = float(self._eval(str(y_expr), ctx))
        c.velocity = (vx, vy)

    def _do_veladd(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        c = self.character
        vx, vy = c.velocity if hasattr(c, "velocity") else (0.0, 0.0)
        x_expr = ctrl.params.get("x")
        y_expr = ctrl.params.get("y")
        if x_expr:
            vx += float(self._eval(str(x_expr), ctx))
        if y_expr:
            vy += float(self._eval(str(y_expr), ctx))
        c.velocity = (vx, vy)

    def _do_posset(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        c = self.character
        px, py = c.position if hasattr(c, "position") else (0.0, 0.0)
        x_expr = ctrl.params.get("x")
        y_expr = ctrl.params.get("y")
        if x_expr:
            px = float(self._eval(str(x_expr), ctx))
        if y_expr:
            py = float(self._eval(str(y_expr), ctx))
        c.position = (px, py)

    def _do_posadd(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        c = self.character
        px, py = c.position if hasattr(c, "position") else (0.0, 0.0)
        x_expr = ctrl.params.get("x")
        y_expr = ctrl.params.get("y")
        if x_expr:
            px += float(self._eval(str(x_expr), ctx))
        if y_expr:
            py += float(self._eval(str(y_expr), ctx))
        c.position = (px, py)

    def _do_ctrlset(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        val = ctrl.params.get("value", "1")
        self.character.ctrl = int(self._eval(str(val), ctx))

    def _do_poweradd(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        val = ctrl.params.get("value", "0")
        c = self.character
        c.power = min(getattr(c, "max_power", 3000),
                      getattr(c, "power", 0) + int(self._eval(str(val), ctx)))

    def _do_lifeadd(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        val = ctrl.params.get("value", "0")
        c = self.character
        c.life = max(0, min(getattr(c, "max_life", 1000),
                            getattr(c, "life", 0) + int(self._eval(str(val), ctx))))

    def _do_selfstate(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        self._do_changestate(ctrl, ctx)

    def _do_null(self, ctrl: Any, ctx: Dict[str, Any]) -> None:
        pass
