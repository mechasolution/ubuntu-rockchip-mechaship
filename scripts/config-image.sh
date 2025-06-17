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

chroot_run() {
    chroot "${chroot_dir}" /bin/bash -c "$*"
}

chroot_run_ubuntu() {
    chroot --userspec=ubuntu:ubuntu "${chroot_dir}" env HOME=/home/ubuntu /bin/bash -c "cd ~ && $*"
}

# Prevent dpkg interactive dialogues
export DEBIAN_FRONTEND=noninteractive

# Override localisation settings to address a perl warning
export LC_ALL=C

# Debootstrap options
chroot_dir=rootfs
overlay_dir=../overlay

# Extract the compressed root filesystem
rm -rf ${chroot_dir} && mkdir -p ${chroot_dir}
tar -xpJf "mechaship-ubuntu-${RELASE_VERSION}-preinstalled-${FLAVOR}-arm64.rootfs.tar.xz" -C ${chroot_dir}

# Mount the root filesystem
setup_mountpoint $chroot_dir

# Change to local mirror & DNS server
chroot_run "sed -i 's|http://ppa.launchpad.net|http://krr.ppa.launchpad.net|g' /etc/apt/sources.list.d/extra-ppas.list"
chroot_run "sed -i 's|http://ports.ubuntu.com|http://krr.ports.ubuntu.com/ubuntu-ports|g' /etc/apt/sources.list.d/ubuntu.sources"
chroot_run "sed -i 's|^\(nameserver[[:space:]]*\).*|\1 192.168.1.11|' /etc/resolv.conf"

# Run config hook to handle board specific changes
if [[ $(type -t config_image_hook__"${BOARD}") == function ]]; then
    config_image_hook__"${BOARD}" "${chroot_dir}" "${overlay_dir}" "${SUITE}"
fi 

# Download and install U-Boot
if [[ ${LAUNCHPAD} == "Y" ]]; then
    chroot ${chroot_dir} apt-get -y install "u-boot-${BOARD}"
else
    cp "${uboot_package}" ${chroot_dir}/tmp/
    chroot ${chroot_dir} dpkg -i "/tmp/${uboot_package}"
    chroot ${chroot_dir} apt-mark hold "$(echo "${uboot_package}" | sed -rn 's/(.*)_[[:digit:]].*/\1/p')"

    cp "${linux_image_package}" "${linux_headers_package}" "${linux_modules_package}" "${linux_buildinfo_package}" "${linux_rockchip_headers_package}" ${chroot_dir}/tmp/
    chroot ${chroot_dir} /bin/bash -c "apt-get -y purge \$(dpkg --list | grep -Ei 'linux-image|linux-headers|linux-modules|linux-rockchip' | awk '{ print \$2 }')"
    chroot ${chroot_dir} /bin/bash -c "dpkg -i /tmp/{${linux_image_package},${linux_modules_package},${linux_buildinfo_package},${linux_rockchip_headers_package}}"
    chroot ${chroot_dir} apt-mark hold "$(echo "${linux_image_package}" | sed -rn 's/(.*)_[[:digit:]].*/\1/p')"
    chroot ${chroot_dir} apt-mark hold "$(echo "${linux_modules_package}" | sed -rn 's/(.*)_[[:digit:]].*/\1/p')"
    chroot ${chroot_dir} apt-mark hold "$(echo "${linux_buildinfo_package}" | sed -rn 's/(.*)_[[:digit:]].*/\1/p')"
    chroot ${chroot_dir} apt-mark hold "$(echo "${linux_rockchip_headers_package}" | sed -rn 's/(.*)_[[:digit:]].*/\1/p')"
fi

# Update the initramfs
chroot ${chroot_dir} update-initramfs -u

# create user & do not create user on cloud-init
chroot_run "adduser --gecos ",,," --disabled-password ubuntu"
chroot_run "sh -c 'echo "ubuntu:ubuntu" | chpasswd'"
chroot_run "usermod -aG sudo,dialout ubuntu"
chroot_run "echo \"ubuntu ALL=(ALL) NOPASSWD: ALL\" >> /etc/sudoers"
echo '#cloud-config
system_info:
  default_user: {}' >> ${chroot_dir}/etc/cloud/cloud.cfg.d/91-disable-default-user.cfg
chroot_run_ubuntu "mkdir temp"

# add default wifi ap to connect
echo '
write_files:
- path: /etc/cloud/cloud.cfg.d/99-custom-networking.cfg
  permissions: '0644'
  content: |
    network: {config: disabled}
