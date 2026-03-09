#!/bin/sh
# LogFalcon boot LED heartbeat — slow pulse while the Pi is starting up.
# Stopped automatically when logfalcon-web.service becomes active.

LED="/sys/class/leds/led0"
TRIGGER="$LED/trigger"
BRIGHTNESS="$LED/brightness"

# Take control of the ACT LED
echo none > "$TRIGGER" 2>/dev/null

cleanup() {
    echo 0 > "$BRIGHTNESS" 2>/dev/null
    echo mmc0 > "$TRIGGER" 2>/dev/null
    exit 0
}
trap cleanup TERM INT

# Slow heartbeat: 1s on / 1s off
while true; do
    echo 1 > "$BRIGHTNESS"
    sleep 1
    echo 0 > "$BRIGHTNESS"
    sleep 1
done
