import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if getattr(sys, "frozen", False) and not args:
        args = ["--heartbeat", "--show"]
    if "--heartbeat" in args:
        from water_assistant.heartbeat import main as launch
    else:
        from water_assistant.app import main as launch
    return launch(args)


if __name__ == "__main__":
    raise SystemExit(main())
