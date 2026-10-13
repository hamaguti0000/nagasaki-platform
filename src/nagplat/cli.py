"""コマンド: python -m nagplat.cli <fetch|verify-raw|build|validate|map|publish-list|privacy-scan|qc-report|notice|panel-eval|all>"""
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "help"
    if cmd == "fetch":
        from .fetch import fetch_all
        groups = set(argv[2:]) or None
        return 1 if fetch_all(groups) else 0
    if cmd == "verify-raw":
        from .fetch import verify_local
        p = verify_local()
        print("raw verify:", "OK" if not p else p)
        return 1 if p else 0
    if cmd == "build":
        from .build import build_all
        build_all()
        return 0
    if cmd == "validate":
        from .validate import run_validation
        return 0 if run_validation() else 1
    if cmd == "map":
        from .mapmaker import make_maps
        make_maps()
        return 0
    if cmd == "publish-list":
        from .publish_list import write_list
        rows = write_list()
        print("publish-list:", {k: sum(1 for r in rows if r["klass"] == k) for k in ("public", "review", "private")})
        return 0
    if cmd == "privacy-scan":
        from .privacy_scan import main as scan_main
        return scan_main()
    if cmd == "qc-report":
        from .qc_report import main as qc_main
        return qc_main()
    if cmd == "notice":
        from .notice import write
        write()
        print("notice: OK")
        return 0
    if cmd == "panel-eval":
        from .panel_report import main as pr_main
        return pr_main()
    if cmd == "all":
        from .build import build_all
        from .mapmaker import make_maps
        from .validate import run_validation
        from .panel_report import run as run_panel_eval
        build_all()
        ok = run_validation()
        if ok:
            run_panel_eval()
            make_maps()
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
