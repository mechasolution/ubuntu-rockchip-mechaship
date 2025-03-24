#!/bin/bash

set -eE 
trap 'echo Error: in $0 on line $LINENO' ERR

if [ "$(id -u)" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

cd "$(dirname -- "$(readlink -f -- "$0")")" && cd ..
mkdir -p build && cd build

if [[ -z ${BOARD} ]]; then
    echo "Error: BOARD is not set"
    exit 1
fi

# shellcheck source=/dev/null
source "../config/boards/${BOARD}.sh"

if [[ -z ${SUITE} ]]; then
    echo "Error: SUITE is not set"
    exit 1
fi

# shellcheck source=/dev/null
source "../config/suites/${SUITE}.sh"

if [[ -z ${FLAVOR} ]]; then
    echo "Error: FLAVOR is not set"
    exit 1
fi

# shellcheck source=/dev/null
source "../config/flavors/${FLAVOR}.sh"

if [[ ${LAUNCHPAD} != "Y" ]]; then
    uboot_package="$(basename "$(find u-boot-"${BOARD}"_*.deb | sort | tail -n1)")"
    if [ ! -e "$uboot_package" ]; then
        echo 'Error: could not find the u-boot package'
        exit 1
    fi

    linux_image_package="$(basename "$(find linux-image-*.deb | sort | tail -n1)")"
    if [ ! -e "$linux_image_package" ]; then
        echo "Error: could not find the linux image package"
        exit 1
    fi

    linux_headers_package="$(basename "$(find linux-headers-*.deb | sort | tail -n1)")"
    if [ ! -e "$linux_headers_package" ]; then
        echo "Error: could not find the linux headers package"
        exit 1
    fi

    linux_modules_package="$(basename "$(find linux-modules-*.deb | sort | tail -n1)")"
    if [ ! -e "$linux_modules_package" ]; then
        echo "Error: could not find the linux modules package"
        exit 1
    fi

    linux_buildinfo_package="$(basename "$(find linux-buildinfo-*.deb | sort | tail -n1)")"
    if [ ! -e "$linux_buildinfo_package" ]; then
        echo "Error: could not find the linux buildinfo package"
        exit 1
    fi

    linux_rockchip_headers_package="$(basename "$(find linux-rockchip-headers-*.deb | sort | tail -n1)")"
    if [ ! -e "$linux_rockchip_headers_package" ]; then
        echo "Error: could not find the linux rockchip headers package"
        exit 1
    fi
fi

setup_mountpoint() {
    local mountpoint="$1"

    if [ ! -c /dev/mem ]; then
        mknod -m 660 /dev/mem c 1 1
        chown root:kmem /dev/mem
    fi

    mount dev-live -t devtmpfs "$mountpoint/dev"
    mount devpts-live -t devpts -o nodev,nosuid "$mountpoint/dev/pts"
    mount proc-live -t proc "$mountpoint/proc"
    mount sysfs-live -t sysfs "$mountpoint/sys"
    mount securityfs -t securityfs "$mountpoint/sys/kernel/security"
    # Provide more up to date apparmor features, matching target kernel
    # cgroup2 mount for LP: 1944004
    mount -t cgroup2 none "$mountpoint/sys/fs/cgroup"
    mount -t tmpfs none "$mountpoint/tmp"
    mount -t tmpfs none "$mountpoint/var/lib/apt/lists"
    mount -t tmpfs none "$mountpoint/var/cache/apt"
    mv "$mountpoint/etc/resolv.conf" resolv.conf.tmp
    cp /etc/resolv.conf "$mountpoint/etc/resolv.conf"
    mv "$mountpoint/etc/nsswitch.conf" nsswitch.conf.tmp
    sed 's/systemd//g' nsswitch.conf.tmp > "$mountpoint/etc/nsswitch.conf"
}

teardown_mountpoint() {
    # Reverse the operations from setup_mountpoint
    local mountpoint
    mountpoint=$(realpath "$1")

    # ensure we have exactly one trailing slash, and escape all slashes for awk
    mountpoint_match=$(echo "$mountpoint" | sed -e's,/$,,; s,/,\\/,g;')'\/'
    # sort -r ensures that deeper mountpoints are unmounted first
    awk </proc/self/mounts "\$2 ~ /$mountpoint_match/ { print \$2 }" | LC_ALL=C sort -r | while IFS= read -r submount; do
        mount --make-private "$submount"
        umount "$submount"
    done
    mv resolv.conf.tmp "$mountpoint/etc/resolv.conf"
    mv nsswitch.conf.tmp "$mountpoint/etc/nsswitch.conf"
}

# Prevent dpkg interactive dialogues
export DEBIAN_FRONTEND=noninteractive

# Override localisation settings to address a perl warning
export LC_ALL=C

# Debootstrap options
chroot_dir=rootfs
overlay_dir=../overlay

# Mount the root filesystem
set +e
setup_mountpoint $chroot_dir

chroot $chroot_dir /bin/bash < /dev/tty > /dev/tty 2>&1

# clean apt
chroot ${chroot_dir} apt-get -y clean
chroot ${chroot_dir} apt-get -y autoclean
chroot ${chroot_dir} apt-get -y autoremove

# Umount the root filesystem
teardown_mountpoint $chroot_dir
