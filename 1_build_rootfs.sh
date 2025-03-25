#!/bin/bash

set -eE 
trap 'echo Error: in $0 on line $LINENO' ERR

cd "$(dirname -- "$(readlink -f -- "$0")")"

if [ "$(id -u)" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

cd "$(dirname -- "$(readlink -f -- "$0")")"

export BOARD=rock-5a
export SUITE=noble
export FLAVOR=server
export LAUNCHPAD=Y

if [ "${SUITE}" == "help" ]; then
    for file in config/suites/*; do
        basename "${file%.sh}"
    done
    exit 0
fi

if [ -n "${SUITE}" ]; then
    while :; do
        for file in config/suites/*; do
            if [ "${SUITE}" == "$(basename "${file%.sh}")" ]; then
                # shellcheck source=/dev/null
                source "${file}"
                break 2
            fi
        done
        echo "Error: \"${SUITE}\" is an unsupported suite"
        exit 1
    done
fi

if [ -n "${FLAVOR}" ]; then
    while :; do
        for file in config/flavors/*; do
            if [ "${FLAVOR}" == "$(basename "${file%.sh}")" ]; then
                # shellcheck source=/dev/null
                source "${file}"
                break 2
            fi
        done
        echo "Error: \"${FLAVOR}\" is an unsupported flavor"
        exit 1
    done
fi

if [ -n "${BOARD}" ]; then
    while :; do
        for file in config/boards/*; do
            if [ "${BOARD}" == "$(basename "${file%.sh}")" ]; then
                # shellcheck source=/dev/null
                source "${file}"
                break 2
            fi
        done
        echo "Error: \"${BOARD}\" is an unsupported board"
        exit 1
    done
fi

mkdir -p build/logs && exec > >(tee "build/logs/build-$(date +"%Y%m%d%H%M%S").log") 2>&1

# Create the root filesystem
./scripts/build-rootfs.sh

# 기존 패키지 설치 코드 실행
./scripts/config-image.sh

exit 0
