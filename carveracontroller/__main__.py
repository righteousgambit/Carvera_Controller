import os
import sys

if "--headless-supervisor" in sys.argv:
    from carveracontroller.headless.__main__ import main as supervisor_main

    sys.argv.remove("--headless-supervisor")
    raise SystemExit(supervisor_main())

if "--artifact-fs-worker" in sys.argv:
    from carveracontroller.machine.artifact_fs_worker import worker_main

    worker_main()
    raise SystemExit(0)

import certifi

if getattr(sys, "frozen", False):
    os.environ["SSL_CERT_FILE"] = certifi.where()

from carveracontroller.main import main
from carveracontroller.translation import tr

if __name__ == "__main__":
    main()