- path: /etc/netplan/my-new-config.yaml
  permissions: '0644'
  content: |
    network:
      version: 2
      renderer: NetworkManager
      ethernets:
        zz-all-en:
          match:
            name: "en*"
          optional: true
          dhcp4: true
        zz-all-eth:
          match:
            name: "eth*"
          optional: true
          dhcp4: true
      wifis:
        zz-all-wifi:
          match:
            name: "wl*"
          dhcp4: true
          dhcp6: true
          access-points:
            "mechasolution_5":
              auth:
                key-management: "psk"
                password: "mechaship@123"
            "iptime-Tech_5":
              auth:
                key-management: "psk"
                password: "mecha@123"

runcmd:
 - rm /etc/netplan/50-cloud-init.yaml
 - netplan generate
 - netplan apply' >> ${chroot_dir}/etc/cloud/cloud.cfg

# Update packages, 네트워크 툴 설치
chroot_run "apt-get update"
chroot_run "apt-get install net-tools network-manager -y"

# chroot $chroot_dir apt-get -y upgrade

# Install apt-fast
chroot_run "/bin/bash -c '$(curl -sL https://git.io/vokNn)'"

# ROS2 Jazzy
echo '#!/bin/bash
set -e
DEBIAN_FRONTEND=noninteractive

sudo apt-get install software-properties-common curl -y
sudo add-apt-repository -y universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://krr.packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update
sudo apt-get install ros-jazzy-ros-base ros-dev-tools python3-pip -y
python3 -m pip config set global.break-system-packages true # Disable externally-managed-environment error
pip install setuptools==70.0.0
mkdir -p ~/ros2_ws/src && cd ~/ros2_ws
colcon build
cd
sudo rosdep init
rosdep update
' >> ${chroot_dir}/home/ubuntu/temp/install_ros2_jazzy.sh
chmod 777 ${chroot_dir}/home/ubuntu/temp/install_ros2_jazzy.sh
chroot_run_ubuntu "./temp/install_ros2_jazzy.sh"

# 환경변수
echo 'source /opt/ros/jazzy/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
source /home/ubuntu/uros_ws/install/local_setup.bash

# export ROS_DOMAIN_ID=0 # moved to ament_environment_hooks; do not set domain id here (mechaship_bringup/hooks/mechaship_bringup.sh.in)

alias cb="cd ~/ros2_ws && colcon build --symlink-install && source ~/ros2_ws/install/local_setup.bash"' >> ${chroot_dir}/home/ubuntu/ros2_setup.bash
echo "source ~/ros2_setup.bash" >> ${chroot_dir}/home/ubuntu/.bashrc
chroot_run "chown ubuntu:ubuntu /home/ubuntu/ros2_setup.bash"

# uROS
echo '#!/bin/bash
source ~/ros2_setup.bash
DEBIAN_FRONTEND=noninteractive
set -e

mkdir ~/uros_ws && cd ~/uros_ws
git clone -b $ROS_DISTRO https://github.com/micro-ROS/micro_ros_setup.git src/micro_ros_setup
rosdep install --from-paths src --ignore-src -y
colcon build
source install/local_setup.bash
ros2 run micro_ros_setup create_agent_ws.sh
ros2 run micro_ros_setup build_agent.sh
source install/local_setup.sh
' >> ${chroot_dir}/home/ubuntu/temp/install_uros.sh
chmod 777 ${chroot_dir}/home/ubuntu/temp/install_uros.sh
chroot_run_ubuntu "./temp/install_uros.sh"

# Udev
echo '# Main Circuit
KERNEL=="ttyACM*", ATTRS{interface}=="MechaShip Motherboard CDC", ATTRS{bInterfaceNumber}=="00", MODE="0666", GROUP="dialout", SYMLINK+="ttyUROS"
KERNEL=="ttyACM*", ATTRS{interface}=="MechaShip Motherboard CDC", ATTRS{bInterfaceNumber}=="02", MODE="0666", GROUP="dialout", SYMLINK+="ttyMCU"

# GNSS (GPS)
KERNEL=="ttyACM*", ATTRS{idVendor}=="1546", MODE="0666", GROUP="dialout", SYMLINK+="ttyGPS"

# LiDAR
KERNEL=="ttyUSB*", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", ATTRS{bcdDevice}=="0200", MODE="0666", GROUP="dialout", SUBSYSTEM=="tty",SYMLINK+="ttyLiDAR"

# IMU
KERNEL=="ttyUSB*", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", ATTRS{bcdDevice}=="8134", MODE="0666", GROUP="dialout", SUBSYSTEM=="tty",SYMLINK+="ttyIMU"

