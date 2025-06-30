#!/bin/bash
echo "get_battery" | socat - UNIX-CONNECT:/tmp/mechaship_service.sock
