"""Post-build step: give the built exe its Chinese product name.

Lives in Python rather than in build_exe.bat because cmd.exe reads .bat files in
the OEM codepage (GBK here), so a non-ASCII filename inside the .bat would be
mis-decoded. Python source is UTF-8, so the name survives intact.
"""

import os
import shutil
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BUILT = os.path.join(APP_DIR, "dist", "SJTU-Assistant.exe")
FINAL = os.path.join(APP_DIR, "交大助手.exe")


def main():
    if not os.path.isfile(BUILT):
        print("[post-build] 未找到构建产物:", BUILT)
        return 1
    shutil.move(BUILT, FINAL)
    size = os.path.getsize(FINAL)
    print("[post-build] %s  %.2f MB" % (FINAL, size / 2 ** 20))
    return 0


if __name__ == "__main__":
    sys.exit(main())
