"""Signal only a verified session belonging to this assistant task."""
import os
import signal
import sys

def main():
    pid=int(sys.argv[1]);owner=sys.argv[2]
    try:
        command=open(f'/proc/{pid}/cmdline','rb').read().replace(b'\0',b' ').decode(errors='replace')
        if owner not in command or os.getpgid(pid)!=pid:return 3
        os.killpg(pid,signal.SIGKILL if sys.argv[3]=='KILL' else signal.SIGINT)
    except ProcessLookupError:return 0
    return 0

if __name__=='__main__':raise SystemExit(main())
