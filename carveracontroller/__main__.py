import os
import sys

if "--artifact-fs-worker" in sys.argv:
    from carveracontroller.machine.artifact_fs import worker_main

    worker_main()
    raise SystemExit(0)

import certifi

if getattr(sys, "frozen", False):
    os.environ["SSL_CERT_FILE"] = certifi.where()

from carveracontroller.main import main
from carveracontroller.translation import tr

if __name__ == "__main__":
    main()
