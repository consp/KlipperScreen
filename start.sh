#!/bin/sh
PYTHON=/root/printer_software/KlipperScreen/KlipperScreen-env/bin/python3
VENV=/root/printer_software/KlipperScreen/KlipperScreen-env/bin/activate
KLIPPERSCREEN=/root/printer_software/KlipperScreen/screen.py
KLIPPERSCREEN_DIR=/root/printer_software/KlipperScreen
KLIPPERSCREEN_CONFIG=/root/printer_data/config/KlipperScreen.conf
KLIPPERSCREEN_LOGFILE=/var/log/KlipperScreen.log
PID_FILE=/run/klipperscreen.pid

export DISPLAY=:0.0
export LANG=en_US.UTF8
export LC_ALL=en_US.UTF8

cd $KLIPPERSCREEN_DIR

source $VENV

while true;
do
    if ! $PYTHON $KLIPPERSCREEN --logfile $KLIPPERSCREEN_LOGFILE --config $KLIPPERSCREEN_CONFIG; then
        echo "Klipperscreen exited with an error, pleach check the logs"
        exit 1
    fi
done
