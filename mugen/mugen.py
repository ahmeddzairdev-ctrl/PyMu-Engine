"""
Core MUGEN data classes — ported from the original Python 2 mugen.py.

Changes from the original:
  - print statements → print() functions  (Python 3)
  - Division operator already safe (Python 3 defaults to true division)
  - math import added for ln()
  - Command, StateDef, Controller, World, Character updated with type hints
    and connected to the rest of the engine where appropriate.
"""

import math
from typing import Dict, List, Optional, Any


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class MugenException(Exception):
    pass


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command:
    def __init__(self):
        self.state:       Optional[str]  = None
        self.keys:        List[str]      = []
        self.time:        Optional[int]  = None
        self.bufferTime:  Optional[int]  = None


# ---------------------------------------------------------------------------
# StateDef
# ---------------------------------------------------------------------------

class StateDef:
    """
    Holds the parameters declared in a [Statedef] block and
    the relative procedure/controller states.
    """

    def __init__(self, player: 'Character', world: 'World'):
        self.stateNumber:        Optional[int]  = None
        self.player                             = player
        self.world                              = world
        self.stateType:          Optional[str]  = None
        self.moveType:           Optional[str]  = None
        self.physics:            Optional[str]  = None
        self.anim:               Optional[int]  = None
        self.velset:             Optional[Any]  = None
        self.ctrl:               Optional[int]  = None
        self.poweradd:           Optional[int]  = None
        self.juggle:             Optional[int]  = None
        self.facep2:             Optional[bool] = None
        self.hitdefpersist:      Optional[bool] = None
        self.movehitpersist:     Optional[bool] = None
        self.hitcountpersist:    Optional[bool] = None
        self.sprpriority:        Optional[int]  = None

    def getNumber(self) -> Optional[int]:
        return self.stateNumber

    def evaluate(self, world: 'World') -> None:
        pass


# ---------------------------------------------------------------------------
# Controller (base)
# ---------------------------------------------------------------------------

class Controller:
    def __init__(self):
        pass


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------

class World:
    def __init__(self):
        self.currentTime:   int            = 0
        self.endTime:       Optional[int]  = None
        self.currentRound:  int            = 1
        self.rounds:        Optional[int]  = None
        self.player1:       Optional['Character'] = None
        self.player2:       Optional['Character'] = None
        self.player3:       Optional['Character'] = None
        self.player4:       Optional['Character'] = None

    def getTime(self) -> int:
        return self.currentTime

    def getCurrentRound(self) -> int:
        return self.currentRound

    def isMatchOver(self) -> int:
        return 0

    def getPlayerBodyXDistance(self) -> float:
        if self.player1 and self.player2:
            return abs(self.player1.getPositionX() - self.player2.getPositionX())
        return 0.0

    def getPlayerBodyYDistance(self) -> float:
        if self.player1 and self.player2:
            return abs(self.player1.getPositionY() - self.player2.getPositionY())
        return 0.0

    def getPlayerXDistance(self) -> float:
        return self.getPlayerBodyXDistance()

    def getPlayerYDistance(self) -> float:
        return self.getPlayerBodyYDistance()


# ---------------------------------------------------------------------------
# Character
# ---------------------------------------------------------------------------

