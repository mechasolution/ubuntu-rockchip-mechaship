#!/bin/bash
echo "get_battery" | socat - UNIX-CONNECT:/tmp/battery.sock
