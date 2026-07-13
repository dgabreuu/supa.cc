import sys
import tomllib
from pathlib import Path


def runtime_requirements():
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    with pyproject.open("rb") as stream:
        return tomllib.load(stream)["project"]["dependencies"]


def main():
    output = Path(sys.argv[1])
    output.write_text("\n".join(runtime_requirements()) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
