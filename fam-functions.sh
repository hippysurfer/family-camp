#
# Set default options. These can be overidden in calling scripts.
#
DEBUG=${DEBUG:-false}      # Set default debug state to off.
LOGTAG=${LOGTAG:-"$0"}     # String to use as 'tag' in syslog message.
LOGOUT=${LOGOUT:-false}    # Set to true to log to stderr and syslog.
LOGPRI=${LOGPRI:-"user"}   # String to use as log priority.

#
# Generate logger options from the options above.
#
log_opts () {
    local opts=""
    
    ( $LOGOUT ) && opts="-s" # log to stderr as well
 
    opts="${opts} -t ${LOGTAG}"

    printf "%s" "${opts}"
}

fatal () {
    logger -p "${LOGPRI}.crit" $(log_opts) "(FAM-ERROR) $*"
    exit 1
}

fatalaudit() {
	fatal "(FAM-AUDIT) $*"
}

log () {
    logger -p "${LOGPRI}.notice" $(log_opts) "$*"
}

audit () {
	log "(FAM-AUDIT) $*"
}

warn () {
    logger -p "${LOGPRI}.warn" $(log_opts) "(FAM-ERROR) $*"
}

warnaudit() {
	warn "(FAM-AUDIT) $*"
}

debug () {
    ( $DEBUG ) && logger -p "${LOGPRI}.debug" $(log_opts) "$*"
    return 0
}

debugaudit () {
	debug "(FAM-AUDIT) $*"
}

