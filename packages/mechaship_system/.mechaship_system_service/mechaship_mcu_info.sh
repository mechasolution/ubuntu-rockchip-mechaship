#!/bin/bash
echo "get_mcu_info" | socat - UNIX-CONNECT:/tmp/mechaship_service.sock