# Camera
KERNEL=="video*", ATTR{index}=="0", MODE="0666", SYMLINK+="videoRGBCAMERA0"
KERNEL=="video*", ATTR{index}=="1", MODE="0666", SYMLINK+="videoRGBCAMERA1"' | sudo tee ${chroot_dir}/etc/udev/rules.d/98-mechaship.rules > /dev/null

# ROS Dependency pkg
echo '#!/bin/bash
source ~/ros2_setup.bash
DEBIAN_FRONTEND=noninteractive
set -e

sudo apt-get install -y ros-jazzy-usb-cam ros-jazzy-robot-localization ros-jazzy-slam-toolbox ros-jazzy-vision-msgs ros-jazzy-cartographer ros-jazzy-cartographer-ros ros-jazzy-ros-gz ros-jazzy-cv-bridge ros-jazzy-ublox-gps
git clone https://github.com/YDLIDAR/YDLidar-SDK
cd YDLidar-SDK
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
git clone --recurse-submodules https://github.com/mechasolution/mechaship.git ~/ros2_ws/src/mechaship
cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -y --skip-keys=cmake_modules # TODO: remove skip-keys after fix rf2o_laser_odometry dependency problem
colcon build --symlink-install
' >> ${chroot_dir}/home/ubuntu/temp/install_ydlidar_driver.sh
chmod 777 ${chroot_dir}/home/ubuntu/temp/install_ydlidar_driver.sh
chroot_run_ubuntu "./temp/install_ydlidar_driver.sh"

# Service unit
mkdir -p ${chroot_dir}/home/ubuntu/.mechaship_system_service
cp ../packages/mechaship_system/mcu_service.py ${chroot_dir}/home/ubuntu/.mechaship_system_service/.

# battery custom command
cp ../packages/mechaship_system/mechaship_battery.sh ${chroot_dir}/home/ubuntu/.mechaship_system_service/.
chroot_run "apt-get install -y socat"
chroot_run "ln -s /home/ubuntu/.mechaship_system_service/mechaship_battery.sh /usr/local/bin/mechaship_battery"
chroot_run "chmod 755 /usr/local/bin/mechaship_battery"

echo '[Unit]
Description=Mechaship System
After=network.target

[Service]
WorkingDirectory=/home/ubuntu/.mechaship_system_service
ExecStart=/usr/bin/python3 mcu_service.py
RemainAfterExit=no
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=multi-user.target' | sudo tee ${chroot_dir}/etc/systemd/system/mechaship_system.service > /dev/null
chroot_run_ubuntu "sudo systemctl enable mechaship_system.service"

# RKNN
cp -r ../packages/rknn-toolkit2/rknn_toolkit_lite2-2.3.0-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl ${chroot_dir}/home/ubuntu/temp/.
cp -r ../packages/rknn-toolkit2/librknnrt.so ${chroot_dir}/home/ubuntu/temp/.
chroot_run "chown ubuntu:ubuntu -R /home/ubuntu/temp/*"
echo '#!/bin/bash
source ~/ros2_setup.bash
DEBIAN_FRONTEND=noninteractive
set -e

# git clone https://github.com/airockchip/rknn-toolkit2/
sudo apt-get install python3-dev python3-pip gcc python3-opencv python3-numpy -y
pip3 install ~/temp/rknn_toolkit_lite2-2.3.0-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
sudo cp ~/temp/librknnrt.so /usr/lib/.
' >> ${chroot_dir}/home/ubuntu/temp/install_rknn.sh
chmod 777 ${chroot_dir}/home/ubuntu/temp/install_rknn.sh
chroot_run_ubuntu "./temp/install_rknn.sh"

# Roll back local mirror
chroot_run "sed -i 's|http://krr.ppa.|http://ppa.|g' /etc/apt/sources.list.d/extra-ppas.list"
chroot_run "sed -i 's|http://krr.ports.ubuntu.com/ubuntu-ports|http://kr.ports.ubuntu.com|g' /etc/apt/sources.list.d/ubuntu.sources"
chroot_run "sed -i 's|http://krr.packages.ros.org/ros2/ubuntu|http://packages.ros.org/ros2/ubuntu|g' /etc/apt/sources.list.d/ros2.list"

# Remove packages
chroot_run "apt-get -y clean"
chroot_run "apt-get -y autoclean"
chroot_run "apt-get -y autoremove"
chroot_run "history -c"
chroot_run "history -w"
chroot_run_ubuntu "history -c"
chroot_run_ubuntu "history -w"

# Umount the root filesystem
teardown_mountpoint $chroot_dir
