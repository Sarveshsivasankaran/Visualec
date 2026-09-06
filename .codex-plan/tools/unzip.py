import sys
import zipfile


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "-Z1":
        with zipfile.ZipFile(sys.argv[2]) as archive:
            sys.stdout.write("\n".join(archive.namelist()))
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "-p":
        with zipfile.ZipFile(sys.argv[2]) as archive:
            sys.stdout.buffer.write(archive.read(sys.argv[3]))
        return 0
    sys.stderr.write("Supported forms: unzip -Z1 file.pptx | unzip -p file.pptx entry\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
