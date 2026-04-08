"""
PyMugen Engine - Main entry point.
A MUGEN-compatible 2D fighting game engine written in Python.
"""

import sys
import argparse

from config import CONFIG
from engine.core import Engine, GameState


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="PyMugen - A MUGEN-compatible fighting game engine"
    )
    
    parser.add_argument(
        '-f', '--fullscreen',
        action='store_true',
        help='Start in fullscreen mode'
    )
    
    parser.add_argument(
        '-w', '--windowed',
        action='store_true',
        help='Start in windowed mode'
    )
    
    parser.add_argument(
        '-r', '--resolution',
        type=str,
        default=None,
        help='Screen resolution (e.g., 1280x720)'
    )
    
    parser.add_argument(
        '--software',
        action='store_true',
        help='Force software rendering (no GPU required)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (show hitboxes, FPS, etc.)'
    )
    
    parser.add_argument(
        '-c', '--config',
        type=str,
        default='config.json',
        help='Path to configuration file'
    )
    
    return parser.parse_args()


def apply_args(args):
    """Apply command line arguments to configuration."""
    if args.fullscreen:
        CONFIG.video.fullscreen = True
    elif args.windowed:
        CONFIG.video.fullscreen = False
    
    if args.resolution:
        try:
            w, h = args.resolution.split('x')
            CONFIG.video.width = int(w)
            CONFIG.video.height = int(h)
        except ValueError:
            print(f"Invalid resolution format: {args.resolution}")
    
    if args.software:
        CONFIG.video.use_software_renderer = True
    
    if args.debug:
        CONFIG.video.show_fps = True


def setup_states(engine: Engine):
    """Set up all game state handlers."""
    from modes.arcade import ArcadeMode
    from modes.versus import VersusMode
    from modes.survival import SurvivalMode
    from modes.training import TrainingMode
    from modes.online import OnlineMode
    from ui.menu import MainMenuHandler, TitleHandler
    from ui.character_select import CharacterSelectHandler
    
    # Create content manager reference
    content_manager = engine.content_manager
    
    # Register state handlers
    engine.register_state_handler(GameState.TITLE, TitleHandler())
    engine.register_state_handler(GameState.MAIN_MENU, MainMenuHandler())
    engine.register_state_handler(GameState.CHARACTER_SELECT, CharacterSelectHandler(content_manager))
    
    # Game modes
    engine.register_state_handler(GameState.FIGHT, ArcadeMode(content_manager))


def main():
    """Main entry point."""
    print("=" * 50)
    print("PyMugen Engine v0.1.0")
    print("MUGEN-compatible 2D Fighting Game Engine")
    print("=" * 50)
    
    # Parse arguments
    args = parse_args()
    apply_args(args)
    
    # Load configuration
    try:
        CONFIG.load(args.config)
    except FileNotFoundError:
        print(f"Config file not found: {args.config}, using defaults")
    
    # Create and initialize engine
    engine = Engine()
    
    if not engine.init():
        print("Failed to initialize engine!")
        sys.exit(1)
    
    print(f"Resolution: {CONFIG.video.width}x{CONFIG.video.height}")
    print(f"Fullscreen: {CONFIG.video.fullscreen}")
    print(f"Software Rendering: {CONFIG.video.use_software_renderer}")
    
    # Scan for content
    print("\nScanning for MUGEN content...")
    char_count = len(engine.content_manager.get_character_list())
    stage_count = len(engine.content_manager.get_stage_list())
    print(f"Found {char_count} characters, {stage_count} stages")
    
    # Set up game states
    setup_states(engine)
    
    # Start at title screen
    engine.change_state(GameState.TITLE)
    
    print("\nStarting game loop...")
    print("Press ESC to quit\n")
    
    try:
        engine.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        engine.shutdown()
        print("Engine shut down cleanly")


if __name__ == '__main__':
    main()
