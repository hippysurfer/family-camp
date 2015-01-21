#!/bin/bash

# 7th Lichfield Family Camp
#
# This script calls the two python scripts that process the bookings and generate
# the invoices.
#
# This script jumps through lots of hoops to ensure that it only ever runs one copy
# of itself.
#

#
# Set defensive shell options
#
set -e    # exit is a not trival command fails (use || : if it is OK for it to fail).
set -u    # treat unset variables as an error. (you have have to surround some contructs with
          # set +u; set -u if you need to deal with unset variables.

# Force running to the correct location.
cd /home/rjt/family_camp
source ../scout_records/py/bin/active

#
# Defaults. These can be overidden in calling scripts.
#
LIBRARYDIR=${FAM_LIBS:-"."}
LOCKDIR=${LOCKDIR:-"."}                        # Path to directory where the lock 
                                                       # files are stored.
LOCKFILE=${LOCKFILE:-"fam_concurrency_lock.pid"}      # Name of primary lockfile.
LOCKFILE_PRE=${LOCKFILE_PRE:-"fam_concurrency_lock"}  # Leading name for temp lock files.
MAX_RUNTIME=${MAX_RUNTIME:-60}                         # Number of mins.
DEBUG=${DEBUG:-false}                                  # Set default debug state to off.
LOGOUT=true
DEBUG=true

#
# Globals.
#
PID=$$                                                 # The process id of the current process.
TMP_LOCK_PATH="${LOCKDIR}/${LOCKFILE_PRE}_${PID}"      # Full path for process specific lockfile
LOCKFILE_PATH="${LOCKDIR}/${LOCKFILE}"                 # Full path for main lockfile.

#
# Error codes.
#
ERROR_LOCKDIR_NOT_A_DIR=1
ERROR_FAILED_TO_CREATE_LOCKDIR=2
ERROR_FAILED_TO_CREATE_TMP_LOCK_FILE=3
ERROR_FAILED_TO_ACQUIRE_LOCK=4

#
# Import library functions.
#
. "${LIBRARYDIR}/fam-functions.sh"

#
# Attemp to aquire the lock.
#
# Returns:
#
#    0 (Success) if the lock is acquired.
#    Error code on failure (see above for error codes).
#
acquire_lock() {
    #
    # Install the signal handler to ensure that all files are
    # removed if the process terminates.
    #
    trap _on_exit 0

    # Check that the lock file directory exists.
    if [ -e "${LOCKDIR}" -a ! -d "${LOCKDIR}" ]
    then
        # The path exists but is not a directory. This is fatal.
        return ${ERROR_LOCKDIR_NOT_A_DIR}
    fi
    
    if [ ! -e "${LOCKDIR}" ]
    then
        # Lock directory does not exist, so attempt to create it.
        mkdir -p "${LOCKDIR}" || return ${ERROR_FAILED_TO_CREATE_LOCKDIR}
    fi
    
    # Write the pid of the current process into a temporary lockfile.
    printf "${PID}" > "${TMP_LOCK_PATH}" || return ${ERROR_FAILED_TO_CREATE_TMP_LOCK_FILE}

    # Attempt to acquire the lock.
    if _get_lock
    then
        debug "Acquired lock for PID=${PID}."
        return 0
    fi

    #
    # Read the PID from the lock file and check to see whether the process is still running.
    #
    local old_pid=$(cat "${LOCKFILE_PATH}")
    if [ ! -e "/proc/${old_pid}" ]
    then
        # If the old_pid is not in /proc we can be sure that the 
        # process is no longer running.
        
        # Force the lock to be acquired.
        if _get_lock 1
        then
            debug "Forced lock: old_pid=${old_pid}, new_pid=${PID}"
            return 0
        fi
    fi

    #
    # The process is still running, so we check to see if it has been running
    # for longer than the allowed time.
    #
    local now=$(date  +"%s")                                      # Get the current time in secs since
                                                                  # the epoch.
    local process_modtime=$(date -r /proc/${old_pid} +"%s")       # Get the process runtime in secs from 
                                                                  # the epoch.
    local process_runtime=$(( ( $now - $process_modtime ) / 60 )) # Calculate the process runtime in mins

    debug "Checking for process runtime: now=${now} secs, "
    debug "   process_modtime(${old_pid})=${process_modtime}, "
    debug "   process_runtime(${old_pid})=${process_runtime}, "
    debug "   ${MAX_RUNTIME}" -lt "${process_runtime}"
    if [ "${MAX_RUNTIME}" -lt "${process_runtime}" ]
    then
        debug "old_pid=${old_pid} has exceeded MAX_RUNTIME=${MAX_RUNTIME} mins - killing..."

        # If a process has been running for longer than the MAX_RUNTIME it is 
        # an indication that something has gone wrong. So we send a message to the
        # logger to help with understanding the issue.
        [ -e "/proc/${old_pid}" ] && {
            local cmd="$( (/bin/ls -l /proc/${old_pid}/exe | /bin/cut -d'>' -f 2) 2>/dev/null)"
            local cmdline="$(/bin/cat /proc/${old_pid}/cmdline 2>/dev/null)"
            warn "Killing process because it is been running for too long (${process_runtime}). (${cmd}  ${cmdline})" || :
        }
       
        # Attempt to kill the process nicely first.
        [ -e "/proc/${old_pid}" ] && {
            kill "${old_pid}" && sleep 1
        }

        # If the process did not die, attempt to kill it with a SIG_TERM.
        [ -e "/proc/${old_pid}" ] && {
            debug "old_pid=${old_pid} did not respond to SIGTERM, trying SIGKILL..."
            kill -9 "${old_pid}" && sleep 1
        }

        [ -e "/proc/${old_pid}" ] && debug "old_pid=${old_pid} did not respond to SIGKILL."
        
        # Force the aquisition of the lock.
        
        if _get_lock 1
        then
            debug "Lock aquired after attempting to kill old_pid=${old_pid}."
            return 0
        fi
    fi

    return ${ERROR_FAILED_TO_ACQUIRE_LOCK}
}

