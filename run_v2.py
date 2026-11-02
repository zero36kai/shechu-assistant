import sys


if __name__ == "__main__":
    if "--heartbeat" in sys.argv:
        from water_assistant.heartbeat import main
    else:
        from water_assistant.app import main
    raise SystemExit(main())
