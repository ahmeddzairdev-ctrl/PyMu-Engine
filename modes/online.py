"""
Online versus mode — wraps Fight with NetworkManager for P2P netplay.
Uses delay-based netcode with optional rollback (see engine/network.py).
"""

from typing import Dict, Any, Optional
from engine.core import StateHandler, GameTime, GameState
from engine.renderer import Renderer
from engine.network import NetworkManager, NetState


class OnlineMode(StateHandler):

    def __init__(self, content_manager):
        super().__init__()
        self.content_manager = content_manager
        self._fight   = None
        self._network = NetworkManager()
        self._frame: int = 0

    # ------------------------------------------------------------------

    def on_enter(self, data: Dict[str, Any]) -> None:
        p1_info  = data.get("p1_character")
        stage_info = data.get("stage")
        host     = data.get("host")        # None → we are the host
        address  = data.get("address", "")
        port     = data.get("port", 7500)

        if p1_info is None:
            self.engine.change_state(GameState.MAIN_MENU)
            return

        p1 = self._load_char(p1_info)
        if p1 is None:
            self.engine.change_state(GameState.MAIN_MENU)
            return

        # Wire up network callbacks
        self._network.on_connected    = self._on_connected
        self._network.on_disconnected = self._on_disconnected

        if host:
            self._network.join(address, port)
        else:
            self._network.host(port)

        # Use a placeholder P2 until we know who the remote chose
        p2_infos = self.content_manager.get_character_list()
        p2_info  = p2_infos[0] if p2_infos else p1_info
        p2 = self._load_char(p2_info)
        if p2 is None:
            p2 = p1   # Last resort

        stage = self._load_stage(stage_info) or self._make_dummy_stage()

        from game.fight import Fight
        self._fight = Fight(p1, p2, stage)
        self._frame = 0

    def on_exit(self) -> None:
        self._network.disconnect()
        self._fight = None

    # ------------------------------------------------------------------

    def update(self, time: GameTime) -> None:
        if self._fight is None:
            return

        # Update network
        self._network.update()

        # Check for loss of connection
        if self._network.state == NetState.DISCONNECTED:
            print("OnlineMode: disconnected — returning to menu")
            self.engine.change_state(GameState.MAIN_MENU)
            return

        # Only advance logic when connected
        if self._network.state != NetState.CONNECTED:
            return

        self._frame += 1
        delay = self._network.input_delay

        # Send local input with delay
        p1_input = self.engine.input_handler.get_player(0)
        self._network.send_input(self._frame + delay, p1_input.current)

        # Retrieve remote input (with prediction)
        remote_frame = self._network.get_remote_input(self._frame)
        if remote_frame is None:
            return

        self._fight.update(p1_input, self._wrap_remote(remote_frame))

        # Desync detection
        if self._network.check_desync(self._frame - 1):
            print("OnlineMode: desync detected!")

        from game.fight import FightState
        if self._fight.state == FightState.MATCH_END:
            self.engine.change_state(GameState.MAIN_MENU)

    def render(self, renderer: Renderer) -> None:
        if self._fight:
            self._fight.render(renderer)

        # Show connection stats overlay
        if self._network.state == NetState.CONNECTED:
            renderer.draw_text(
                f"Ping: {self._network.stats.ping_ms:.0f}ms",
                4, 4, color=(255, 255, 0), size=12,
            )

    # ------------------------------------------------------------------

    def _on_connected(self) -> None:
        print("OnlineMode: connected!")

    def _on_disconnected(self) -> None:
        print("OnlineMode: remote disconnected")
        if self.engine:
            self.engine.change_state(GameState.MAIN_MENU)

    # ------------------------------------------------------------------

    @staticmethod
    def _wrap_remote(input_frame):
        """Wrap a raw InputFrame so Fight can use it via the PlayerInput interface."""
        from engine.input_handler import Button

        class _RemoteInput:
            def __init__(self, frame):
                self.current = frame
            def button_held(self, b):    return bool(self.current.buttons & b)
            def button_pressed(self, b): return bool(self.current.buttons_pressed & b)
            def button_released(self, b): return bool(self.current.buttons_released & b)
            def command_active(self, n): return False

        return _RemoteInput(input_frame)

    def _load_char(self, info: Dict[str, Any]):
        loader = self.content_manager.load_character(info["path"])
        if loader is None:
            return None
        from game.character import Character
        return Character(loader)

    def _load_stage(self, info: Optional[Dict[str, Any]]):
        if info is None:
            return None
        try:
            from mugen.stage_loader import StageLoader
            from game.stage import Stage
            return Stage(StageLoader.load(info["def"]))
        except Exception:
            return None

    @staticmethod
    def _make_dummy_stage():
        from unittest.mock import MagicMock
        s = MagicMock()
        s.bound_left  = -200
        s.bound_right = 200
        s.start_x     = 70
        s.render      = lambda *a: None
        s.render_foreground = lambda *a: None
        return s
