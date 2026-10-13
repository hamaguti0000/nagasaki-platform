# 使い方: make fetch && make all && make test
# ライブラリは `pip install -r requirements.txt`(仮想環境を推奨)。このリポジトリの作業環境では .pylibs/ に入れてある。
PYTHON ?= python3
export PYTHONPATH := src:.pylibs:$(PYTHONPATH)
CLI = $(PYTHON) -m nagplat.cli

.PHONY: fetch verify-raw build validate map publish-list privacy-scan qc-report notice all test clean
fetch:        ; $(CLI) fetch
verify-raw:   ; $(CLI) verify-raw
build:        ; $(CLI) build
validate:     ; $(CLI) validate
map:          ; $(CLI) map
publish-list: ; $(CLI) publish-list
privacy-scan: ; $(CLI) privacy-scan
qc-report:    ; $(CLI) qc-report
notice:       ; $(CLI) notice
all:          ; $(CLI) all
test:         ; $(PYTHON) -m pytest -q tests
clean:        ; rm -rf warehouse data outputs work