class Character:
    def __init__(self):
        # ---- From character definition file ----
        self.name:               Optional[str]  = None
        self.displayName:        Optional[str]  = None
        self.versionDate:        List           = []
        self.mugenVersion:       List           = []
        self.author:             Optional[str]  = None
        self.paletteDefaults:    List           = []
        self.cmdFile:            Optional[str]  = None
        self.stateFiles:         List[str]      = []
        self.spriteFile:         Optional[str]  = None
        self.animFile:           Optional[str]  = None
        self.soundFile:          Optional[str]  = None
        self.paletteFiles:       Dict           = {}
        self.introStoryboard:    Optional[str]  = None
        self.endingStoryboard:   Optional[str]  = None

        # ---- Defaults (cmd file) ----
        self.commandTime:        Optional[int]  = None
        self.commandBufferTime:  Optional[int]  = None

        # ---- Data (constants) ----
        self.life:               Optional[int]   = None
        self.attack:             Optional[int]   = None
        self.defence:            Optional[int]   = None
        self.fallDefenceUp:      Optional[int]   = None
        self.liedownTime:        Optional[int]   = None
        self.airjuggle:          Optional[int]   = None
        self.sparkno:            Optional[int]   = None
        self.guardSparkno:       Optional[int]   = None
        self.koEcho:             Optional[int]   = None
        self.volume:             Optional[int]   = None
        self.intPersistIndex:    Optional[int]   = None
        self.floatPersistIndex:  Optional[int]   = None

        # ---- Size (constants) ----
        self.xscale:             Optional[float] = None
        self.yscale:             Optional[float] = None
        self.groundBack:         Optional[int]   = None
        self.groundFront:        Optional[int]   = None
        self.airBack:            Optional[int]   = None
        self.airFront:           Optional[int]   = None
        self.height:             Optional[int]   = None
        self.attackDist:         Optional[int]   = None
        self.projAttackDist:     Optional[int]   = None
        self.projDoscale:        Optional[int]   = None
        self.headPos:            List            = []
        self.midPos:             List            = []
        self.shadowoffset:       Optional[int]   = None
        self.drawOffset:         List            = []

        # ---- Velocity (constants) ----
        self.walkFwd:            List[float]     = []
        self.walkBack:           List[float]     = []
        self.runFwd:             List[float]     = []
        self.runBack:            List[float]     = []
        self.jumpNeu:            List[float]     = []
        self.jumpBack:           List[float]     = []
        self.jumpFwd:            List[float]     = []
        self.runjumpBack:        List[float]     = []
        self.runjumpFwd:         List[float]     = []
        self.airjumpNeu:         List[float]     = []
        self.airjumpBack:        List[float]     = []
        self.airjumpFwd:         List[float]     = []

        # ---- Movement (constants) ----
        self.airjumpNum:         Optional[int]   = None
        self.airjumpHeight:      Optional[int]   = None
        self.yaccel:             Optional[float] = None
        self.standFriction:      Optional[float] = None
        self.crouchFriction:     Optional[float] = None

        # ---- Command holders ----
        self.commands:           Dict[str, Command] = {}
        self.currentCommand:     Optional[str]      = None

        # ---- State holders ----
        self.states:             Dict[int, Any]  = {}
        self.previousStateNumber: Optional[int]  = None
        self.currentState:       Optional[StateDef] = None

        # ---- Special states (-3, -2, -1) ----
        self.neg3State:          Optional[StateDef] = None
        self.neg2State:          Optional[StateDef] = None
        self.neg1State:          Optional[StateDef] = None

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def setName(self, name: str) -> None:
        self.name = name

    def addStateFile(self, stateFile: str) -> None:
        if stateFile not in self.stateFiles:
            self.stateFiles.append(stateFile)

    def addCommand(self, state: str, keys: List,
                   time: Optional[int] = None,
                   bufferTime: Optional[int] = None) -> None:
        cmd = Command()
        cmd.state      = state
        cmd.keys       = keys
        cmd.time       = time
        cmd.bufferTime = bufferTime
        self.commands[state] = cmd

    def addState(self, number: int, state: Any) -> None:
        self.states[number] = state

    def getState(self, number: int) -> Any:
        try:
            return self.states[number]
        except KeyError:
            raise MugenException(f"State {number} does not exist")

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def changeState(self, number: int, world: World) -> None:
        try:
            prev = self.currentState
            self.currentState = self.getState(number)(self, world)
            if prev:
                self.previousStateNumber = prev.getNumber()
            print(f"Changed to state {number}")
        except MugenException:
            print(f"State ({number}) does not exist")

    def listStates(self) -> None:
        print(", ".join(str(k) for k in sorted(self.states)))

    # ------------------------------------------------------------------
    # Command evaluation
    # ------------------------------------------------------------------

    def setCurrentCommand(self, command: str) -> None:
        self.currentCommand = command

    def evaluateCommand(self) -> Optional[str]:
        return self.currentCommand

    # ------------------------------------------------------------------
    # Per-tick action
    # ------------------------------------------------------------------

    def act(self, world: World) -> None:
        if self.neg3State:
            self.neg3State.evaluate(world)
        if self.neg2State:
            self.neg2State.evaluate(world)
        if self.neg1State:
            self.neg1State.evaluate(world)
        if self.currentState:
            self.currentState.evaluate(world)

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def getPreviousStateNumber(self) -> Optional[int]:
        return self.previousStateNumber

    def getStateNumber(self) -> Optional[int]:
        return self.currentState.getNumber() if self.currentState else None

    # ------------------------------------------------------------------
    # Stub methods (to be implemented by game.character.Character)
    # ------------------------------------------------------------------

    def animationElementTime(self, time: int) -> int:  return 1
    def canRecover(self) -> int:                        return 1
    def getAnimationTime(self) -> int:                  return 0
    def getBackEdgeBodyDistance(self) -> float:         return 0.0
    def getBackEdgeDistance(self) -> float:             return 0.0
    def getFrontEdgeBodyDistance(self) -> float:        return 0.0
    def getFrontEdgeDistance(self) -> float:            return 0.0
    def getHitFall(self) -> int:                        return 0
    def getHitOver(self) -> int:                        return 0
    def getHitShakeOver(self) -> int:                   return 0
    def getHitVariable(self, value: Any) -> int:        return 0
    def getMoveContact(self) -> int:                    return 0
    def getMoveGuarded(self) -> int:                    return 0
    def getMoveHit(self) -> int:                        return 0
    def getMoveType(self) -> int:                       return 0
    def getStateType(self) -> int:                      return 0
    def hasControl(self) -> int:                        return 0
    def roundsExisted(self) -> int:                     return 0
    def selfAnimExist(self, number: int) -> int:        return 1
    def setAnimation(self, number: int, element: int) -> None: pass
    def currentAnimation(self) -> int:                  return 0
    def getPositionX(self) -> float:                    return 0.0
    def getPositionY(self) -> float:                    return 0.0
    def getSystemFloatVariable(self, number: int) -> float: return 0.0
    def getSystemVariable(self, number: int) -> int:    return 0
    def getVariable(self, number: int) -> int:          return 0
    def getVelocityX(self) -> float:                    return 0.0
    def getVelocityY(self) -> float:                    return 0.0
    def isAlive(self) -> int:                           return 1
    def turn(self) -> None:                             pass
    def setControl(self, trigger: Any) -> None:         pass


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def ln(number: float) -> float:
    """Natural logarithm (MUGEN trigger function)."""
    return math.log(number, math.e)
