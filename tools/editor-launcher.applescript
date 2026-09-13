-- Signalbox Editor launcher: starts the local editor server if needed, then opens it.
set startScript to POSIX path of (path to home folder) & "signalbox-start.sh"
set healthURL to "http://localhost:5001/api/health"
set isUp to (do shell script "curl -s -m 2 " & healthURL & " >/dev/null 2>&1 && echo yes || echo no")
if isUp is "no" then
	do shell script "nohup /bin/bash " & quoted form of startScript & " >> /tmp/signalbox-editor.log 2>&1 &"
	repeat with i from 1 to 30
		delay 0.5
		set isUp to (do shell script "curl -s -m 2 " & healthURL & " >/dev/null 2>&1 && echo yes || echo no")
		if isUp is "yes" then exit repeat
	end repeat
end if
if isUp is "yes" then
	do shell script "open http://localhost:5001"
else
	display alert "Signalbox editor did not start" message "See /tmp/signalbox-editor.log for details." as critical
end if
