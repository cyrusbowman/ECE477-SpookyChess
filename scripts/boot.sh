#!/bin/sh -e
#
# boot.sh
#
# This script is executed at the end of each multiuser runlevel.
# Make sure that the script will "exit 0" on success or any other
# value on error.
#
# In order to enable or disable this script just change the execution
# bits.
#

# Print the IP address
sleep 10
_IP=$(hostname -I) || true
if [ "$_IP" ]; then
  echo "$_IP" | mail -s "Raspberry Pi Booted" 2609085550@mms.att.net
fi