#
# Release the lockfile
#
release_lock()
{
    if [ -e "${LOCKFILE_PATH}" ]
    then
        /bin/rm -f "${LOCKFILE_PATH}" || :
    fi

    # Remove signal handler.
    trap - 0
}

#
# Actually grab the lock.
#
# params:
#
#  $1 - if '1' the lock will be forced. (defaults to 0)
#
_get_lock()
{
    local ln_opts=""

    if [ $# -eq 1 ]
    then
        if [ $1 -eq 1 ]
        then
            ln_opts="--force"
        fi
    fi

    # Attempt to acquire the lock.
    ln ${ln_opts} "${TMP_LOCK_PATH}" "${LOCKFILE_PATH}" > /dev/null 2>&1
    local lnret=$?
    if [ ${lnret} -eq 0 ]
    then
        # We have successfully acquired the lock.

        # Remove the temporary process lockfile.
        /bin/rm -f "${TMP_LOCK_PATH}"

        debug "Lock aquired for ${PID}."
        return 0
    fi

    debug "Failed to acquire lock for ${PID}, ln exit status: ${lnret}"
    
    return ${ERROR_FAILED_TO_ACQUIRE_LOCK}
}

#
# Exit signal handler.
#
_on_exit()
{
    # If our temporary lockfile exists, remove it.
    if [ -e "${TMP_LOCK_PATH}" ]
    then
        /bin/rm -f "${TMP_LOCK_PATH}" || :
    fi

    # Check to see if we own the current main lockfile and remove it
    # if we do. 
    # 
    # NOTE: there is a minor problem with this, it is possible that another
    # process will acquire the lock between us checking the content of the 
    # lockfile and then removing it. This is unlikely because our process
    # would have to have been running for more than the PROCESS_TIMEOUT 
    # threshold. The consequence of this situation occuring is very minimal.
    # It might result in two jobs running at the same time, but only once 
    # and we do not think that this will cause an issue anyway.
    if [ -e "${LOCKFILE_PATH}" ]
    then 
        if [ "X${PID}X" = "X$(cat "${LOCKFILE_PATH}")X" ]
        then
            # The lockfile is for our process, so we must remove it.
            /bin/rm -f "${LOCKFILE_PATH}" || :
        fi
    fi
}


if ! acquire_lock
then 
   printf "Failed to aquire the lock.\n" >&2
   exit 1
fi

# Main script
(python process_fam_bookings.py --debug && python ./gen_invoices.py) >> process_all.log

if ! release_lock
then
   printf "Failed to release the lock.\n" >&2
fi
